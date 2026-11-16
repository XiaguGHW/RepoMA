@echo off
REM Prueft, ob conda und Git noch installiert sind und ob sie im PATH stehen.
REM Ausgabe erscheint im Fenster und wird zusaetzlich in env_check_log.txt (gleicher Ordner) gespeichert.
REM Hinweis: Wegen Bosch AppLocker nicht aus "Downloads" starten (z. B. Desktop verwenden).

setlocal
set "LOG=%~dp0env_check_log.txt"
call :checks > "%LOG%" 2>&1
type "%LOG%"
echo.
echo Log gespeichert: %LOG%
pause
exit /b

:checks
echo ===== env check %DATE% %TIME% =====
echo.
echo --- Git ---
dir "C:\Program Files\Git\cmd\git.exe"
dir "%LOCALAPPDATA%\Programs\Git\cmd\git.exe"
echo.
echo --- conda: moegliche Installationsorte ---
dir "C:\Program Files\Anaconda3\Scripts\conda.exe"
dir "C:\Program Files\Anaconda3\condabin"
dir "%USERPROFILE%\anaconda3\Scripts\conda.exe"
dir "%USERPROFILE%\miniconda3\Scripts\conda.exe"
dir "C:\ProgramData\anaconda3\Scripts\conda.exe"
dir "C:\ProgramData\miniconda3\Scripts\conda.exe"
dir "%LOCALAPPDATA%\anaconda3\Scripts\conda.exe"
dir "%LOCALAPPDATA%\miniconda3\Scripts\conda.exe"
echo.
echo --- conda-Umgebungen (thesis?) ---
dir "%USERPROFILE%\.conda\envs"
dir "%USERPROFILE%\anaconda3\envs"
dir "%USERPROFILE%\miniconda3\envs"
echo.
echo --- where ---
where git
where conda
echo.
echo --- PATH ---
echo "%PATH%"
exit /b
