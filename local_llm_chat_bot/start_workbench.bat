@echo off
rem One-click start: starts the local Workbench and opens it in the browser.
rem The last workspace, model and language are restored automatically.
rem Optional: add  --workspace "C:\path\to\folder"  to a shortcut to always open that folder.
setlocal
cd /d "%~dp0"
title Bosch Local Workbench
echo Bosch Local Workbench is starting; the browser opens automatically.
echo Keep this window open. Closing it stops the Workbench.
echo.
if exist "%~dp0.venv\Scripts\python.exe" (
  "%~dp0.venv\Scripts\python.exe" "%~dp0chat_workbench.py" %*
  goto done
)
if exist "%~dp0..\.venv\Scripts\python.exe" (
  "%~dp0..\.venv\Scripts\python.exe" "%~dp0chat_workbench.py" %*
  goto done
)
where python >nul 2>nul
if not errorlevel 1 (
  python "%~dp0chat_workbench.py" %*
  goto done
)
py -3 "%~dp0chat_workbench.py" %*
:done
if errorlevel 1 (
  echo.
  echo The Workbench could not start. See the message above.
  pause
)
