@echo off
REM Auralis — first-run setup + launch.
REM Creates a .venv, installs deps, launches the app.

setlocal
cd /d "%~dp0"

echo ============================================================
echo  Auralis  -  setup + launch
echo ============================================================
echo Running from: %CD%
echo.

REM Pick a Python interpreter (py launcher preferred)
set "PY="
where py >nul 2>nul
if not errorlevel 1 (set "PY=py -3" & goto :have_py)
where python >nul 2>nul
if not errorlevel 1 (set "PY=python" & goto :have_py)
where python3 >nul 2>nul
if not errorlevel 1 (set "PY=python3" & goto :have_py)

echo [!] No Python found on PATH.
echo     Install Python 3.12 from https://www.python.org/downloads/windows/
echo     During the installer, tick "Add python.exe to PATH".
pause & exit /b 1

:have_py
echo Using interpreter: %PY%
%PY% --version
echo.

if exist .venv goto :venv_ready

echo Creating virtual environment in .venv ...
%PY% -m venv .venv
if errorlevel 1 (
    echo [!] venv creation failed. Move the folder to a short path (e.g. C:\Auralis\) and try again.
    pause & exit /b 1
)

:venv_ready
call .venv\Scripts\activate.bat || (echo [!] activation failed & pause & exit /b 1)

echo Installing/updating dependencies...
python -m pip install --upgrade pip
python -m pip install -r requirements.txt
if errorlevel 1 (
    echo [!] pip install failed. If wheels are missing for your Python, install Python 3.12.
    pause & exit /b 1
)

echo.
echo ============================================================
echo  Launching Auralis...
echo ============================================================
python auralis.py

echo.
echo App closed. Press any key to exit.
pause
exit /b 0
