@echo off
setlocal

cd /d "%~dp0"

set "VENV_PY=%~dp0.venv\Scripts\python.exe"
if not exist "%VENV_PY%" (
  echo [ERROR] .venv not found at "%~dp0.venv"
  echo Create it first, then install dependencies.
  exit /b 1
)

set "DATA_PATH=%~1"
if "%DATA_PATH%"=="" set "DATA_PATH=data\processed\interview_segments_v1.parquet"

echo [INFO] Using python: %VENV_PY%
echo [INFO] Using dataset: %DATA_PATH%

if not exist "%DATA_PATH%" (
  echo [ERROR] Dataset not found: %DATA_PATH%
  echo Provide a path as first arg, e.g.:
  echo   run_ml.cmd data\processed\my_dataset.parquet
  exit /b 1
)

echo [STEP] Training behavior model...
"%VENV_PY%" ml\pipelines\train_behavior.py --data "%DATA_PATH%"
if errorlevel 1 (
  echo [ERROR] Behavior model training failed.
  exit /b 1
)

echo [STEP] Training speech model...
"%VENV_PY%" ml\pipelines\train_speech.py --data "%DATA_PATH%"
if errorlevel 1 (
  echo [ERROR] Speech model training failed.
  exit /b 1
)

echo [STEP] Running evaluation summary...
"%VENV_PY%" ml\evaluation\evaluate_models.py
if errorlevel 1 (
  echo [ERROR] Evaluation step failed.
  exit /b 1
)

echo [DONE] ML training pipeline completed successfully.
echo [INFO] Output report: artifacts\model_eval_latest.json
exit /b 0

