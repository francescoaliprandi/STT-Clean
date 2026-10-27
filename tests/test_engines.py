"""Unit tests for the pluggable parts: speech engines (stt.py), LLM servers (cleanup.py).

    python -m unittest discover tests
"""
import os
import sys
import tempfile
import unittest
import urllib.error
from unittest import mock

sys.path.insert(0, os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "src"))
import stt  # noqa: E402
from cleanup import Cleaner, Glossary, strip_wrapping  # noqa: E402


class TestSpeechEngines(unittest.TestCase):
    def test_unknown_engine(self):
        with self.assertRaisesRegex(ValueError, "parakeet, whisper"):
            stt.load("piper")

    def test_available_lists_loadable_models_only(self):
        with tempfile.TemporaryDirectory() as hub:
            for repo, weights in [("mlx-community--parakeet-tdt-0.6b-v3", "model.safetensors"),
                                  ("mlx-community--whisper-tiny", "weights.npz"),
                                  ("openai--whisper-large-v3", "model.safetensors"),     # PyTorch format: no
                                  ("mlx-community--whisper-small-mlx", "weights.npz.incomplete"),   # downloading
                                  ("Comfy-Org--z_image_turbo", "model.safetensors")]:    # not speech
                snap = os.path.join(hub, f"models--{repo}", "snapshots", "abc")
                os.makedirs(snap)
                open(os.path.join(snap, weights), "w").close()
            with mock.patch.dict(os.environ, {"HF_HUB_CACHE": hub}), \
                    mock.patch("importlib.util.find_spec", return_value=True):
                self.assertEqual(stt.available(), [("parakeet", "mlx-community/parakeet-tdt-0.6b-v3"),
                                                   ("whisper", "mlx-community/whisper-tiny")])
            with mock.patch.dict(os.environ, {"HF_HUB_CACHE": hub}), \
                    mock.patch("importlib.util.find_spec", side_effect=lambda p: p == "parakeet_mlx"):
                self.assertEqual([e for e, _ in stt.available()], ["parakeet"])   # mlx-whisper not installed


class TestLLMProviders(unittest.TestCase):
    def test_unknown_provider(self):
        with self.assertRaisesRegex(ValueError, "ollama or lmstudio"):
            Cleaner("x", "", Glossary(None), provider="openai")

    def test_default_urls(self):
        self.assertEqual(Cleaner("x", "", Glossary(None)).url, "http://127.0.0.1:11434")
        self.assertEqual(Cleaner("x", "", Glossary(None), provider="lmstudio").url, "http://127.0.0.1:1234/v1")

    def test_lmstudio_request_and_reply(self):
        c = Cleaner("qwen3", "http://h/v1/", Glossary(None), provider="lmstudio")
        sent = {}

        def post(path, body, timeout):
            sent.update(path=path, body=body)
            return {"choices": [{"message": {"content": "<think>\nhmm\n</think>\n\nCiao, come stai?"},
                                 "finish_reason": "stop"}]}
        c._post = post
        self.assertEqual(c.clean("ciao come stai"), "Ciao, come stai?")
        self.assertEqual(sent["path"], "/chat/completions")
        self.assertEqual(sent["body"]["temperature"], 0)
        self.assertNotIn("think", sent["body"])        # Ollama-only fields stay out

    def test_lmstudio_strict_server_drops_thinking_fields(self):
        c = Cleaner("x", "", Glossary(None), provider="lmstudio")
        bodies = []

        def post(path, body, timeout):
            bodies.append(body)
            if "reasoning_effort" in body:
                raise urllib.error.HTTPError(path, 400, "Unsupported parameter", {}, None)
            return {"choices": [{"message": {"content": "Ciao."}, "finish_reason": "stop"}]}
        c._post = post
        self.assertEqual(c.clean("ciao"), "Ciao.")
        self.assertEqual(c.clean("ciao"), "Ciao.")
        self.assertEqual(len(bodies), 3)               # one rejected request, then plain ones only

    def test_other_400_keeps_thinking_off(self):
        c = Cleaner("x", "", Glossary(None), provider="lmstudio")

        def post(path, body, timeout):               # e.g. a dictation too long for the server's context
            raise urllib.error.HTTPError(path, 400, "context length exceeded", {}, None)
        c._post = post
        self.assertIsNone(c.clean("ciao"))
        self.assertTrue(c.no_think)

    def test_lmstudio_cut_off(self):
        c = Cleaner("x", "", Glossary(None), provider="lmstudio")
        c._post = lambda *_, **__: {"choices": [{"message": {"content": "Ciao"}, "finish_reason": "length"}]}
        self.assertIsNone(c.clean("ciao come stai"))
        self.assertIn("cut off", c.last_error)

    def test_lmstudio_check(self):
        c = Cleaner("missing", "", Glossary(None), provider="lmstudio")
        c._post = lambda *_, **__: {"data": [{"id": "qwen3-8b"}, {"id": "text-embedding-nomic"}]}
        self.assertEqual(c.models(1), ["qwen3-8b"])     # embedding models can't chat
        self.assertIn("isn't in LM Studio", c.check())
        c.model = "qwen3-8b"
        self.assertIsNone(c.check())

    def test_think_block_only_at_start(self):
        self.assertEqual(strip_wrapping("x", "Use <think></think> tags"), "Use <think></think> tags")


class TestSettings(unittest.TestCase):
    def test_saved_values_keep_their_types(self):
        import menubar
        from AppKit import NSUserDefaults
        prefs = NSUserDefaults.alloc().initWithSuiteName_("stt-clean-unittest")
        self.addCleanup(prefs.removePersistentDomainForName_, "stt-clean-unittest")
        with mock.patch.object(menubar, "PREFS", prefs):
            self.assertEqual(menubar.load_settings(), menubar.DEFAULTS)          # nothing saved yet
            prefs.setObject_forKey_(False, "live")
            prefs.setObject_forKey_("qwen3:8b", "llm_model")
            s = menubar.load_settings()
        self.assertIs(s["live"], False)
        self.assertEqual((s["llm_model"], type(s["llm_model"]), s["llm"]), ("qwen3:8b", str, True))


if __name__ == "__main__":
    unittest.main()
