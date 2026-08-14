@echo off
setlocal
powershell.exe -NoLogo -NoProfile -NonInteractive -File "%~dp0bootstrap_windows.ps1"
endlocal
