@echo off
rem One-click start for the Bosch Local Workbench.
rem Finds a Python that has the Workbench packages - also inside conda
rem environments, without "conda activate" - remembers it, starts the
rem Workbench and opens the browser. The last workspace is restored.
rem
rem Optional overrides:
rem   set WORKBENCH_PYTHON=C:\path\to\python.exe   (use exactly this Python)
rem   start_workbench.bat --workspace "C:\path\to\folder"
setlocal
cd /d "%~dp0"
title Bosch Local Workbench
set "CHECK=import fastapi, uvicorn, fitz"
set "STATE=%~dp0AI_Bot_State"
set "SAVED=%STATE%\python_path.txt"
set "PY="

echo Looking for a Python environment with the Workbench packages...

rem 1) Explicit choice
if defined WORKBENCH_PYTHON call :try "%WORKBENCH_PYTHON%"
if defined PY goto run

rem 2) The Python found last time
if not exist "%SAVED%" goto venv
set /p REMEMBERED=<"%SAVED%"
call :try "%REMEMBERED%"
if defined PY goto run

:venv
rem 3) A virtual environment next to or above this folder
call :try "%~dp0.venv\Scripts\python.exe"
if defined PY goto run
call :try "%~dp0..\.venv\Scripts\python.exe"
if defined PY goto run

rem 4) Python on PATH (also an already activated conda environment)
for /f "delims=" %%P in ('where python 2^>nul') do if not defined PY call :try "%%~P"
if defined PY goto run

rem 5) Every conda environment that conda has registered for this user
if not exist "%USERPROFILE%\.conda\environments.txt" goto condaroots
for /f "usebackq delims=" %%E in ("%USERPROFILE%\.conda\environments.txt") do if not defined PY call :try "%%~E\python.exe"
if defined PY goto run

:condaroots
rem 6) Usual conda / Anaconda / Miniforge install folders
for %%R in ("%USERPROFILE%\anaconda3" "%USERPROFILE%\miniconda3" "%USERPROFILE%\miniforge3" "%USERPROFILE%\mambaforge" "%LOCALAPPDATA%\anaconda3" "%LOCALAPPDATA%\miniconda3" "%ProgramData%\anaconda3" "%ProgramData%\miniconda3") do if not defined PY call :tryroot "%%~R"
if defined PY goto run

rem 7) py launcher
for /f "delims=" %%P in ('py -3 -c "import sys; print(sys.executable)" 2^>nul') do if not defined PY call :try "%%~P"
if defined PY goto run

goto nopython

:run
for %%D in ("%PY%") do set "PYDIR=%%~dpD"
set "PYDIR=%PYDIR:~0,-1%"
rem A conda environment works without "conda activate" once its DLL folders are on PATH.
if exist "%PYDIR%\conda-meta" set "PATH=%PYDIR%;%PYDIR%\Library\mingw-w64\bin;%PYDIR%\Library\usr\bin;%PYDIR%\Library\bin;%PYDIR%\Scripts;%PATH%"
if not exist "%STATE%" mkdir "%STATE%" >nul 2>nul
> "%SAVED%" echo %PY%
echo Using Python: %PY%
echo The browser opens automatically. Keep this window open; closing it stops the Workbench.
echo.
"%PY%" "%~dp0chat_workbench.py" %*
if errorlevel 1 goto failed
exit /b 0

:failed
echo.
echo The Workbench could not start. See the message above.
pause
exit /b 1

:nopython
echo.
echo No Python environment with the Workbench packages was found.
echo.
echo   A) If you already use an environment, start it once like this from its prompt:
echo        conda activate NAME
echo        "%~f0"
echo      It is remembered for every later double-click.
echo   B) Or let this window create a private environment (.venv) in this folder now
echo      and install the packages from requirements.txt (needs internet access).
echo.
choice /c YN /m "Create .venv and install the packages now"
if errorlevel 2 goto failed
set "BASEPY="
for /f "delims=" %%P in ('py -3 -c "import sys; print(sys.executable)" 2^>nul') do if not defined BASEPY set "BASEPY=%%~P"
if not defined BASEPY for /f "delims=" %%P in ('where python 2^>nul') do if not defined BASEPY call :anypython "%%~P"
if not defined BASEPY (
  echo No Python 3 was found. Install Python 3.10 or newer first, then start again.
  goto failed
)
"%BASEPY%" -m venv "%~dp0.venv" || goto failed
"%~dp0.venv\Scripts\python.exe" -m pip install -r "%~dp0requirements.txt" || goto failed
call :try "%~dp0.venv\Scripts\python.exe"
if defined PY goto run
goto failed

rem ---- helpers ------------------------------------------------------------
:try
rem Accept a python.exe only if it exists and imports the Workbench packages.
if "%~1"=="" exit /b 1
if not exist "%~1" exit /b 1
setlocal
set "CAND=%~1"
for %%D in ("%CAND%") do set "CDIR=%%~dpD"
set "CDIR=%CDIR:~0,-1%"
if exist "%CDIR%\conda-meta" set "PATH=%CDIR%;%CDIR%\Library\mingw-w64\bin;%CDIR%\Library\usr\bin;%CDIR%\Library\bin;%CDIR%\Scripts;%PATH%"
"%CAND%" -c "%CHECK%" >nul 2>nul
if errorlevel 1 (
  endlocal
  exit /b 1
)
endlocal & set "PY=%~1"
exit /b 0

:tryroot
if not exist "%~1" exit /b 1
if exist "%~1\envs" for /d %%E in ("%~1\envs\*") do if not defined PY call :try "%%~E\python.exe"
if not defined PY call :try "%~1\python.exe"
exit /b 0

:anypython
"%~1" -c "import sys; sys.exit(0 if sys.version_info >= (3, 10) else 1)" >nul 2>nul && set "BASEPY=%~1"
exit /b 0
