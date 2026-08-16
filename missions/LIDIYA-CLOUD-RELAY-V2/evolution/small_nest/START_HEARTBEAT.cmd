@echo off
setlocal
set "SCRIPT_DIR=%~dp0"
set "STATE_PATH=%SCRIPT_DIR%..\..\.lidiya\heartbeat_state.json"
if not exist "%SCRIPT_DIR%heartbeat_agent.py" (
  echo Missing heartbeat_agent.py 1>&2
  exit /b 2
)
python "%SCRIPT_DIR%heartbeat_agent.py" --state "%STATE_PATH%" --interval 300
exit /b %ERRORLEVEL%
