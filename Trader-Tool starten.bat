@echo off
rem Fenster immer offen halten, damit Meldungen lesbar bleiben
if not "%~1"=="run" (
  cmd /k ""%~f0" run"
  exit /b
)
chcp 65001 >nul
set PYTHONUTF8=1
title Trader Tool - Live
cd /d "%~dp0"

if not exist .env (
  copy .env.example .env >nul
  echo Bitte zuerst die Datei .env mit deinen Zugangsdaten ausfuellen - sie wird jetzt geoeffnet.
  notepad .env
  pause
)

set "PY="
rem bewaehrte Python-Versionen bevorzugen (fuer sehr neue gibt es oft noch keine fertigen Pakete)
for %%V in (3.12 3.13 3.11 3.14) do (
  if not defined PY (
    py -%%V --version >nul 2>nul && set "PY=py -%%V"
  )
)
if not defined PY (
  where py >nul 2>nul && (set "PY=py -3") || (set "PY=python")
)
%PY% --version >nul 2>nul
if errorlevel 1 (
  echo.
  echo FEHLER: Python wurde nicht gefunden.
  echo Bitte Python 3.12 von https://www.python.org/downloads/ installieren
  echo und beim Installieren unten "Add python.exe to PATH" anhaken. Danach diese Datei erneut starten.
  goto :eof
)
%PY% --version

if not exist .venv\Scripts\python.exe (
  echo Erster Start: richte Python-Umgebung ein ^(dauert 1-2 Minuten^) ...
  %PY% -m venv .venv
)
if not exist .venv\Scripts\python.exe (
  echo FEHLER: Python-Umgebung konnte nicht angelegt werden.
  goto :eof
)
echo Pruefe/installiere Pakete ...
.venv\Scripts\python -m pip install -q --disable-pip-version-check -r requirements.txt
if errorlevel 1 (
  echo FEHLER bei der Installation der Pakete - siehe Meldung oben.
  echo Tipp: Python 3.12 von https://www.python.org/downloads/release/python-3120/ installieren,
  echo den Ordner .venv loeschen und diese Datei erneut starten.
  goto :eof
)

start "" http://localhost:8080
.venv\Scripts\python live.py
echo.
echo Das Programm wurde beendet. Protokoll: state\live.log
