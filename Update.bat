@echo off
rem Holt die neueste Version von GitHub. .env, .venv und die Daten bleiben erhalten.
if not "%~1"=="run" (
  cmd /k ""%~f0" run"
  exit /b
)
chcp 65001 >nul
cd /d "%~dp0"
echo Lade neueste Version von GitHub ...
set "TMPD=%TEMP%\trader-tool-update"
if exist "%TMPD%" rmdir /s /q "%TMPD%"
mkdir "%TMPD%"
powershell -NoProfile -Command "Invoke-WebRequest -UseBasicParsing https://github.com/olegspitsov1990-create/trader-tool/archive/refs/heads/main.zip -OutFile \"$env:TMPD\update.zip\"; Expand-Archive -Force \"$env:TMPD\update.zip\" \"$env:TMPD\""
if not exist "%TMPD%\trader-tool-main\live.py" (
  echo FEHLER: Download fehlgeschlagen.
  goto :eof
)
robocopy "%TMPD%\trader-tool-main" "%CD%" /E /NFL /NDL /NJH /NJS /NP /XD .venv state data /XF .env >nul
rmdir /s /q "%TMPD%"
echo.
echo Update fertig. Jetzt das Trader-Tool-Fenster schliessen und "Trader-Tool starten.bat" neu starten.
