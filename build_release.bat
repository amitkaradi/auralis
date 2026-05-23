@echo off
REM Build BOTH Auralis installers from a single run:
REM   Pass 1: LITE  -> dist\AuralisSetup-1.1.1-lite.exe (~68 MB, no model)
REM   Pass 2: FULL  -> dist\AuralisSetup-1.1.1.exe      (~1.6 GB, model bundled)
REM
REM Prereqs:
REM   1. .venv exists       (run setup_and_run.bat once first)
REM   2. Inno Setup 6       (free, https://jrsoftware.org/isdl.php)
REM
REM Tips:
REM   FORCE_REBUNDLE_MODEL=1  re-fetches the Ivrit.AI model even if cached.
REM   ONLY_LITE=1             skip pass 2 (much faster — only build the lite installer).
REM   ONLY_FULL=1             skip pass 1 (only build the full installer).

setlocal
cd /d "%~dp0"

echo ============================================================
echo  Auralis  -  building release installers (lite + full)
echo ============================================================

call .venv\Scripts\activate.bat || (
    echo [!] No .venv yet. Run setup_and_run.bat once first.
    pause & exit /b 1
)

echo Installing build deps (pyinstaller + pillow + huggingface_hub) ...
python -m pip install --upgrade pyinstaller pillow huggingface_hub >nul

echo.
echo === Generating icons (assets\auralis.ico + Store tiles) ===
python build_icons.py
echo.

REM ---------------------------------------------------------------------
REM Locate Inno Setup compiler (ISCC.exe) up-front so we fail fast.
REM ---------------------------------------------------------------------
echo === Locating Inno Setup compiler (ISCC.exe) ===
set "ISCC="
for %%P in (
    "%ProgramFiles(x86)%\Inno Setup 6\ISCC.exe"
    "%ProgramFiles%\Inno Setup 6\ISCC.exe"
    "%LOCALAPPDATA%\Programs\Inno Setup 6\ISCC.exe"
    "%ProgramFiles(x86)%\Inno Setup 5\ISCC.exe"
    "%ProgramFiles%\Inno Setup 5\ISCC.exe"
) do (
    if exist %%P set "ISCC=%%~P"
)
if not defined ISCC (
    for /f "delims=" %%P in ('where ISCC 2^>nul') do (
        set "ISCC=%%P"
        goto :found_iscc
    )
)
:found_iscc
if not defined ISCC (
    for /f "tokens=2*" %%a in (
        'reg query "HKLM\SOFTWARE\Microsoft\Windows\CurrentVersion\Uninstall\Inno Setup 6_is1" /v "InstallLocation" 2^>nul ^| find "InstallLocation"'
    ) do (
        if exist "%%~b\ISCC.exe" set "ISCC=%%~b\ISCC.exe"
    )
)
if not defined ISCC (
    for /f "tokens=2*" %%a in (
        'reg query "HKCU\SOFTWARE\Microsoft\Windows\CurrentVersion\Uninstall\Inno Setup 6_is1" /v "InstallLocation" 2^>nul ^| find "InstallLocation"'
    ) do (
        if exist "%%~b\ISCC.exe" set "ISCC=%%~b\ISCC.exe"
    )
)
if not defined ISCC (
    echo [!] Inno Setup compiler ISCC.exe not found.
    echo     Install from https://jrsoftware.org/isdl.php then re-run.
    pause & exit /b 1
)
echo Using ISCC: %ISCC%
echo.

REM ---------------------------------------------------------------------
REM PASS 1: Standard installer (no bundled model, model downloaded in-app).
REM ---------------------------------------------------------------------
if "%ONLY_FULL%"=="1" goto :skip_lite

echo ============================================================
echo  Building AuralisSetup-1.1.1.exe (standard installer)
echo  Model downloads on first launch via the in-app picker.
echo ============================================================

if exist bundled_models (
    echo === Temporarily moving bundled_models\ aside for lite build ===
    if exist bundled_models.parked rmdir /s /q bundled_models.parked
    move bundled_models bundled_models.parked >nul
)
echo.

echo === Cleaning previous PyInstaller output ===
if exist build rmdir /s /q build
if exist dist\Auralis rmdir /s /q dist\Auralis
echo.

echo === PyInstaller (lite) ===
pyinstaller --noconfirm --clean auralis.spec
if errorlevel 1 (
    echo [!] PyInstaller failed on lite build.
    if exist bundled_models.parked move bundled_models.parked bundled_models >nul
    pause & exit /b 1
)
echo.

echo === Inno Setup -^> AuralisSetup-1.1.1.exe ===
"%ISCC%" auralis.iss
if errorlevel 1 (
    echo [!] Inno Setup failed on lite build.
    if exist bundled_models.parked move bundled_models.parked bundled_models >nul
    pause & exit /b 1
)
echo.

REM Restore the parked bundle, if we parked one.
if exist bundled_models.parked (
    echo === Restoring bundled_models\ for pass 2 ===
    move bundled_models.parked bundled_models >nul
)

:skip_lite
REM Default: skip the full (bundled-model) pass. The Hugging Face downloader
REM needs Windows Developer Mode / admin to create symlinks, which most
REM dev machines don't have. Opt in with BUILD_FULL=1 if you have it set up.
if not "%BUILD_FULL%"=="1" goto :done
if "%ONLY_LITE%"=="1" goto :done

REM ---------------------------------------------------------------------
REM PASS 2: FULL installer (Ivrit.AI v3 turbo bundled).
REM ---------------------------------------------------------------------
echo ============================================================
echo  Pass 2 of 2  -  FULL installer (Ivrit.AI v3 turbo bundled)
echo ============================================================

if "%FORCE_REBUNDLE_MODEL%"=="1" (
    echo === Forcing fresh model download ===
    if exist bundled_models rmdir /s /q bundled_models
)

REM Defensive cleanup: drop any stale models--* subdirs that aren't the one
REM we're shipping (e.g. test leftovers, or models the user downloaded into
REM the bundle by mistake). Keeps the installer tight and predictable.
if exist bundled_models\hub (
    echo === Pruning unexpected entries from bundled_models\hub\ ===
    for /d %%D in (bundled_models\hub\models--*) do (
        if /i not "%%~nxD"=="models--ivrit-ai--whisper-large-v3-turbo-ct2" (
            echo     removing %%D
            rmdir /s /q "%%D"
        )
    )
)

