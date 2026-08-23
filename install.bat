@echo off
setlocal
echo ductgen setup
echo -------------

where py >nul 2>nul
if %errorlevel%==0 ( set PY=py ) else ( set PY=python )

%PY% --version >nul 2>nul
if errorlevel 1 (
  echo.
  echo Python was not found. Install Python 3.10 or newer from python.org
  echo and tick "Add python.exe to PATH", then run this again.
  pause
  exit /b 1
)

echo Installing dependencies...
%PY% -m pip install --upgrade pip >nul
%PY% -m pip install -r "%~dp0requirements.txt"
if errorlevel 1 (
  echo.
  echo Dependency install failed. See the messages above.
  pause
  exit /b 1
)

echo.
echo Done. Start it with either of these:
echo   - double-click ductgen-gui.pyw
echo   - %PY% -m ductgen preview -p presets\13in_a1.json
echo.
echo To put a button inside SolidWorks, see macro\README.md
pause
