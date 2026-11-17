@echo off
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

if not exist .venv (
  echo Erster Start: richte Python-Umgebung ein ^(dauert 1-2 Minuten^) ...
  py -3 -m venv .venv 2>nul || python -m venv .venv
  if not exist .venv (
    echo Python wurde nicht gefunden. Bitte Python 3.12 von https://www.python.org/downloads/ installieren
    echo und beim Installieren "Add python.exe to PATH" anhaken.
    pause
    exit /b 1
  )
)
.venv\Scripts\python -m pip install -q --disable-pip-version-check -r requirements.txt

start "" http://localhost:8080
.venv\Scripts\python live.py
pause
