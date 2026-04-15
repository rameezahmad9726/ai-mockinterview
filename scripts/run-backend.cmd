@echo off
cd /d "%~dp0..\backend"
set "VENV_PY=%~dp0..\ai-mockenv\Scripts\python.exe"
if exist "%VENV_PY%" (
  echo Using venv: ai-mockenv
  echo Starting Interveux backend on http://localhost:8000
  "%VENV_PY%" main.py
) else (
  echo ai-mockenv not found at %~dp0..\ai-mockenv — using system python
  echo Starting Interveux backend on http://localhost:8000
  python main.py
)
pause
