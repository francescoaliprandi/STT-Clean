<img src="assets/LOGO.png" width="320" alt="STT-Clean logo">

# STT-Clean: Live Speech-to-Text with LLM Refinement

![License: MIT](https://img.shields.io/badge/license-MIT-blue)
![macOS 14+, Apple silicon](https://img.shields.io/badge/macOS-14%2B%2C%20Apple%20silicon-lightgrey)
![Windows 10 | 11, x64](https://img.shields.io/badge/Windows-10%20%7C%2011%2C%20x64-lightgrey)
![Python 3.12 | 3.13 | 3.14](https://img.shields.io/badge/python-3.12%20%7C%203.13%20%7C%203.14-blue)

STT-Clean is a macOS menu-bar app that types what you say into any app, at the cursor. While you
speak, a live draft appears as you talk, transcribed on your Mac by Parakeet or Whisper (MLX on
Apple silicon). When you stop, a local LLM in Ollama or LM Studio refines it: it applies spoken
corrections ("scratch that"), punctuation ("comma", "new line"), your glossary's spellings and
translation ("write it in English"), and the clean text replaces the draft. It is a wrapper
around models you already have: it finds them, lists them in its menu, and never downloads one.
Nothing leaves your Mac. On an M4, Parakeet TDT 0.6B v3 transcribes 44 s of speech in 1.2 s, and
`gemma4:12b-mlx` refines a dictation in 0.6–3.3 s.

It also runs on Windows 10 and 11, as an icon in the notification area, with the same menu, the
same models in Windows formats on the CPU, and the same LLM step: see [Windows](#windows).

| You say | Pasted |
|---|---|
| "Send the report to Luca by Friday, actually no, by Thursday." | Send the report to Luca by Thursday. |
| "Caro Marco virgola a capo ti scrivo per confermare la riunione di domani punto" | Caro Marco,<br>ti scrivo per confermare la riunione di domani. |
| "Ho installato o lama e uso il modello emme elle ics per la dettatura." | Ho installato Ollama e uso il modello MLX per la dettatura. *(glossary)* |
| "Domani mando la relazione al professore. Scrivilo in inglese." | I will send the report to the professor tomorrow. |

*Real outputs of `gemma4:12b-mlx` from `tests/bench_llm.py` and `tests/e2e_pipeline.py`.*

## Install

| You need | Check / get it |
|---|---|
| A Mac with Apple silicon (M1 or newer), macOS 14 or newer | Apple menu → About This Mac |
| Apple's command line tools (for `git` and to build the app) | `xcode-select --install` |
| Python 3.12, 3.13 or 3.14 (3.15 is too new for some dependencies yet) | [python.org](https://www.python.org/downloads/macos/) or `brew install python@3.14` |

```bash
git clone https://github.com/riccardoroselli/STT-Clean.git
cd STT-Clean
./install.sh
```

`install.sh` creates a Python environment in `.venv` inside the folder (59 packages, 0.7 GB, no
models), builds `build/STT-Clean.app` and opens it. When it finishes it tells you if a speech model
or an LLM is missing, with the command to get one. To use a Python environment you already have
instead of `.venv`: `STT_CLEAN_PYTHON=/path/to/python ./install.sh`.

The app runs from this folder, so keep it where you cloned it. To update: `git pull`, then
`./install.sh` again.

### First launch

1. **Accessibility:** allow it when macOS asks. STT-Clean needs it to type the text.
2. **Microphone:** allow it on your first dictation.
3. **Speech model:** right-click the icon → **Speech**. If the list is empty, download one (next
   section). The new model shows up the next time you open the menu, no restart needed.
4. **Start at login** (optional): System Settings → General → Login Items → + →
   `build/STT-Clean.app`.

### Windows

| You need | Check / get it |
|---|---|
| Windows 10 or 11, 64-bit | Settings → System → About |
| [Git for Windows](https://git-scm.com/download/win) (for `git clone`) | `git --version` |
| Python 3.12, 3.13 or 3.14 | [python.org](https://www.python.org/downloads/windows/) or `winget install Python.Python.3.14` |

```bat
git clone https://github.com/riccardoroselli/STT-Clean.git
cd STT-Clean
install.cmd
```

`install.cmd` (or a double-click on it) runs `install.ps1`, which creates a Python environment in
`.venv` (29 packages, 0.3 GB, no models), adds **STT-Clean** to the Start menu and starts it. When it
finishes it tells you if a speech model or an LLM is missing, with the command to get one. To use a
Python environment you already have: `set STT_CLEAN_PYTHON=C:\path\to\python.exe` before
`install.cmd`. As on macOS, the app runs from this folder; to update: `git pull`, then `install.cmd`.

First launch: there are no permissions to grant, except the microphone if Windows has it off for
desktop apps (Settings → Privacy & security → Microphone → *Let desktop apps access your
microphone*). The icon may land behind the **^** of the notification area: drag it onto the taskbar.
To start it at login, copy the Start menu shortcut into the folder that `Win+R` → `shell:startup` opens.

## Models

STT-Clean uses the models already on your Mac and checks for new ones every time you open its menu.

| Kind | Found in | Formats | Picked at launch |
|---|---|---|---|
| Speech | The Hugging Face cache: `~/.cache/huggingface/hub`, or `$HF_HOME/hub` if it was set when you ran `install.sh` | Parakeet and Whisper in MLX format (`mlx-community/…`) | Your last pick, else Parakeet TDT 0.6B v3, else the first one found |
| LLM | Every chat model in [Ollama](https://ollama.com) and [LM Studio](https://lmstudio.ai), while they run | Any instruct model | Your last pick, else `gemma4:12b-mlx`, else the first one found |

Download a speech model with the Hugging Face CLI that `install.sh` put in `.venv`:

```bash
.venv/bin/hf download mlx-community/parakeet-tdt-0.6b-v3      # 2.3 GB, 25 European languages, fastest
.venv/bin/hf download mlx-community/whisper-large-v3-turbo    # 1.6 GB, ~100 languages
```

Whisper models in other formats are not found: whisper.cpp or MacWhisper `.bin` files,
faster-whisper, OpenAI `.pt` files, Transformers `openai/whisper-*`. Whisper pads every clip to
30 s, so with large Whisper models the live draft updates less often than with Parakeet.

On Windows the same models run on the CPU, in other formats, found in the same Hugging Face cache
(`%USERPROFILE%\.cache\huggingface\hub`, or `%HF_HOME%\hub`):

| Engine | Format | Download | Re-transcribing a 30 s clip (8-core Ryzen 7 8840HS) |
|---|---|---|---|
| Parakeet TDT 0.6B v3 (default) | ONNX, 8-bit ([onnx-asr](https://github.com/istupakov/onnx-asr)) | `.venv\Scripts\hf download istupakov/parakeet-tdt-0.6b-v3-onnx --include "*.int8.onnx" config.json vocab.txt nemo128.onnx` (0.6 GB) | 0.98 s |
| Whisper large-v3-turbo | CTranslate2 ([faster-whisper](https://github.com/SYSTRAN/faster-whisper)) | `.venv\Scripts\hf download dropbox-dash/faster-whisper-large-v3-turbo` (1.6 GB) | ~16 s |

The 8-bit Parakeet is what makes the live draft work without a GPU; the full-size export
(`encoder-model.onnx*`, 2.5 GB) loads too. Whisper pads every clip to 30 s, which a CPU feels: use
it for the languages Parakeet doesn't cover, with Live text off. For the LLM, LM Studio is the
simplest on Windows: download `google/gemma-4-12b` (7.4 GB) and start its server
(Developer → Start server), or `ollama pull gemma4:12b`. Check another model with
`tests\bench_llm_win.py`.

The LLM is optional; without one you get the raw transcript. For the refinement, install Ollama and
run `ollama pull gemma4:12b-mlx` (7.7 GB, ~8 GB of RAM while loaded), or download a model in LM
Studio. The prompt was tuned on Gemma 4: `gemma4:12b-mlx` passes all 16 cases of
`tests/bench_llm.py`; run it to check another model. Models that answer the text instead of
refining it fail the check run when you pick them, and the previous model stays.

## Usage

| Action | How |
|---|---|
| Dictate | Click the menu-bar icon, speak, click again. A clock shows the recording time. |
| Cancel | Esc while recording: the live text is erased, nothing is pasted. |
| Menu | Right-click the icon. |
| Switch speech model or LLM | Menu → **Speech** or **LLM** → click a model. The one in use is ticked. |
| Smart clean-up (LLM) | Menu switch. Off: raw transcript, and the LLM's memory is freed. |
| Live text while speaking | Menu switch. Off: only the final text is typed. |
| Custom spellings | Menu → **Edit Glossary…** (see [Glossary](#glossary)) |

On Windows the icon is in the notification area: it turns red while recording, with the clock in its
tooltip (the notification area shows no text), and the paste is Ctrl+V. **Ctrl+Win+R** starts and
stops a dictation from the keyboard, like a click, without leaving the app you type in; change it with
`"hotkey"` in `%APPDATA%\STT-Clean\settings.json` (e.g. `"ctrl+alt+d"`, `""` for click only), then
restart the app.

Your choices are remembered. Only one LLM is in memory at a time; it is unloaded when you switch,
turn clean-up off or quit.

Keystrokes only go to the app, window and text field where the dictation started. Switch away and
the typing pauses; come back and it catches up. If you're still away when the dictation ends, the
text goes to the clipboard and the menu says so.

### Voice commands

The LLM follows these in Italian and English:

| Kind | Say | Result |
|---|---|---|
| Self-correction | "scratch that" · "actually no" · "no cancella" · "anzi" | Only the corrected version is kept |
| Punctuation | "comma", "period" · "virgola", "punto", "due punti", "punto interrogativo" | `,` `.` `:` `?` |
| Layout | "new line" / "a capo" · "new paragraph" / "nuovo paragrafo" | Line break / blank line |
| Translation | "… write it in English" · "scrivilo in inglese" · "traduci in inglese" | Whole text translated, instruction removed |
| Partial translation | "solo la prossima frase traducimela in inglese" | Only the next sentence translated |

Questions and requests are pasted as text, not answered.

### Glossary

For names, brands and jargon the speech model gets wrong, open Menu → **Edit Glossary…** and add one
term per line:

```
Ollama: o lama, olama
GitHub: git hub
Kubernetes
```

The variants after the colon are replaced exactly, before the LLM runs. Every term is also given to
the LLM, which fixes close mis-hearings from context. Changes apply from the next dictation.

## How it works

| Step | What happens | Code |
|---|---|---|
| Record | The mic opens on click and closes on stop. Esc is a global hot key only while recording. | `src/menubar.py`, `src/audio.py`, `src/esc_key.py` |
| Live draft | Every ≥0.5 s the whole clip so far is transcribed again. Only words that two consecutive drafts agree on are typed, so the text grows instead of flickering. | `src/stt.py`, `src/live.py` |
| Final pass | The clip is transcribed once more and the glossary's variants are replaced. | `src/stt_clean.py`, `src/cleanup.py` |
| Refinement | The LLM (temperature 0, thinking off) applies the voice commands. On any failure, or an output that looks like an answer, the raw text is used. | `src/cleanup.py` |
| Replace | Only the changed tail of the draft is erased; the rest is pasted with ⌘V. The previous clipboard (text, images, files) is restored once the app has read the paste. | `src/output.py` |

With Parakeet, transcribing the whole clip again takes ~0.25 s at 10 s of audio, ~0.5 s at 30–40 s
and ~0.9 s at 50 s. Parakeet uses ~1.3 GB of RAM; its working cache is freed after each dictation.

On Windows the same steps run in the `_win` modules (`tray_win.py`, `stt_win.py`, `output_win.py`,
`esc_key_win.py`, `stt_clean_win.py`), through the Windows API directly (`win32.py`, no pywin32);
`audio.py`, `live.py` and `cleanup.py` are shared. The paste uses the same trick as on macOS, text
handed over when the app reads it, and hands it only to the app you dictate into: on Windows, WSL's
and Remote Desktop's clipboard sync read every clipboard change at once and would pass for the paste.
Parakeet (8-bit, CPU) re-transcribes a clip in ~0.3 s at 10 s, ~1 s at 30 s and ~1.5 s at 40 s.

`build/STT-Clean.app` is a small compiled launcher (`macos/launcher.c`) that starts the Python app
as a child process, so macOS gives the Microphone and Accessibility permissions to STT-Clean
rather than to Python.

## Privacy

| | |
|---|---|
| **Network** | Only `127.0.0.1`: Ollama (port 11434) and LM Studio (port 1234). The Hugging Face library runs offline (`HF_HUB_OFFLINE=1`), so no model is ever downloaded by the app. |
| **Your voice** | Kept in memory during the dictation, never written to disk (unless you run it from a terminal with `--debug`, see [Development](#development)). |
| **Dictated text** | Typed or pasted into your app, shown in the menu's status line, never written to disk. The clipboard is used for the paste and then restored. |
| **Files it writes** | Menu choices: `~/Library/Preferences/com.riccardoroselli.stt-clean.plist`. Glossary: `config/glossary.txt`. Log of the current run (status and errors, no dictated text): `logs/stt-clean.log`, overwritten at each launch. |
| **On Windows** | Menu choices: `%APPDATA%\STT-Clean\settings.json`; glossary and log as above. If Windows' clipboard history is on (Win+V), each dictation is added to it like anything you copy (and synced to your other PCs if you turned that on); the clipboard restored after the paste is not added again. |

## Troubleshooting

| Problem | Fix |
|---|---|
| `install.sh`: "Needs Python 3.12, 3.13 or 3.14" | Install Python 3.14 (see [Install](#install)) and run `./install.sh` again. |
| The live text or the final text never appears | Turn STT-Clean on in System Settings → Privacy & Security → Accessibility. The menu's status line warns about this. |
| The app does nothing when opened, and the project is on an external drive | Allow STT-Clean in Privacy & Security → Files & Folders → Removable Volumes. |
| "No speech model found" | Download one ([Models](#models)), then pick it in the menu → Speech. |
| "Ollama isn't running" | Open Ollama (or LM Studio), or turn Smart clean-up off. |
| A model "didn't work" | It answered instead of refining, or thought too long. Pick another; `gemma4:12b-mlx` passes all checks. |
| Windows: the icon isn't visible | It's behind the **^** in the notification area: drag it onto the taskbar. |
| Windows: nothing is typed in one app | The app runs as administrator, which blocks keys from normal programs: the text goes to the clipboard and the menu says so. Paste with Ctrl+V, or run that app normally. |
| Windows: "STT-Clean is already running" | Its icon is in the notification area; to restart it, Quit from its menu first. |
| Anything else | Read `logs/stt-clean.log`. |

Every `./install.sh` rebuilds the app, and macOS identifies an unsigned app by its exact contents:
allow Accessibility and the Microphone again after an update.

**Reset or uninstall.** `defaults delete com.riccardoroselli.stt-clean` clears the menu choices.
To uninstall, run it, remove STT-Clean from Login Items if you added it, and delete the folder. Your
models stay where they are. On Windows: Quit it, then delete the Start menu shortcut, the folder and
`%APPDATA%\STT-Clean`.

## Limitations

- Dictation starts and stops with a mouse click; there is no keyboard shortcut, and Esc only cancels.
  (On Windows, Ctrl+Win+R also does it.)
- Secure input fields (passwords, terminals with Secure Keyboard Entry) block typing and pasting.
- Chrome and Electron apps (VS Code) don't report their focused text field, so switching tabs inside
  one of their windows during a dictation isn't detected.
- A clipboard manager that reads the clipboard before the target app counts as the paste, so the
  old clipboard can come back too early.
- The LLM rewrites the whole text: long dictations take ~1 s per 20–25 words. Turn Smart clean-up off
  for raw speed.
- Windows: an app run as administrator blocks the typing (Windows drops keys from normal programs
  there); the text goes to the clipboard instead.
- Windows, on the CPU: past ~30 s of speech the live draft updates about once a second, then slower;
  the final text isn't affected. Whisper is much slower than Parakeet without a GPU.
- Voice commands work as phrased in the prompt (`SYSTEM_PROMPT` in `src/cleanup.py`); there is no
  general voice-command engine.

## Project structure

```
install.sh             One-step install: Python packages in .venv, then the app
src/                   The app (Python, ~1180 lines)
  stt_clean.py         Entry point and worker loop: record → live draft → final → refine → paste
  stt.py               Speech engines (Parakeet, Whisper on MLX); finds the models on this Mac
  menubar.py           Menu-bar icon, menu, Speech/LLM lists, switches, saved choices, status line
  audio.py             Mic stream opened per recording, resampling, sounds
  live.py              Live-draft logic: which words to type, minimal erase/append diff
  output.py            Keystrokes, focus check (app/window/field), clipboard save/restore, ⌘V
  esc_key.py           Esc as a global hot key while recording (no extra permission)
  cleanup.py           LLM client (Ollama, LM Studio), system prompt, glossary, fallbacks
  requirements.txt     Pinned dependencies

  stt_clean_win.py     Windows: entry point and the same worker loop
  stt_win.py           Windows: speech engines (Parakeet on ONNX Runtime, Whisper on CTranslate2)
  tray_win.py          Windows: notification-area icon, menu, saved choices, status line
  output_win.py        Windows: keystrokes, focus check, clipboard save/restore, Ctrl+V
  esc_key_win.py       Windows: Esc as a global hot key while recording
  win32.py             Windows: the Windows API calls, declared with ctypes
  requirements-windows.txt   Pinned dependencies for Windows

install.cmd, install.ps1   Windows one-step install: Python packages in .venv, Start menu shortcut
macos/                 App bundle: build_app.sh, launcher.c, Info.plist, AppIcon.icns, make_icon.py
windows/               AppIcon.ico, tray icons, start/stop/cancel sounds, make_icons.py, make_sounds.py
tests/                 31 unit tests, LLM benchmark, end-to-end and typing checks
assets/                Logo and 1024 px app icon
```

`.venv/`, `build/`, `logs/` and your `config/glossary.txt` are created locally and not tracked.

## Development

```bash
.venv/bin/python src/stt_clean.py --no-paste    # run from a terminal: log there, text printed, not typed
.venv/bin/python -m unittest discover tests     # 31 unit tests: live-draft logic, glossary, LLM servers, engines, settings
.venv/bin/python tests/bench_llm.py [model ...] # 16 dictations through the LLM picked in the menu, exit 1 on a failure
.venv/bin/python tests/e2e_pipeline.py          # macOS `say` → speech model → LLM, no mic
.venv/bin/python tests/typing_check.py          # replays heavy live-draft churn into TextEdit (takes the keyboard ~15 s)
```

`--debug` keeps the last dictation's audio and live drafts in `logs/debug/` to replay it offline.
After changing `SYSTEM_PROMPT` in `src/cleanup.py`, rerun `tests/bench_llm.py`.

On Windows:

```bat
.venv\Scripts\python src\stt_clean_win.py --no-paste
.venv\Scripts\python -m unittest discover tests -p "test_[cw]*.py"
.venv\Scripts\python tests\bench_llm_win.py [model ...]
.venv\Scripts\python tests\e2e_pipeline_win.py
.venv\Scripts\python tests\typing_check_win.py
```

In order: run from a terminal (log there, text printed, not typed); the unit tests that run on
Windows; `bench_llm.py`'s 16 dictations with the Windows app's settings; Windows speech synthesis →
speech model → LLM, no mic; live-draft churn and the paste into Notepad (takes the keyboard ~15 s).
GitHub Actions runs the unit tests on macOS and Windows for every push and pull request
(`.github/workflows/tests.yml`).

## Licence

[MIT](LICENSE). The models are not part of this repo and keep their own licences, e.g.
[Parakeet TDT 0.6B v3](https://huggingface.co/nvidia/parakeet-tdt-0.6b-v3) (NVIDIA, CC-BY-4.0),
[Whisper](https://github.com/openai/whisper) (OpenAI, MIT) and
[Gemma](https://ai.google.dev/gemma/terms) (Google).
