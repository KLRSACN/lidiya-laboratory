@echo off
setlocal

set ROOT=%~dp0
cd /d "%ROOT%"

if not exist .venv (
  py -m venv .venv
)

call .venv\Scripts\activate.bat
python -m pip install --upgrade pip
pip install -r requirements.txt
playwright install chromium

python relay_mvp.py --db nav_relay_mvp.sqlite3 register WINDOW-00 COORDINATOR 9222 "[LIDIYA:WINDOW-00]"
python relay_mvp.py --db nav_relay_mvp.sqlite3 register WINDOW-01 BUILDER 9223 "[LIDIYA:WINDOW-01]"
python relay_mvp.py --db nav_relay_mvp.sqlite3 register WINDOW-02 REVIEWER 9224 "[LIDIYA:WINDOW-02]"

start "NAV Relay Scheduler" cmd /k python relay_mvp.py --db nav_relay_mvp.sqlite3 scheduler --interval 5
start "NAV Browser Adapter" cmd /k python navigator_adapter.py --db nav_relay_mvp.sqlite3 --mission-id NAV-RELAY-MVP-0001 --interval 5 WINDOW-00 WINDOW-01 WINDOW-02

echo.
echo Relay and Navigator started.
echo Keep the Chrome windows on ports 9222, 9223 and 9224 open.
pause
