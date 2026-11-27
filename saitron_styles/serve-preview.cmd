@echo off
rem Serves this folder on http://127.0.0.1:8766 and opens both panel previews. Close this window to stop.
cd /d "%~dp0"
start "" "http://127.0.0.1:8766/static/preview/certs.html?theme=dark&look=modern"
start "" "http://127.0.0.1:8766/static/preview/urls.html?theme=dark&look=modern"
python -m http.server 8766 --bind 127.0.0.1
