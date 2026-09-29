@echo off
REM Double-click me to start the Dyad pipeline app in your browser.
cd /d "%~dp0"
if not exist "venv\Scripts\streamlit.exe" (
  echo First run - setting up the pipeline ^(this can take 5-10 minutes^)...
  py -m venv venv > setup_error.log 2>&1 || goto :pyerror
  venv\Scripts\pip install -r requirements_asr.txt > setup_error.log 2>&1 || goto :piperror
  del setup_error.log 2>nul
)
echo Starting the app... your browser will open in a few seconds.
echo (Keep this window open while you work; close it to stop the app.)
start "" cmd /c "timeout /t 4 >nul & start "" http://localhost:8501"
venv\Scripts\streamlit run app_streamlit.py --server.maxUploadSize 4096 --server.headless true --server.address localhost --server.port 8501 --browser.gatherUsageStats false
exit /b 0

:pyerror
call :showerror "Python 3 was not found" "This app needs Python 3. Install it from python.org (tick 'Add Python to PATH') and double-click Start Dyad App again."
exit /b 1
:piperror
call :showerror "The libraries could not be installed" "This is almost always an internet connection issue. Check that you are online and double-click Start Dyad App again."
exit /b 1
:showerror
(
echo ^<!doctype html^>^<meta charset="utf-8"^>^<title^>Dyad app - setup problem^</title^>
echo ^<body style="font-family:Segoe UI,sans-serif;background:#f6f7f9;display:flex;justify-content:center;padding-top:8vh"^>
echo ^<div style="max-width:560px;background:#fff;border-radius:14px;padding:36px 42px;box-shadow:0 4px 24px rgba(0,0,0,.08)"^>
echo ^<h2 style="color:#c0392b;margin-top:0"^>%~1^</h2^>
echo ^<p style="font-size:15px;line-height:1.6"^>%~2^</p^>
echo ^<p style="font-size:13px;color:#777"^>Details were saved to Scripts\setup_error.log - please attach it to an issue on the project repository.^</p^>
echo ^</div^>^</body^>
) > setup_error.html
start "" setup_error.html
exit /b 0
