#!/bin/zsh
# Installs STT-Clean in this folder:  ./install.sh
#   1. a Python environment in .venv with the app's Python packages (~0.5 GB; no models)
#   2. the app, build/STT-Clean.app, and opens it
# It downloads no model: STT-Clean uses the speech models and LLMs already on this Mac.
# Run it again after updating (git pull): it only adds what is missing and rebuilds the app.
# Use your own Python environment instead of .venv:  STT_CLEAN_PYTHON=/path/to/python ./install.sh
set -e
cd "${0:A:h}"
step() { print -P "\n%B==> $1%b" }
fail() { print -r -- "✗ $1"; exit 1 }

[[ $(uname -s) == Darwin && $(uname -m) == arm64 ]] || fail "STT-Clean needs a Mac with Apple silicon (M1 or newer)."
xcode-select -p >/dev/null 2>&1 || fail "Install Apple's command line tools first:  xcode-select --install  (then run ./install.sh again)"

PY=$STT_CLEAN_PYTHON
if [[ -z $PY ]]; then
  if [[ ! -x .venv/bin/python ]]; then
    for p in python3.14 python3.13 python3.12 python3; do     # the dependencies need Python 3.12 or newer
      if command -v $p >/dev/null && $p -c 'import sys; sys.exit(sys.version_info < (3, 12))' 2>/dev/null; then
        BASE=$p; break
      fi
    done
    [[ -n $BASE ]] || fail "Needs Python 3.12 or newer: install it from https://www.python.org/downloads/macos/ (or: brew install python), then run ./install.sh again."
    step "Creating the Python environment (.venv) with $($BASE --version)"
    $BASE -m venv .venv
  fi
  PY=$PWD/.venv/bin/python
fi

step "Installing the dependencies"
$PY -m pip install --disable-pip-version-check -r src/requirements.txt
$PY -m pip install --disable-pip-version-check --no-deps mlx-whisper==0.4.3   # Whisper engine, without PyTorch

step "Building the app"
STT_CLEAN_PYTHON=$PY zsh macos/build_app.sh
open build/STT-Clean.app

print -r -- "
✓ STT-Clean is running: its icon is in the menu bar (top right).
  - Allow Accessibility when macOS asks (to type the text), and the Microphone on your first dictation.
  - Right-click the icon: Speech and LLM list the models already on this Mac. No speech model
    yet? See \"Models\" in README.md.
  - Click the icon, speak, click again.
  - Start it at login: System Settings → General → Login Items → + → $PWD/build/STT-Clean.app"
