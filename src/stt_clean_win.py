#!/usr/bin/env python
"""stt_clean_win.py - STT-Clean: local dictation for Windows, as a notification-area (tray) app.

The Windows counterpart of stt_clean.py, same use and same worker loop: click the STT-Clean icon in the
notification area, speak, click it again (Esc cancels). While you speak, a live draft is typed where
your cursor is, in any app. On stop the audio is transcribed again, cleaned up by a local LLM, and the
draft is replaced with the final text. Right-click it for the same menu as on macOS.
Everything runs on this PC: speech on the CPU (stt_win.py), the LLM in LM Studio or Ollama (cleanup.py).

    Start menu → STT-Clean                        # normal use (install.cmd adds the shortcut)
    .venv\\Scripts\\python src\\stt_clean_win.py              # same, from a terminal (log in the terminal)
    .venv\\Scripts\\python src\\stt_clean_win.py --no-paste   # only print the text (live draft in the terminal)

Shared with macOS: audio (mic), live (live-draft text), cleanup (LLM + glossary). Windows modules: tray_win
(icon, menu, status line), output_win (typing, clipboard, paste), esc_key_win (Esc while recording),
stt_win (speech engines), win32 (the Windows API). This file: the options and the worker loop, kept
line for line like stt_clean.py's so a fix there is easy to carry over.
"""
import argparse
import atexit
import ctypes
import os
import re
import shutil
import signal
import sys
import threading
import time
import winsound

import numpy as np

import stt_win as stt
from audio import resample
import cleanup
from cleanup import Cleaner, Glossary
from live import advance
from output_win import blocked, can_post, copy, paste, retype
from tray_win import GLOSSARY, ROOT, SETTINGS, Tray, status
import win32 as W

MIN_SECONDS = 0.3         # shorter clicks are ignored
# the LLM picked when none is yet: Gemma 4 12B, the one the prompt was tuned on, under any of its names
# (LM Studio's id depends on the variant downloaded: google/gemma-4-12b, gemma-4-12b-it-qat, ...; Ollama: gemma4:12b)
GEMMA = re.compile(r"gemma-?4[-:]12b", re.IGNORECASE)
DEFAULT_LLM = ("lmstudio", "google/gemma-4-12b")    # named in the warning when no server has a model
# soft notes made by windows/make_sounds.py (Windows' own speech sounds are metallic), like macOS' Tink, Pop, Funk
SOUND_START = os.path.join(ROOT, "windows", "sounds", "start.wav")
SOUND_STOP = os.path.join(ROOT, "windows", "sounds", "stop.wav")
SOUND_CANCEL = os.path.join(ROOT, "windows", "sounds", "cancel.wav")


def play(path: str) -> None:
    if os.path.exists(path):
        winsound.PlaySound(path, winsound.SND_FILENAME | winsound.SND_ASYNC | winsound.SND_NODEFAULT)


def default_llm(found: list) -> tuple:
    """(provider, model) to use when none is picked yet, among `found` [(provider, model)]: Gemma 4 12B,
    else the first one found."""
    return next((c for c in found if GEMMA.search(c[1])), found[0] if found else DEFAULT_LLM)


def save_debug(audio: np.ndarray, drafts: list) -> None:
    """Last dictation only (overwritten): exact float32 audio + every live draft and the text typed
    after it, to replay offline."""
    d = os.path.join(ROOT, "logs", "debug")
    os.makedirs(d, exist_ok=True)
    np.save(os.path.join(d, "last.npy"), audio)
    with open(os.path.join(d, "last_drafts.txt"), "w", encoding="utf-8") as f:
        f.writelines(f"{n}\t{draft}\t{typed}\n" for n, draft, typed in drafts)


