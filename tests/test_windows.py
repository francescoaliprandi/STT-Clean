"""Unit tests for the Windows modules (no mic, keyboard or model needed):

    python -m unittest discover tests

The speech-engine tests are plain Python and run on any OS; the rest import the Windows API and are
skipped elsewhere.
"""
import json
import os
import sys
import tempfile
import unittest
from unittest import mock

sys.path.insert(0, os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "src"))
import stt_win  # noqa: E402

WINDOWS = sys.platform == "win32"


class TestWindowsSpeechEngines(unittest.TestCase):
    def test_unknown_engine(self):
        with self.assertRaisesRegex(ValueError, "parakeet, whisper"):
            stt_win.load("piper")

    def test_available_lists_loadable_models_only(self):
        with tempfile.TemporaryDirectory() as hub:
            for repo, weights in [("istupakov--parakeet-tdt-0.6b-v3-onnx", "encoder-model.int8.onnx"),
                                  ("istupakov--parakeet-tdt-0.6b-v2-onnx", "encoder-model.onnx"),    # fp32 export
                                  ("dropbox-dash--faster-whisper-large-v3-turbo", "model.bin"),    # CTranslate2
                                  ("mlx-community--parakeet-tdt-0.6b-v3", "model.safetensors"),     # MLX: macOS only
                                  ("openai--whisper-large-v3", "model.safetensors"),                # PyTorch: no
                                  ("Systran--faster-whisper-small", "model.bin.incomplete"),        # downloading
                                  ("Comfy-Org--z_image_turbo", "model.bin")]:                       # not speech
                snap = os.path.join(hub, f"models--{repo}", "snapshots", "abc")
                os.makedirs(snap)
                open(os.path.join(snap, weights), "w").close()
            with mock.patch.dict(os.environ, {"HF_HUB_CACHE": hub}), \
                    mock.patch("importlib.util.find_spec", return_value=True):
                self.assertEqual(stt_win.available(), [            # in cache-folder order
                    ("whisper", "dropbox-dash/faster-whisper-large-v3-turbo"),
                    ("parakeet", "istupakov/parakeet-tdt-0.6b-v2-onnx"),
                    ("parakeet", "istupakov/parakeet-tdt-0.6b-v3-onnx")])
            with mock.patch.dict(os.environ, {"HF_HUB_CACHE": hub}), \
                    mock.patch("importlib.util.find_spec", return_value=None):
                self.assertEqual(stt_win.available(), [])          # engine not installed: nothing to offer

    def test_snapshot_needs_the_weights(self):
        with tempfile.TemporaryDirectory() as hub, mock.patch.dict(os.environ, {"HF_HUB_CACHE": hub}):
            with self.assertRaisesRegex(FileNotFoundError, "download it"):
                stt_win.snapshot("istupakov/parakeet-tdt-0.6b-v3-onnx", "parakeet")
            snap = os.path.join(hub, "models--istupakov--parakeet-tdt-0.6b-v3-onnx", "snapshots", "abc")
            os.makedirs(snap)
            open(os.path.join(snap, "encoder-model.int8.onnx"), "w").close()
            self.assertEqual(stt_win.snapshot("istupakov/parakeet-tdt-0.6b-v3-onnx", "parakeet"), snap)


@unittest.skipUnless(WINDOWS, "Windows API")
class TestKeystrokes(unittest.TestCase):
    def setUp(self):
        global output_win, W
        import output_win
        import win32 as W

    def keys(self, events):
        return [(e.u.ki.wVk, e.u.ki.wScan, e.u.ki.dwFlags) for e in events]

    def test_backspaces_then_unicode_text(self):
        down, up = W.KEYEVENTF_UNICODE, W.KEYEVENTF_UNICODE | W.KEYEVENTF_KEYUP
        self.assertEqual(self.keys(output_win.keystrokes("è", backspaces=1)),
                         [(W.VK_BACK, 0, 0), (W.VK_BACK, 0, W.KEYEVENTF_KEYUP), (0, 0xE8, down), (0, 0xE8, up)])

    def test_emoji_is_two_utf16_units(self):
        self.assertEqual([scan for _, scan, _ in self.keys(output_win.keystrokes("🙂"))],
                         [0xD83D, 0xD83D, 0xDE42, 0xDE42])

    def test_new_line_is_enter(self):
        self.assertEqual([vk for vk, _, _ in self.keys(output_win.keystrokes("a\nb"))],
                         [0, 0, W.VK_RETURN, W.VK_RETURN, 0, 0])

    def test_input_has_the_size_sendinput_expects(self):
        import ctypes
        self.assertEqual(ctypes.sizeof(W.INPUT), 40 if ctypes.sizeof(ctypes.c_void_p) == 8 else 28)


@unittest.skipUnless(WINDOWS, "Windows API")
class TestWindowsSettings(unittest.TestCase):
    def test_saved_values_keep_their_types(self):
        import tray_win
        with tempfile.TemporaryDirectory() as d:
            path = os.path.join(d, "settings.json")
            self.assertEqual(tray_win.load_settings(path), tray_win.DEFAULTS)      # nothing saved yet
            with open(path, "w", encoding="utf-8") as f:
                json.dump({"live": False, "llm_model": "google/gemma-4-12b", "unknown": 1}, f)
            s = tray_win.load_settings(path)
            self.assertIs(s["live"], False)
            self.assertEqual((s["llm_model"], s["llm"]), ("google/gemma-4-12b", True))
            self.assertNotIn("unknown", s)
            with open(path, "w", encoding="utf-8") as f:
                f.write("{ not json")
            self.assertEqual(tray_win.load_settings(path), tray_win.DEFAULTS)      # edited by hand, broken

    def test_hotkey(self):
        from tray_win import hotkey_label, parse_hotkey
        self.assertEqual(parse_hotkey("ctrl+win+r"), (0x2 | 0x8, ord("R")))
        self.assertEqual(parse_hotkey(" Ctrl + Alt + Space "), (0x2 | 0x1, 0x20))
        self.assertEqual(parse_hotkey("f9"), (0, 0x78))
        for bad in ("", "ctrl+", "hyper+r", "ctrl+è"):
            self.assertIsNone(parse_hotkey(bad), bad)
        self.assertEqual(hotkey_label("ctrl+win+r"), "Ctrl+Win+R")


if __name__ == "__main__":
    unittest.main()
