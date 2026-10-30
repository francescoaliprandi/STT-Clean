"""tray_win.py - the STT-Clean icon in the Windows notification area, its menu and switches, and the status line.

The counterpart of menubar.py, same menu and behaviour: click = start / stop dictation; right-click = the
menu. The tray can't show text next to the icon, so the recording clock is in the icon's tooltip and the
icon turns red while recording. Lives on the main thread (a hidden window and its message loop); the
worker thread talks to it with call_after(), like AppHelper.callAfter on macOS.
"""
import atexit
import ctypes
import json
import os
import queue
import subprocess
import sys
import time
import winreg

import cleanup
import output_win
import stt_win as stt
import win32 as W
from audio import open_mic
from esc_key_win import EscKey
from output_win import focus

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
ICONS = os.path.join(ROOT, "windows", "icons")
UI = None                 # the Tray, once created


def status(msg: str, keep: bool = False, log: bool = True) -> None:
    """Show `msg` in the menu's status line and print it. In a terminal the line is redrawn in place
    unless `keep`; the app's log file gets every message except log=False ones (live drafts and
    dictated text: nothing you say is written to disk)."""
    if sys.stdout and sys.stdout.isatty():
        print(f"\r\033[K{msg}", end="\n" if keep else "", flush=True)
    elif sys.stdout and log:
        print(msg, flush=True)
    if UI is not None:
        UI.call_after(UI.note, msg)


# ---------------------------------------------------------------- settings: the menu's switches and picks
# Remembered in %APPDATA%\STT-Clean\settings.json (same for the app and a terminal run; delete it to start over).
SETTINGS = os.path.join(os.environ.get("APPDATA") or os.path.expanduser("~"), "STT-Clean", "settings.json")
DEFAULTS = {"llm": True, "live": True,                    # switches: smart clean-up, live text while speaking
            "stt": "parakeet", "stt_model": "",           # speech engine and model ("" = its default)
            "llm_provider": "lmstudio", "llm_model": "",  # LLM server and model ("" = found at launch)
            "hotkey": "ctrl+win+r"}                       # start / stop from the keyboard ("" = click only)
MODIFIERS = {"alt": 0x1, "ctrl": 0x2, "shift": 0x4, "win": 0x8}
MOD_NOREPEAT = 0x4000     # holding the keys down doesn't toggle again and again
KEYS = {"space": 0x20, **{f"f{n}": 0x6F + n for n in range(1, 25)}}


def parse_hotkey(text: str) -> tuple | None:
    """"ctrl+win+r" -> (modifiers, virtual key) for RegisterHotKey; None if empty or not understood."""
    *mods, key = [p.strip().lower() for p in text.split("+")] if text.strip() else [""]
    if not key or any(m not in MODIFIERS for m in mods):
        return None
    vk = KEYS.get(key) or (ord(key.upper()) if len(key) == 1 and key.isascii() and key.isalnum() else None)
    return (sum(MODIFIERS[m] for m in mods), vk) if vk else None


def hotkey_label(text: str) -> str:
    return "+".join(p.strip().capitalize() for p in text.split("+"))


def load_settings(path: str = SETTINGS) -> dict:
    try:
        with open(path, encoding="utf-8") as f:
            saved = json.load(f)
    except (OSError, ValueError):         # first launch, or a file edited by hand into invalid JSON
        saved = {}
    return {k: v if (x := saved.get(k)) is None else type(v)(x) for k, v in DEFAULTS.items()}


GLOSSARY = os.path.join(ROOT, "config", "glossary.txt")
GLOSSARY_TEMPLATE = """\
# STT-Clean glossary: how to spell names, brands and jargon the speech model gets wrong.
# One term per line:   Correct spelling: heard as 1, heard as 2
#   - the "heard as" variants (optional) are replaced exactly, before the LLM runs
#   - every term is also given to the LLM, which fixes close mis-hearings on its own
# Lines starting with # are ignored. Changes apply from the next dictation. Examples:
# Ollama: o lama, olama
# GitHub: git hub
"""

