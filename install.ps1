# Installs STT-Clean on Windows in this folder: double-click install.cmd (or run .\install.ps1 in PowerShell)
#   1. a Python environment in .venv with the app's Python packages (~0.6 GB; no models)
#   2. a Start menu shortcut, STT-Clean, and starts the app
# It downloads no model: STT-Clean uses the speech models and LLMs already on this PC.
# Run it again after updating (git pull): it only adds what is missing and restarts the app.
# Use your own Python environment instead of .venv:  $env:STT_CLEAN_PYTHON = "C:\path\to\python.exe"; .\install.ps1
$ErrorActionPreference = "Stop"
Set-Location $PSScriptRoot
function Step($msg) { Write-Host "`n==> $msg" -ForegroundColor Cyan }
function Fail($msg) { Write-Host "x $msg" -ForegroundColor Red; exit 1 }

if (-not [Environment]::Is64BitOperatingSystem) { Fail "STT-Clean needs 64-bit Windows 10 or 11." }

$py = $env:STT_CLEAN_PYTHON
if (-not $py) {
    if (-not (Test-Path .venv\Scripts\python.exe)) {
        # Python 3.12-3.14: every dependency has a ready-made package for them, as on macOS
        $base = $null
        foreach ($v in "3.14", "3.13", "3.12") {
            if ((Get-Command py -ErrorAction SilentlyContinue) -and (& py "-$v" -c "print(1)" 2>$null)) { $base = "py"; $baseArgs = @("-$v"); break }
        }
        if (-not $base -and (Get-Command python -ErrorAction SilentlyContinue)) {
            & python -c "import sys; sys.exit(not (3, 12) <= sys.version_info[:2] <= (3, 14))" 2>$null
            if ($LASTEXITCODE -eq 0) { $base = "python"; $baseArgs = @() }
        }
        if (-not $base) { Fail "Needs Python 3.12, 3.13 or 3.14 (3.15 is too new for some packages yet): install 3.14 from https://www.python.org/downloads/windows/, then run install.cmd again." }
        Step "Creating the Python environment (.venv) with $(& $base @baseArgs --version)"
        & $base @baseArgs -m venv .venv
        if ($LASTEXITCODE -ne 0) { Fail "Couldn't create .venv." }
    }
    $py = "$PSScriptRoot\.venv\Scripts\python.exe"
}
$pyw = Join-Path (Split-Path $py) "pythonw.exe"

Step "Installing the dependencies"
& $py -m pip install --disable-pip-version-check -r src\requirements-windows.txt
if ($LASTEXITCODE -ne 0) { Fail "pip couldn't install the dependencies (see above)." }

Step "Adding STT-Clean to the Start menu"
# quit a running STT-Clean first (it unloads its LLM): its hidden window takes WM_CLOSE like any window
Add-Type -Namespace SttClean -Name User32 -MemberDefinition @'
[DllImport("user32.dll", CharSet = CharSet.Unicode)] public static extern IntPtr FindWindow(string cls, string title);
[DllImport("user32.dll")] public static extern bool PostMessage(IntPtr hWnd, uint msg, IntPtr w, IntPtr l);
'@
$running = [SttClean.User32]::FindWindow("STT-Clean", "STT-Clean")
if ($running -ne [IntPtr]::Zero) {
    [void][SttClean.User32]::PostMessage($running, 0x0010, [IntPtr]::Zero, [IntPtr]::Zero)
    Start-Sleep -Seconds 2
}
$lnk = Join-Path ([Environment]::GetFolderPath("Programs")) "STT-Clean.lnk"
$shortcut = (New-Object -ComObject WScript.Shell).CreateShortcut($lnk)
$shortcut.TargetPath = $pyw                       # pythonw: no console window
$shortcut.Arguments = "`"$PSScriptRoot\src\stt_clean_win.py`""
$shortcut.WorkingDirectory = $PSScriptRoot
$shortcut.IconLocation = "$PSScriptRoot\windows\AppIcon.ico"
$shortcut.Description = "Live speech-to-text with LLM refinement, on this PC"
$shortcut.Save()
Write-Host "Added $lnk (Python: $py)"
Start-Process $lnk

function Found($module) {
    & $py -c "import sys; sys.path.insert(0, 'src'); import $module; sys.exit(not $module.available())" 2>$null
    return $LASTEXITCODE -eq 0
}
Write-Host @"

v STT-Clean is running: its icon is in the notification area (bottom right; behind ^ if hidden,
  drag it onto the taskbar to keep it in sight).
  - Right-click the icon: Speech and LLM list the models already on this PC.
  - Click the icon, speak, click again.
  - Start it at login: Win+R, shell:startup, copy the STT-Clean shortcut from the Start menu there.
"@ -ForegroundColor Green
if (-not (Found "stt_win")) {
    Write-Host @"

! No speech model on this PC yet. Download one (0.6 GB), then pick it in the menu -> Speech:
    $(Split-Path $py)\hf download istupakov/parakeet-tdt-0.6b-v3-onnx --include "*.int8.onnx" config.json vocab.txt nemo128.onnx
  Other models: see "Models" in README.md.
"@ -ForegroundColor Yellow
}
if (-not (Found "cleanup")) {
    Write-Host @"

! No LLM server running, so you get the raw transcript. For the clean-up, install LM Studio
  (https://lmstudio.ai), download google/gemma-4-12b and start its server (or use Ollama: ollama pull gemma4:12b)
"@ -ForegroundColor Yellow
}
