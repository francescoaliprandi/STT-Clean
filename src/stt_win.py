"""stt_win.py - speech-to-text engines on Windows (CPU), picked in the tray menu's Speech list.

The Windows counterpart of stt.py, same interface: available() lists the models a click away,
load(engine, model) -> (transcribe, sample_rate), free_cache() between dictations. MLX is Apple-only,
so the same two model families run in Windows formats:

    parakeet  NVIDIA Parakeet TDT, ONNX export, with onnx-asr + ONNX Runtime (default)
    whisper   OpenAI Whisper family, CTranslate2 format, with faster-whisper
"""
import glob
import importlib.util
import os

import numpy as np

os.environ.setdefault("HF_HUB_OFFLINE", "1")   # use the models already on this PC, never download one

DEFAULT_MODELS = {"parakeet": "istupakov/parakeet-tdt-0.6b-v3-onnx",
                  "whisper": "dropbox-dash/faster-whisper-large-v3-turbo"}
PACKAGES = {"parakeet": "onnx_asr", "whisper": "faster_whisper"}
WEIGHTS = {"parakeet": ["encoder-model.int8.onnx", "encoder-model.onnx"],   # onnx-asr's NeMo export
           "whisper": ["model.bin"]}                                         # CTranslate2
SAMPLE_RATE = 16000       # both engines


def hub() -> str:
    return os.environ.get("HF_HUB_CACHE") or os.path.join(
        os.environ.get("HF_HOME") or os.path.expanduser("~/.cache/huggingface"), "hub")


def snapshot(model: str, engine: str) -> str:
    """The cached folder of `model` that holds its weights (the newest snapshot if there are several)."""
    folder = os.path.join(hub(), "models--" + model.replace("/", "--"), "snapshots")
    found = [s for s in glob.glob(os.path.join(folder, "*"))
             if any(os.path.exists(os.path.join(s, w)) for w in WEIGHTS[engine])]
    if not found:
        raise FileNotFoundError(f"{model} isn't in the Hugging Face cache ({hub()}): download it (see the README)")
    return max(found, key=os.path.getmtime)


def available() -> list[tuple[str, str]]:
    """(engine, model) for each model in the Hugging Face cache that its installed engine can load."""
    found = []
    for folder in sorted(glob.glob(os.path.join(hub(), "models--*"))):
        repo = os.path.basename(folder)[len("models--"):].replace("--", "/", 1)
        for engine, package in PACKAGES.items():
            if (engine in repo.lower() and importlib.util.find_spec(package)
                    and any(glob.glob(os.path.join(folder, "snapshots", "*", w)) for w in WEIGHTS[engine])):
                found.append((engine, repo))
    return found


def free_cache() -> None:
    """Nothing to give back: unlike MLX, ONNX Runtime and CTranslate2 don't grow a cache per clip length."""


def load(engine: str, model: str = ""):
    engines = {"parakeet": _parakeet, "whisper": _whisper}
    if engine not in engines:
        raise ValueError(f'unknown speech engine "{engine}": use {", ".join(engines)}')
    return engines[engine](model or DEFAULT_MODELS[engine])


def _parakeet(model: str):
    import onnx_asr
    path = snapshot(model, "parakeet")
    # int8 if downloaded: on an 8-core Ryzen it re-transcribes a 30 s clip in 0.98 s (the live draft's
    # worst case), fp32 is the fallback for a cache that only has the full-size export
    int8 = os.path.exists(os.path.join(path, "encoder-model.int8.onnx"))
    m = onnx_asr.load_model("nemo-conformer-tdt", path, quantization="int8" if int8 else None)

    def transcribe(audio: np.ndarray) -> str:
        return m.recognize(audio.astype(np.float32), sample_rate=SAMPLE_RATE).strip()
    return transcribe, SAMPLE_RATE


def _whisper(model: str):
    try:
        from faster_whisper import WhisperModel
    except ImportError:
        raise ImportError("the whisper engine needs faster-whisper: run install.cmd again") from None
    # one thread per physical core (CTranslate2's default is 4). Still slow on a CPU: every clip is padded
    # to 30 s, so large-v3-turbo takes ~10 s for a 10 s clip on an 8-core Ryzen, where Parakeet takes 0.3 s
    m = WhisperModel(snapshot(model, "whisper"), device="cpu", compute_type="int8", cpu_threads=max(1, os.cpu_count() // 2))

    def transcribe(audio: np.ndarray) -> str:
        # same choices as stt.py: greedy (mlx-whisper's default; faster-whisper's is a 5-way beam search),
        # temperature 0 (no garbled random retries), no previous-text conditioning
        segments, _ = m.transcribe(audio.astype(np.float32), beam_size=1, temperature=0.0,
                                   condition_on_previous_text=False)
        return "".join(s.text for s in segments).strip()
    return transcribe, SAMPLE_RATE
