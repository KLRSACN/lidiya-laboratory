@echo off
setlocal
set "ROOT=%~dp0..\.."
py -3 "%ROOT%\evolution\local_command_tower\local_canary.py" --workspace-root "%ROOT%" --execute-windows
if errorlevel 1 python "%ROOT%\evolution\local_command_tower\local_canary.py" --workspace-root "%ROOT%" --execute-windows
endlocal
