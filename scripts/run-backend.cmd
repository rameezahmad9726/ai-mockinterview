@echo off
cd /d "%~dp0..\backend"
echo Starting Interveux backend on http://localhost:8000
python main.py
pause
