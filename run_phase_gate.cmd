@echo off
setlocal

cd /d "%~dp0"

set "VENV_PY=%~dp0.venv\Scripts\python.exe"
if not exist "%VENV_PY%" (
  echo [ERROR] .venv not found at "%~dp0.venv"
  exit /b 1
)

set "PHASE=%~1"
if "%PHASE%"=="" set "PHASE=all"

echo [INFO] Running phase gate check for: %PHASE%
"%VENV_PY%" ml\evaluation\check_phase_gates.py --phase %PHASE%
exit /b %ERRORLEVEL%

