"""Windows version of e2e_pipeline.py: end-to-end check without mic/keyboard:
Windows' own speech synthesis (an Italian voice) -> speech engine -> glossary -> LLM.

    python tests/e2e_pipeline_win.py    # speech model and LLM picked in the app's menu
"""
import os
import subprocess
import sys
import tempfile
import time
import wave

import numpy as np

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(ROOT, "src"))
import stt_win as stt  # noqa: E402
from cleanup import Cleaner, Glossary  # noqa: E402
from stt_clean_win import DEFAULT_LLMS  # noqa: E402
from tray_win import GLOSSARY, load_settings  # noqa: E402

PHRASES = [
    "Ci vediamo martedì alle cinque, no cancella, mercoledì alle sei.",
    "Domani mando la relazione al professore. Scrivilo in inglese.",
]
# System.Speech, with the Windows Italian voice if installed (Settings → Time & language → Speech)
SPEAK = """Add-Type -AssemblyName System.Speech
$s = New-Object System.Speech.Synthesis.SpeechSynthesizer
$it = $s.GetInstalledVoices() | Where-Object { $_.VoiceInfo.Culture.Name -eq 'it-IT' } | Select-Object -First 1
if ($it) { $s.SelectVoice($it.VoiceInfo.Name) }
$f = New-Object System.Speech.AudioFormat.SpeechAudioFormatInfo({sr}, 'Sixteen', 'Mono')
$s.SetOutputToWaveFile('{wav}', $f); $s.Speak([IO.File]::ReadAllText('{txt}')); $s.Dispose()"""


def speak(text: str, sr: int) -> np.ndarray:
    with tempfile.TemporaryDirectory() as d:
        wav, txt = os.path.join(d, "t.wav"), os.path.join(d, "t.txt")
        with open(txt, "w", encoding="utf-8") as f:
            f.write(text)
        script = SPEAK.replace("{sr}", str(sr)).replace("{wav}", wav).replace("{txt}", txt)
        subprocess.run(["powershell", "-NoProfile", "-Command", script], check=True)
        with wave.open(wav) as w:
            return np.frombuffer(w.readframes(w.getnframes()), np.int16).astype(np.float32) / 32768


def main() -> None:
    for stream in (sys.stdout, sys.stderr):
        stream.reconfigure(encoding="utf-8", errors="replace")
    s = load_settings()
    transcribe, sr = stt.load(s["stt"], s["stt_model"])
    glossary = Glossary(GLOSSARY)
    provider, model = (s["llm_provider"], s["llm_model"]) if s["llm_model"] else DEFAULT_LLMS[0]
    cleaner = Cleaner(model, "", glossary, provider=provider)
    if warning := cleaner.check():
        sys.exit(warning)
    cleaner.warm_up()
    try:
        for phrase in PHRASES:
            audio = speak(phrase, sr)
            t0 = time.perf_counter()
            raw = transcribe(audio)
            t1 = time.perf_counter()
            out = cleaner.clean(glossary.apply(raw))
            t2 = time.perf_counter()
            print(f"spoken : {phrase}\n{s['stt']:8} [{t1 - t0:.2f}s]: {raw}\nllm      [{t2 - t1:.2f}s]: {out!r}\n")
    finally:
        cleaner.unload()


if __name__ == "__main__":
    main()
