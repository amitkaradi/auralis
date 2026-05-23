@echo off
REM One-click push to GitHub. Idempotent — safe to re-run.
REM   - Initializes the repo on first run
REM   - Stages any local changes
REM   - Commits with a timestamped message if there's anything new
REM   - Pushes to origin/main; opens a browser sign-in if needed.

setlocal enabledelayedexpansion
cd /d "%~dp0"

set "REPO_URL=https://github.com/amitkaradi/auralis-.git"

echo ============================================================
echo  Pushing Auralis to GitHub
echo  Repo: %REPO_URL%
echo ============================================================
echo.

REM --- 1. Ensure git is installed ---
where git >nul 2>nul
if errorlevel 1 (
    echo [!] git not found on PATH.
    echo     Install Git for Windows: https://git-scm.com/download/win
    pause
    exit /b 1
)

REM --- 2. Initialize repo on first run ---
if not exist ".git" (
    echo Initializing new git repo on branch 'main'...
    git init -b main >nul 2>&1
    if errorlevel 1 (
        REM Older Git versions don't support -b; fall back to rename.
        git init >nul
        git branch -M main
    )
)

REM --- 3. Make sure origin points to the right URL ---
git remote remove origin >nul 2>&1
git remote add origin "%REPO_URL%"

REM --- 4. Stage every file that's not in .gitignore ---
echo Staging files (respecting .gitignore)...
git add -A

REM --- 5. Show the user what's about to ship ---
echo.
echo === Files staged for this commit ===
git diff --cached --name-only

REM --- 6. Commit if anything is staged ---
git diff --cached --quiet
if errorlevel 1 (
    echo.
    echo Creating commit...
    set "STAMP=%DATE% %TIME%"
    git commit -m "Auralis update — !STAMP!"
    if errorlevel 1 (
        echo [!] Commit failed. See git output above.
        pause
        exit /b 1
    )
) else (
    echo.
    echo (Nothing new to commit. Will still push any unpushed commits.)
)

REM --- 7. Push ---
echo.
echo Pushing to %REPO_URL% ...
echo (A browser window may pop up the first time to sign in to GitHub.)
git push -u origin main
if errorlevel 1 (
    echo.
    echo [!] Push failed. Common causes:
    echo     - You closed the GitHub sign-in window. Re-run this file.
    echo     - The remote has commits you don't — run: git pull --rebase origin main
    echo     - First-time setup: you may need to create the repo on github.com first
    echo       at %REPO_URL%
    pause
    exit /b 1
)

echo.
echo ============================================================
echo  DONE. Repo is now on GitHub:
echo  %REPO_URL%
echo ============================================================
pause
exit /b 0
