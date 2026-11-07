@echo off
setlocal
rem One-click start for Windows: installs uv the first time (needs internet once), then
rem opens evobots in your browser. Close this window to stop the app.
rem No parentheses in echo lines or blocks: cmd reads a ")" there as the end of a block.
cd /d "%~dp0"

if exist "pyproject.toml" goto find_uv
echo This file must be run from the unzipped evobots folder.
echo Right-click the downloaded zip, choose "Extract All", then run it from that folder.
goto end

:find_uv
where uv >nul 2>nul
if not errorlevel 1 goto run
if exist "%USERPROFILE%\.local\bin\uv.exe" goto add_path
echo Installing uv, the Python package manager evobots uses - first run only ...
powershell -NoProfile -ExecutionPolicy ByPass -Command "irm https://astral.sh/uv/install.ps1 | iex"
:add_path
set "PATH=%USERPROFILE%\.local\bin;%PATH%"
where uv >nul 2>nul
if not errorlevel 1 goto run
echo.
echo uv could not be installed. Install it from https://docs.astral.sh/uv/ and run this file again.
goto end

:run
echo Starting evobots. The first start downloads Python and the packages - a few minutes.
echo Your browser opens when it is ready. Keep this window open; close it to stop evobots.
uv run evobots serve
if not errorlevel 1 goto end
echo.
echo evobots stopped with an error - the messages above say why.

:end
echo.
pause
