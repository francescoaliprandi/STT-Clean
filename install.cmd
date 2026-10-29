@echo off
rem Double-click to install STT-Clean on Windows: runs install.ps1 (a .ps1 doesn't run on double-click).
powershell -NoProfile -ExecutionPolicy Bypass -File "%~dp0install.ps1" %*
pause
