#!/bin/zsh
# Builds build/STT-Clean.app (./install.sh runs it). By hand:  zsh macos/build_app.sh
# Uses STT_CLEAN_PYTHON, else .venv/bin/python, else python3; that Python must have the dependencies.
# The app remembers that Python, this folder and HF_HOME (the model cache): re-run after moving any of them.
# Rebuilding changes the app's ad-hoc signature (its identity is the hash of its contents), so old
# permissions no longer match and macOS would silently drop the typing: they are reset below and
# asked for again on the next launch.
set -e
cd "${0:A:h}/.."
PY=${STT_CLEAN_PYTHON:-$([[ -x .venv/bin/python ]] && print -r -- $PWD/.venv/bin/python || command -v python3)}
HF=${HF_HOME:-$HOME/.cache/huggingface}
"$PY" -c "import numpy, sounddevice, AppKit, Quartz" 2>/dev/null ||
  { print -r -- "$PY can't import the dependencies: run ./install.sh (or set STT_CLEAN_PYTHON)."; exit 1 }
pkill -f "$PWD/src/stt_clean.py" && sleep 2 || true   # quit a running STT-Clean (it unloads its LLM)
C=build/STT-Clean.app/Contents
rm -rf build/STT-Clean.app
mkdir -p $C/MacOS $C/Resources logs
cp macos/Info.plist $C/
cp macos/AppIcon.icns $C/Resources/
clang -O2 -Wall -o $C/MacOS/STT-Clean macos/launcher.c -DPYTHON="\"$PY\"" -DHF_HOME="\"$HF\"" \
  -DSCRIPT="\"$PWD/src/stt_clean.py\"" -DLOG="\"$PWD/logs/stt-clean.log\""
codesign --force --sign - build/STT-Clean.app
tccutil reset All com.riccardoroselli.stt-clean >/dev/null 2>&1 || true
print -r -- "Built $PWD/build/STT-Clean.app (Python: $PY, models: $HF)"