# ---------------------------------------------------------------- the tray icon
WM_TRAY, WM_CALL = W.WM_APP + 1, W.WM_APP + 2
CLOCK_TIMER, TICK_TIMER = 1, 2
HOTKEY_ID = 2             # the start / stop shortcut (Esc while recording is esc_key_win's 1)
# the taskbar and its pop-ups take the focus when you click the icon: they're never where the text goes
SHELL = {"Shell_TrayWnd", "Shell_SecondaryTrayWnd", "NotifyIconOverflowWindow", "TopLevelWindowForOverflowXamlIsland",
         "XamlExplorerHostIslandWindow", "#32768"}


def taskbar_is_light() -> bool:
    try:
        with winreg.OpenKey(winreg.HKEY_CURRENT_USER, r"Software\Microsoft\Windows\CurrentVersion\Themes\Personalize") as k:
            return bool(winreg.QueryValueEx(k, "SystemUsesLightTheme")[0])
    except OSError:
        return False


class Tray:
    """Hidden window + notification-area icon. Its window also owns the clipboard during a paste
    (output_win renders the text when the app reads it) and receives the Esc hot key."""

    def __init__(self):
        global UI
        self.events = queue.Queue()        # consumed by the worker thread
        self.calls = queue.Queue()         # functions to run on this thread (call_after)
        self.recording = False
        self.ready = False                 # model loaded
        self.sr = 0                        # model sample rate, set by the worker when ready
        self.stream = None                 # mic, open only while recording
        self.settings = load_settings()    # read by the worker
        self.current_stt = ("", "")        # (engine, model) in use, set by the worker once loaded
        self.current_llm = ("", "")        # (provider, model) in use, set by the worker
        self.info = "Starting ..."         # the menu's status line
        self.t0 = 0.0                      # recording start, for the clock
        self.last_app = None               # the last window you worked in (not the taskbar, not us)
        self.commands = {}                 # menu item id -> function, rebuilt each time the menu opens

        hinst = W.GetModuleHandleW(None)
        self._wndproc = W.WNDPROC(self.wndproc)            # kept referenced: Windows only holds the pointer
        wc = W.WNDCLASSEXW(cbSize=ctypes.sizeof(W.WNDCLASSEXW), lpfnWndProc=self._wndproc, hInstance=hinst,
                           lpszClassName="STT-Clean")
        W.RegisterClassExW(ctypes.byref(wc))
        self.taskbar_created = W.RegisterWindowMessageW("TaskbarCreated")   # before the window: it gets messages at once
        # a hidden top-level window, not a message-only one: only those hear TaskbarCreated (Explorer restarted)
        self.hwnd = W.CreateWindowExW(0, "STT-Clean", "STT-Clean", 0, 0, 0, 0, 0, None, None, hinst, None)
        output_win.OWNER = self.hwnd
        self.esc = EscKey(self.hwnd, lambda: self.end("cancel") if self.recording else None)
        self.shortcut = ""                 # the keyboard shortcut, if registered ("Ctrl+Win+R")
        if self.settings["hotkey"]:
            parsed = parse_hotkey(self.settings["hotkey"])
            if parsed and W.RegisterHotKey(self.hwnd, HOTKEY_ID, parsed[0] | MOD_NOREPEAT, parsed[1]):
                self.shortcut = hotkey_label(self.settings["hotkey"])   # else the worker warns, after Ready
        size = W.GetSystemMetrics(W.SM_CXSMICON)
        self.icons = {name: W.LoadImageW(None, os.path.join(ICONS, f"{name}.ico"), W.IMAGE_ICON, size, size,
                                         W.LR_LOADFROMFILE)
                      for name in ("idle-white", "idle-black", "busy-white", "busy-black", "recording")}
        self.nid = W.NOTIFYICONDATAW(cbSize=ctypes.sizeof(W.NOTIFYICONDATAW), hWnd=self.hwnd, uID=1,
                                     uFlags=W.NIF_MESSAGE | W.NIF_ICON | W.NIF_TIP, uCallbackMessage=WM_TRAY)
        self.show(add=True)
        self._on_foreground = W.WINEVENTPROC(self.foreground)
        self.hook = W.SetWinEventHook(W.EVENT_SYSTEM_FOREGROUND, W.EVENT_SYSTEM_FOREGROUND, None,
                                      self._on_foreground, 0, 0, W.WINEVENT_OUTOFCONTEXT)
        self.foreground(None, 0, W.GetForegroundWindow(), 0, 0, 0, 0)
        # Python runs signal handlers (Ctrl+C in a terminal) only when this thread runs Python code: a 0.5 s tick
        W.SetTimer(self.hwnd, TICK_TIMER, 500, None)
        UI = self

    # ---------------------------------------------------------------- the message loop
    def run(self) -> None:
        msg = W.w.MSG()
        while W.GetMessageW(ctypes.byref(msg), None, 0, 0) > 0:
            W.TranslateMessage(ctypes.byref(msg))
            W.DispatchMessageW(ctypes.byref(msg))

    def call_after(self, fn, *args) -> None:
        """Run fn(*args) on this thread (from the worker thread)."""
        self.calls.put((fn, args))
        W.PostMessageW(self.hwnd, WM_CALL, 0, 0)

    def wndproc(self, hwnd, msg, wparam, lparam):
        try:
            if msg == WM_TRAY:
                if lparam & 0xFFFF == W.WM_LBUTTONUP:
                    self.clicked()
                elif lparam & 0xFFFF == W.WM_RBUTTONUP:
                    self.menu()
                return 0
            if msg == WM_CALL:
                while not self.calls.empty():
                    fn, args = self.calls.get()
                    fn(*args)
                return 0
            if msg == W.WM_TIMER:
                if wparam == CLOCK_TIMER:
                    self.tip()
                return 0
            if msg == W.WM_HOTKEY:
                if wparam == HOTKEY_ID:
                    self.pressed()
                else:
                    self.esc.pressed()
                return 0
            if msg == W.WM_RENDERFORMAT:
                output_win.render(wparam)
                return 0
            if msg == W.WM_RENDERALLFORMATS:
                output_win.render_all()
                return 0
            if msg == self.taskbar_created:          # Explorer restarted: the icon is gone, add it again
                self.show(add=True)
                return 0
            if msg == W.WM_DESTROY:
                W.PostQuitMessage(0)
                return 0
        except Exception as e:                       # an exception must not cross back into Windows
            status(f"⚠️  {type(e).__name__}: {e}", keep=True)
            return 0
        return W.DefWindowProcW(hwnd, msg, wparam, lparam)

    def foreground(self, hook, event, hwnd, obj, child, thread, time_ms) -> None:
        """EVENT_SYSTEM_FOREGROUND: remember the last real app (where a click on the icon means "type here")."""
        if hwnd and hwnd != self.hwnd and W.class_name(hwnd) not in SHELL:
            self.last_app = hwnd

    def back_to_app(self) -> None:
        """Clicking the icon gave the focus to the taskbar: give it back to the app you were in.
        Windows lets us, since the click on our icon was the last input."""
        if self.last_app and W.IsWindow(self.last_app) and W.GetForegroundWindow() != self.last_app:
            W.SetForegroundWindow(self.last_app)
            end = time.monotonic() + 0.3
            while W.GetForegroundWindow() != self.last_app and time.monotonic() < end:
                time.sleep(0.01)
            time.sleep(0.05)               # and for the app to put the focus back in its text field

    # ---------------------------------------------------------------- clicks
    def pressed(self) -> None:
        """The keyboard shortcut: like a click, without leaving the app you're typing in."""
        if self.ready:
            if self.recording:
                self.end("stop")
            else:
                self.start()

    def clicked(self) -> None:
        self.back_to_app()
        if self.ready:
            if self.recording:
                self.end("stop")
            else:
                self.start()

    def start(self) -> None:
        try:                               # here, not in the worker: it may still be busy with the last dictation
            self.stream, rate = open_mic(self.sr, self.events)
        except Exception as e:             # no mic, or it refused to open (Settings → Privacy → Microphone)
            status(f"⚠️  Microphone: {type(e).__name__}: {e}", keep=True)
            return
        self.events.put(("start", (rate, focus())))   # where the text will be typed
        self.recording = True
        self.t0 = time.monotonic()
        W.SetTimer(self.hwnd, CLOCK_TIMER, 1000, None)
        if not self.esc.on():
            status("⚠️  Esc is taken by another app: cancel with Esc won't work.", keep=True)
        self.show()

    def end(self, kind: str) -> None:
        """Stop recording: "stop" transcribes and pastes, "cancel" (Esc) throws the dictation away."""
        self.recording = False
        self.stream.stop()                 # returns after the last callback: all audio is queued before `kind`
        self.stream.close()
        self.events.put((kind, None))
        self.esc.off()
        W.KillTimer(self.hwnd, CLOCK_TIMER)
        self.show(busy=kind == "stop")

    def toggle(self, key: str) -> None:
        self.save({key: not self.settings[key]})
        if key == "llm":
            self.events.put(("llm", self.settings[key]))   # the worker loads / unloads it

    def save(self, changes: dict) -> None:
        """Apply `changes` to the settings and remember them."""
        self.settings.update(changes)
        os.makedirs(os.path.dirname(SETTINGS), exist_ok=True)
        with open(SETTINGS, "w", encoding="utf-8") as f:
            json.dump(self.settings, f, indent=1)

    # ---------------------------------------------------------------- the menu
    def menu(self) -> None:
        """Built each time it opens, with what works right now (the Hugging Face cache and the local
        servers answer in ~40 ms). The models in use are ticked."""
        self.commands = {}
        root = W.CreatePopupMenu()
        self.item(root, "About STT-Clean", self.about)
        W.AppendMenuW(root, W.MF_SEPARATOR, 0, None)
        self.item(root, self.info if len(self.info) <= 80 else self.info[:79] + "…", None)
        W.AppendMenuW(root, W.MF_SEPARATOR, 0, None)

        engine, model = self.current_stt
        speech = stt.available()
        if model and (engine, model) not in speech:
            speech.insert(0, (engine, model))       # in use, but no longer found in the cache
        groups = {}                                 # one section per engine
        for e, m in speech:
            groups.setdefault(e.capitalize(), []).append((m.split("/")[-1], (e, m), (e, m) == self.current_stt))
        self.submenu(root, f"Speech: {model.split('/')[-1]}" if model else "Speech Model", list(groups.items()),
                     self.pick_speech, "No speech model found (see the README)")

        provider, model = self.current_llm
        servers = cleanup.available()
        if model and not any(p == provider and model in names for _, p, names in servers):
            servers.insert(0, ("In use", provider, [model]))   # its server stopped or doesn't list it
        sections = [(label, [(n.removesuffix(":latest"), (p, n), (p, n) == self.current_llm) for n in names])
                    for label, p, names in servers]
        self.submenu(root, f"LLM: {model.removesuffix(':latest')}" if model else "LLM", sections, self.pick_llm,
                     "No LLM server running (Ollama, LM Studio)")
        W.AppendMenuW(root, W.MF_SEPARATOR, 0, None)

        for key, title in (("llm", "Smart clean-up (LLM)"), ("live", "Live text while speaking")):
            self.item(root, title, lambda key=key: self.toggle(key), self.settings[key])
        self.item(root, "Edit Glossary…", self.edit_glossary)
        W.AppendMenuW(root, W.MF_SEPARATOR, 0, None)
        self.item(root, "Quit STT-Clean", self.quit)

        pt = W.w.POINT()
        W.GetCursorPos(ctypes.byref(pt))
        W.SetForegroundWindow(self.hwnd)   # else the menu doesn't close when you click elsewhere
        chosen = W.TrackPopupMenu(root, W.TPM_RIGHTBUTTON | W.TPM_RETURNCMD | W.TPM_NONOTIFY, pt.x, pt.y, 0,
                                  self.hwnd, None)
        W.PostMessageW(self.hwnd, W.WM_NULL, 0, 0)
        W.DestroyMenu(root)                # its submenus with it
        if chosen in self.commands:
            self.commands[chosen]()

    def item(self, menu, title: str, action, ticked: bool = False) -> None:
        """A menu entry calling `action`; no action = a greyed line (status, section header)."""
        flags = W.MF_STRING | (W.MF_CHECKED if ticked else 0) | (0 if action else W.MF_GRAYED)
        cid = len(self.commands) + 1
        if action:
            self.commands[cid] = action
        W.AppendMenuW(menu, flags, cid if action else 0, title)

    def submenu(self, root, title: str, sections, action, empty: str) -> None:
        """A submenu: a greyed header per section, then (title, choice, ticked) items that call action(choice)."""
        sub = W.CreatePopupMenu()
        for header, items in sections:
            self.item(sub, header, None)
            for name, choice, ticked in items:
                self.item(sub, f"    {name}", lambda choice=choice: action(choice), ticked)
        if not sections:
            self.item(sub, empty, None)
        W.AppendMenuW(root, W.MF_POPUP, sub, title)

    def pick_speech(self, choice: tuple) -> None:
        if choice == self.current_stt:
            return
        if self.recording:                 # (while loading is fine: the worker takes picks in order)
            status("⚠️  Switch the speech model after this dictation.", keep=True)
            return
        self.ready = False                 # no new dictation until it's loaded
        self.show()
        self.events.put(("stt", choice))

    def pick_llm(self, choice: tuple) -> None:
        if self.recording:
            status("⚠️  Switch the LLM after this dictation.", keep=True)
            return
        was_on = self.settings["llm"]
        if not was_on:
            self.save({"llm": True})       # picking an LLM means using it
        if choice != self.current_llm:
            self.events.put(("llm_model", choice))
        elif not was_on:
            self.events.put(("llm", True))

    def about(self) -> None:
        W.MessageBoxW(self.hwnd, f"Live speech-to-text with LLM refinement, on this PC.\n\n"
                      f"Speech: {self.current_stt[1]} ({self.current_stt[0]})\n"
                      f"LLM: {self.current_llm[1]} ({self.current_llm[0]})", "STT-Clean",
                      W.MB_OK | W.MB_ICONINFORMATION)

    def edit_glossary(self) -> None:
        if not os.path.exists(GLOSSARY):
            os.makedirs(os.path.dirname(GLOSSARY), exist_ok=True)
            with open(GLOSSARY, "w", encoding="utf-8") as f:
                f.write(GLOSSARY_TEMPLATE)
        subprocess.Popen(["notepad.exe", GLOSSARY])

    def quit(self) -> None:
        if self.recording:
            self.end("cancel")
        W.UnhookWinEvent(self.hook)
        W.UnregisterHotKey(self.hwnd, HOTKEY_ID)
        W.Shell_NotifyIconW(W.NIM_DELETE, ctypes.byref(self.nid))
        W.DestroyWindow(self.hwnd)         # ends run(); atexit then unloads the LLM

    # ---------------------------------------------------------------- the icon
    def show(self, busy: bool = False, add: bool = False) -> None:
        """The logo: red voice wave while recording (clock in the tooltip), sparkle while loading /
        transcribing / cleaning up, else the voice wave in the taskbar's text colour."""
        busy = (busy or not self.ready) and not self.recording
        color = "black" if taskbar_is_light() else "white"
        self.nid.hIcon = self.icons["recording" if self.recording else f"{'busy' if busy else 'idle'}-{color}"]
        self.tip(add)

    def tip(self, add: bool = False) -> None:
        if self.recording:
            s = int(time.monotonic() - self.t0)
            again = f"click or {self.shortcut}" if self.shortcut else "click"
            tip = f"STT-Clean ● {s // 60}:{s % 60:02d}  ({again} to stop, Esc to cancel)"
        else:
            tip = f"STT-Clean: {self.info}"
        self.nid.szTip = tip if len(tip) < 128 else tip[:126] + "…"
        W.Shell_NotifyIconW(W.NIM_ADD if add else W.NIM_MODIFY, ctypes.byref(self.nid))

    def note(self, msg: str) -> None:
        self.info = msg
        self.tip()                         # the icon itself changes only in show(), as on macOS


atexit.register(lambda: UI and W.Shell_NotifyIconW(W.NIM_DELETE, ctypes.byref(UI.nid)))   # no ghost icon