# ---------------------------------------------------------------- main
def main() -> None:
    ap = argparse.ArgumentParser(description="STT-Clean: local tray dictation. Speech model and LLM "
                                 "are picked in its menu (right-click the icon).")
    ap.add_argument("--no-paste", action="store_true", help="only print the text, don't type or paste it")
    ap.add_argument("--debug", action="store_true",
                    help="overwrite logs/debug/last.npy (audio) and last_drafts.txt after each dictation")
    args = ap.parse_args()

    if sys.stdout is None:                 # started without a console (pythonw, the Start menu shortcut)
        os.makedirs(os.path.join(ROOT, "logs"), exist_ok=True)   # the log of this run, overwritten at each launch
        sys.stdout = sys.stderr = open(os.path.join(ROOT, "logs", "stt-clean.log"), "w", encoding="utf-8", buffering=1)
    else:                                  # a console or a pipe: Windows' default code page has no ⚠️ or ✨
        for stream in (sys.stdout, sys.stderr):
            stream.reconfigure(encoding="utf-8", errors="replace")
    W.CreateMutexW(None, False, "Local\\STT-Clean")
    if ctypes.get_last_error() == W.ERROR_ALREADY_EXISTS:      # one icon, one mic, one LLM
        W.MessageBoxW(None, "STT-Clean is already running: its icon is in the notification area.", "STT-Clean",
                      W.MB_OK | W.MB_ICONINFORMATION)
        return
    W.SetProcessDpiAwarenessContext(W.w.HANDLE(-4))   # per-monitor DPI: a sharp icon and menu on scaled screens
    ui = Tray()
    # Ctrl+C, closing the terminal: quit through the tray so the LLM still gets unloaded
    for sig in (signal.SIGINT, signal.SIGTERM, signal.SIGBREAK):
        signal.signal(sig, lambda *_: ui.call_after(ui.quit))
    threading.Thread(target=run, args=(args, ui), daemon=True).start()
    ui.run()


def run(args, ui: Tray) -> None:
    """Worker thread: owns all speech-model calls, consumes ui.events."""
    try:
        work(args, ui)
    except Exception as e:                 # e.g. the model failed to load: show it in the menu instead of dying silently
        status(f"⚠️  {type(e).__name__}: {e}", keep=True)