if not exist "bundled_models\hub\models--ivrit-ai--whisper-large-v3-turbo-ct2" (
    echo === Downloading Ivrit.AI v3 turbo from Hugging Face (~1.5 GB) ===
    python -c "from huggingface_hub import snapshot_download; import os; os.makedirs('bundled_models/hub', exist_ok=True); snapshot_download(repo_id='ivrit-ai/whisper-large-v3-turbo-ct2', cache_dir='bundled_models/hub', allow_patterns=['*.bin','*.json','*.txt','*.model','*.vocab','*.tiktoken','*.spm'])"
    if errorlevel 1 (
        echo [!] Failed to fetch Ivrit.AI v3 turbo model.
        pause & exit /b 1
    )
) else (
    echo === Model already bundled, reusing cache ===
)
echo.

echo === Cleaning previous PyInstaller output ===
if exist build rmdir /s /q build
if exist dist\Auralis rmdir /s /q dist\Auralis
echo.

echo === PyInstaller (full) ===
pyinstaller --noconfirm --clean auralis.spec
if errorlevel 1 (echo [!] PyInstaller failed on full build. & pause & exit /b 1)
echo.

echo === Inno Setup -^> AuralisSetup-1.1.1.exe ===
"%ISCC%" auralis.iss
if errorlevel 1 (echo [!] Inno Setup failed on full build. & pause & exit /b 1)
echo.

:done
echo ============================================================
echo  Build complete.
if exist "dist\AuralisSetup-1.1.1-lite.exe" echo    Lite installer:  dist\AuralisSetup-1.1.1-lite.exe
if exist "dist\AuralisSetup-1.1.1.exe"      echo    Full installer:  dist\AuralisSetup-1.1.1.exe
echo    Standalone app:  dist\Auralis\Auralis.exe
echo ============================================================
pause
exit /b 0
