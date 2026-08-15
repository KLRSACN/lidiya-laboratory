@echo off
setlocal
set "SUBJECT=%~1"
set "OBSERVER=%~2"
set "QUESTIONS=%~3"
set "ROUNDS=%~4"

if "%SUBJECT%"=="" (
  echo Usage: RUN_SMALL_WORLD.cmd SUBJECT_MODEL [OBSERVER_MODEL] [QUESTIONS] [ROUNDS]
  echo Example: RUN_SMALL_WORLD.cmd my-model observer-model 100 1
  exit /b 2
)
if "%OBSERVER%"=="" set "OBSERVER=%SUBJECT%"
if "%QUESTIONS%"=="" set "QUESTIONS=100"
if "%ROUNDS%"=="" set "ROUNDS=1"

set "HERE=%~dp0"
set "OUT=%HERE%..\..\.lidiya\text_world\latest"

where py >nul 2>nul
if %errorlevel%==0 (
  py -3 "%HERE%small_world.py" --subject-model "%SUBJECT%" --observer-model "%OBSERVER%" --questions %QUESTIONS% --rounds %ROUNDS% --output "%OUT%"
) else (
  python "%HERE%small_world.py" --subject-model "%SUBJECT%" --observer-model "%OBSERVER%" --questions %QUESTIONS% --rounds %ROUNDS% --output "%OUT%"
)

if errorlevel 1 exit /b %errorlevel%
echo.
echo Small World experiment complete.
echo Report: %OUT%\experiment_report.json
echo Candidates: %OUT%\training_candidates.jsonl
endlocal
