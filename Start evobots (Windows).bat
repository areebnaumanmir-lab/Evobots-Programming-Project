@echo off
rem One-click start for Windows: installs uv the first time (needs internet once), then
rem opens evobots in your browser. Close this window to stop the app.
cd /d "%~dp0"
where uv >nul 2>nul
if errorlevel 1 (
  echo Installing uv, the Python package manager evobots uses (first run only) ...
  powershell -ExecutionPolicy ByPass -c "irm https://astral.sh/uv/install.ps1 | iex"
  set "PATH=%USERPROFILE%\.local\bin;%PATH%"
)
uv run evobots serve
pause
