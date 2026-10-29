"""Windows runner for bench_llm.py: the same 16 dictations and checks, with the Windows app's settings.

    python tests/bench_llm_win.py                        # the LLM picked in the app's menu, else Gemma 4 12B
    python tests/bench_llm_win.py google/gemma-4-12b google/gemma-4-26b-a4b    # models on the server picked in the menu

bench_llm.py reads the app's settings from menubar.py, which needs AppKit; tray_win.py has the same
load_settings() and keys, so it stands in for it. Exits with status 1 if any case fails.
"""
import os
import runpy
import sys

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(ROOT, "src"))
import cleanup  # noqa: E402
import tray_win  # noqa: E402
from stt_clean_win import default_llm  # noqa: E402

sys.modules["menubar"] = tray_win
if len(sys.argv) == 1:
    s = tray_win.load_settings()
    sys.argv.append(s["llm_model"] or default_llm([(p, n) for _, p, names in cleanup.available() for n in names])[1])
for stream in (sys.stdout, sys.stderr):
    stream.reconfigure(encoding="utf-8", errors="replace")   # the ✓ / ✗ marks, in any console
runpy.run_path(os.path.join(ROOT, "tests", "bench_llm.py"), run_name="__main__")
