"""Builds the Windows start / stop / cancel sounds in windows/sounds/: soft single notes, the counterpart
of macOS' Tink, Pop and Funk (Windows' own speech sounds are metallic). Run again only to change them:
    python windows/make_sounds.py
"""
import os
import wave

import numpy as np

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
OUT = os.path.join(ROOT, "windows", "sounds")
SR = 44100


def note(freq: float, length: float, decay: float, volume: float) -> np.ndarray:
    """A soft mallet note: 12 ms attack, exponential decay, a pure tone with a faint octave, a 30 ms fade-out."""
    t = np.arange(int(SR * length)) / SR
    env = np.minimum(t / 0.012, 1) * np.exp(-decay * t) * np.minimum((length - t) / 0.03, 1)
    x = (np.sin(2 * np.pi * freq * t) + 0.12 * np.sin(4 * np.pi * freq * t)) * env
    return (x / np.abs(x).max() * volume * 32767).astype(np.int16)


SOUNDS = {"start.wav": note(659.25, 0.30, 14, 0.20),     # E5: "tink", a major third above stop
          "stop.wav": note(523.25, 0.26, 18, 0.20),      # C5: "pop"
          # G4 then D4, quick: two falling notes, a soft "uh-oh", heard apart from start and stop by its rhythm
          "cancel.wav": np.concatenate([note(392.0, 0.13, 22, 0.17), note(293.66, 0.22, 16, 0.17)])}

if __name__ == "__main__":
    os.makedirs(OUT, exist_ok=True)
    for name, samples in SOUNDS.items():
        with wave.open(os.path.join(OUT, name), "w") as w:
            w.setnchannels(1)
            w.setsampwidth(2)
            w.setframerate(SR)
            w.writeframes(samples.tobytes())
    print("wrote windows/sounds/start.wav, stop.wav, cancel.wav")