def work(args, ui: Tray) -> None:
    s = ui.settings
    warnings = []             # shown after Ready, so they stay in the menu's status line
    glossary = Glossary(GLOSSARY)
    provider, model = s["llm_provider"], s["llm_model"]
    if not model:             # nothing picked yet: the recommended model if installed, else the first one found
        found = [(p, n) for _, p, names in cleanup.available() for n in names]
        provider, model = default_llm(found)
    cleaner = Cleaner(model, "", glossary, provider=provider)
    ui.current_llm = (provider, model)
    atexit.register(lambda: cleaner.unload())   # frees the LLM's RAM on any exit (the current one)

    def llm_name() -> str:
        return f"{cleaner.model} ({cleaner.label})"

    def llm_error() -> str | None:
        """Check the server and load the model; why it can't be used, or None."""
        if warning := cleaner.check():
            return warning
        status(f"Loading {llm_name()} ...")
        return None if cleaner.warm_up() else f"LLM warm-up failed: {cleaner.last_error}"

    def load_speech(engine: str, model: str):
        status(f"Loading {model} ({engine}) ...")
        new, new_sr = stt.load(engine, model)
        new(np.zeros(new_sr, dtype=np.float32))   # warm-up
        return new, new_sr

    llm = "off"
    if s["llm"]:
        error = llm_error()
        llm = "unavailable, raw text" if error else llm_name()
        if error:
            warnings.append(f"⚠️  {error} Raw transcript until that's fixed.")

    # only speech models already on this PC: the last pick first, then Parakeet v3, then any other
    found = sorted(stt.available(), key=lambda c: (c != (s["stt"], s["stt_model"]), c[1] != stt.DEFAULT_MODELS["parakeet"]))
    transcribe, sr, engine, stt_model = None, 0, "", ""
    for e, m in found:
        try:
            transcribe, sr = load_speech(e, m)
            engine, stt_model = e, m
            break
        except Exception as ex:
            warnings.append(f"⚠️  {m} didn't load: {type(ex).__name__}: {ex}")
    if not transcribe:        # the app stays up: download one, then pick it in the Speech menu
        warnings.append("⚠️  No speech model found on this PC: download one (see the README), "
                        "then pick it in the menu → Speech.")

    events = ui.events
    ui.current_stt = (engine, stt_model)
    ui.sr = sr
    ui.ready = transcribe is not None
    ui.call_after(ui.show)
    if ui.ready:
        how = f"click the STT-Clean icon or press {ui.shortcut}" if ui.shortcut else "click the STT-Clean icon"
        status(f"Ready: {how} to dictate, again to stop, Esc to cancel. LLM: {llm}.", keep=True)
    if s["hotkey"] and not ui.shortcut:
        warnings.append(f"⚠️  The shortcut {s['hotkey']} is taken by another app (or not understood): change "
                        f"\"hotkey\" in {SETTINGS}, then restart STT-Clean. Clicking the icon still works.")
    for warning in warnings:
        status(warning, keep=True)

    recording = False
    capture_sr = sr           # the mic's rate for this recording (resampled to sr)
    target = ()               # focus() at start (app, window, control): the only place we type into
    chunks: list = []
    fresh = 0                 # samples recorded since the last live-draft update
    typed = ""                # live draft currently typed in the focused app
    prev = ""                 # previous live draft
    drafts: list = []         # (samples, draft, typed) of each live update, for --debug
    can_type = False          # False in an app run as administrator: Windows silently drops our keystrokes there

    def erase_draft() -> None:
        if typed and can_type and can_post(target, wait=2):
            paste("", typed, target)

    def deliver(text: str) -> None:
        """Replace the live draft with `text` in the app it was typed into, or leave `text` on the clipboard."""
        if args.no_paste:
            return
        if can_type and can_post(target, wait=2):
            if not paste(text if text[-1].isspace() else text + " ", typed, target):
                status("⚠️  The app didn't paste: the text is on the clipboard, press Ctrl+V.", keep=True)
            return
        copy(text)                       # don't lose the dictation
        why = ("you moved to another app or window (or a key is held)" if can_type
               else "the app runs as administrator, which blocks typing from STT-Clean")
        status(f"⚠️  Not typed: {why}. Text copied, paste it with Ctrl+V.", keep=True)

    def finish(audio: np.ndarray) -> None:
        status("… transcribing")
        t0 = time.perf_counter()
        text = transcribe(audio)
        dt = time.perf_counter() - t0
        if not text:
            status("(no speech detected)", keep=True)
            erase_draft()
            return
        status(f"✓ [{len(audio) / sr:.1f}s audio, {dt:.2f}s] {text}", keep=True, log=False)   # no dictated text on disk
        glossary.maybe_reload()
        text = glossary.apply(text)
        if ui.settings["llm"]:
            status("✨ cleaning up ...")
            t0 = time.perf_counter()
            cleaned = cleaner.clean(text)
            dt = time.perf_counter() - t0
            if cleaned is None:
                status(f"(LLM skipped, raw text pasted: {cleaner.last_error})", keep=True)
            else:
                status(f"✨ [{dt:.2f}s] " + (cleaned.replace("\n", " ⏎ ") if cleaned != text else "(unchanged)"),
                       keep=True, log=False)
                text = cleaned
        deliver(text)

    while True:
        kind, data = events.get()

        if kind == "llm":
            if not data:
                cleaner.unload()          # frees its RAM (~8 GB for a 12B model)
                status("Smart clean-up off: raw transcript (glossary still applied).", keep=True)
            elif error := llm_error():
                status(f"⚠️  {error} Raw transcript until that's fixed.", keep=True)
            else:
                status(f"Smart clean-up on ({llm_name()}).", keep=True)

        elif kind == "llm_model":         # picked in the LLM menu: switch, or stay on the old one if it fails
            provider, model = data
            old = cleaner
            old.unload()                  # don't hold two models in RAM
            cleaner = Cleaner(model, "", glossary, provider=provider)
            if error := llm_error():
                cleaner.unload()          # it may have loaded before failing (e.g. it answers instead of cleaning)
                cleaner = old
                llm_error()
                status(f"⚠️  {model} didn't work, still using {old.model}: {error}", keep=True)
            else:
                ui.current_llm = data
                ui.call_after(ui.save, {"llm_provider": provider, "llm_model": model})
                status(f"LLM: {llm_name()}.", keep=True)

        elif kind == "stt":               # picked in the Speech menu (the menu set ui.ready = False)
            new_engine, new_model = data
            try:
                new, new_sr = load_speech(new_engine, new_model)
            except Exception as e:
                status(f"⚠️  {new_model} didn't load, still using {stt_model or 'none'}: {type(e).__name__}: {e}", keep=True)
            else:
                transcribe, sr, engine, stt_model = new, new_sr, new_engine, new_model
                ui.sr, ui.current_stt = sr, data
                ui.call_after(ui.save, {"stt": engine, "stt_model": stt_model})
                status(f"Speech model: {stt_model} ({engine}).", keep=True)
            stt.free_cache()              # the old model's buffers
            ui.ready = transcribe is not None
            ui.call_after(ui.show)

        elif kind == "start":
            recording, chunks, fresh, typed, prev, drafts = True, [], 0, "", "", []
            capture_sr, target = data
            can_type = not args.no_paste and not blocked(target)   # re-checked: each dictation has its own app
            play(SOUND_START)
            status("● recording ...")

        elif kind == "audio" and recording:
            chunk = resample(data, capture_sr, sr)
            chunks.append(chunk)
            fresh += len(chunk)
            # live draft: re-transcribe the whole clip every ~0.5 s, once the queue is drained.
            # shortcut: cost grows with length (on an 8-core Ryzen, CPU: ~0.3 s per update at 10 s, ~1 s
            # at 30 s, ~1.5 s at 40 s); if long dictations lag, freeze old sentences and re-transcribe only the tail
            if ui.settings["live"] and fresh >= sr // 2 and events.empty():
                fresh = 0
                so_far = np.concatenate(chunks)
                draft = transcribe(so_far)
                cols = shutil.get_terminal_size().columns - 3   # one line, or \r can't redraw it
                status("● " + (draft[-cols:] if draft else "recording ..."), log=False)
                if can_type and can_post(target):   # else skip this update: the next one catches up
                    new = advance(typed, prev, draft)
                    retype(typed, new)
                    typed = new
                prev = draft
                drafts.append((len(so_far), draft, typed))

        elif kind == "cancel" and recording:
            recording = False
            play(SOUND_CANCEL)
            erase_draft()
            stt.free_cache()
            status("✕ Cancelled (Esc): nothing pasted.", keep=True)

        elif kind == "stop" and recording:
            recording = False
            play(SOUND_STOP)
            audio = np.concatenate(chunks) if chunks else np.zeros(0, np.float32)
            if args.debug:
                save_debug(audio, drafts)
            try:
                if len(audio) < MIN_SECONDS * sr:
                    status("(too short, ignored)", keep=True)
                    erase_draft()
                else:
                    finish(audio)
            except Exception as e:        # one bad dictation must not kill the loop
                status(f"⚠️  {type(e).__name__}: {e}", keep=True)
            stt.free_cache()
            ui.call_after(ui.show)        # back to the idle icon


if __name__ == "__main__":
    if sys.platform != "win32":
        sys.exit("stt_clean_win.py is the Windows version: on macOS run stt_clean.py.")
    main()
