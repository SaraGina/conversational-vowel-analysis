@echo off
REM Windows version of run_dyad. Usage:  run_dyad.bat my_dyad.yaml
REM One-time setup (in this Scripts folder):
REM   py -m venv venv
REM   venv\Scripts\pip install -r requirements_asr.txt
cd /d "%~dp0"
if not exist "venv\Scripts\python.exe" (
  echo venv not found - run the Installation step in the README first
  exit /b 1
)
"venv\Scripts\python.exe" -m pipeline.run %*
