#!/bin/bash
# Double-click me to start the Dyad pipeline app in your browser.
cd "$(dirname "$0")"

show_error () {  # $1 = title, $2 = advice; shows a friendly page in the browser
  cat > setup_error.html << HTML
<!doctype html><meta charset="utf-8"><title>Dyad app - setup problem</title>
<body style="font-family:-apple-system,Segoe UI,sans-serif;background:#f6f7f9;
display:flex;justify-content:center;padding-top:8vh">
<div style="max-width:560px;background:#fff;border-radius:14px;padding:36px 42px;
box-shadow:0 4px 24px rgba(0,0,0,.08)">
<h2 style="color:#c0392b;margin-top:0">⚠️ $1</h2>
<p style="font-size:15px;line-height:1.6">$2</p>
<p style="font-size:13px;color:#777">Details were saved to
<code>Scripts/setup_error.log</code> - please attach that file to an issue
on the project repository.</p>
</div></body>
HTML
  open setup_error.html
  exit 1
}

if [ ! -x "venv/bin/streamlit" ]; then
  echo "First run - setting up the pipeline (this can take 5-10 minutes)..."
  command -v python3 >/dev/null 2>&1 || show_error "Python 3 was not found" \
    "This app needs Python 3. On a Mac, macOS will usually offer to install it \
automatically the first time - accept and then double-click Start Dyad App again."
  python3 -m venv venv > setup_error.log 2>&1 || show_error \
    "The setup could not create its environment" \
    "Something prevented the initial setup. Try double-clicking Start Dyad App \
again; if it keeps failing, attach the log file below to an issue on the \
project repository."
  ./venv/bin/pip install -r requirements_asr.txt > setup_error.log 2>&1 || show_error \
    "The libraries could not be installed" \
    "This is almost always an internet connection issue. Check that you are \
online (the first setup needs to download the analysis libraries) and \
double-click Start Dyad App again."
  rm -f setup_error.log setup_error.html
fi
echo "Starting the app... your browser will open in a few seconds."
echo "(Keep this window open while you work; close it to stop the app.)"
( sleep 4; open "http://localhost:8501" ) &
./venv/bin/streamlit run app_streamlit.py --server.maxUploadSize 4096 --server.headless true --server.address localhost --server.port 8501 --browser.gatherUsageStats false
