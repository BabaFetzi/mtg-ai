@echo off
REM ============================================================================
REM  start.bat - Grana lokal auf Windows starten (zum Testen)
REM
REM  Einfach DOPPELKLICKEN. Diese Datei macht automatisch:
REM    1. prueft, ob Python und Node.js installiert sind
REM    2. richtet beim ersten Mal alles ein (Python-Umgebung + Pakete)
REM    3. startet das Backend  (in einem eigenen Fenster)
REM    4. startet das Frontend (in einem eigenen Fenster)
REM
REM  Danach im Browser oeffnen:  http://localhost:5175
REM
REM  Diese Datei ist NUR fuer den Windows-PC zum Testen gedacht.
REM  Fuer den echten Linux-Server gibt es stattdessen start.sh .
REM ============================================================================

setlocal
title Grana Starter
cd /d "%~dp0"

echo ============================================
echo    Grana - lokaler Start (zum Testen)
echo ============================================
echo.

REM ---------- 1) Python pruefen ----------
python --version >nul 2>nul
if errorlevel 1 (
  echo [FEHLER] Python wurde nicht gefunden.
  echo.
  echo Bitte Python installieren von:  https://www.python.org/downloads/
  echo WICHTIG: Beim Installieren unten den Haken bei
  echo          "Add Python to PATH" setzen!
  echo.
  pause
  exit /b 1
)

REM ---------- 2) Python-Umgebung + Backend-Pakete ----------
if not exist ".venv\Scripts\python.exe" (
  echo [1/4] Erstelle Python-Umgebung ^(nur beim ersten Mal^)...
  python -m venv .venv
)
echo [2/4] Installiere/aktualisiere Backend-Pakete...
".venv\Scripts\python.exe" -m pip install --quiet --upgrade pip
".venv\Scripts\python.exe" -m pip install --quiet -r requirements.txt
if errorlevel 1 (
  echo [FEHLER] Backend-Pakete konnten nicht installiert werden.
  pause
  exit /b 1
)

REM ---------- 3) Node.js/npm pruefen + Frontend-Pakete ----------
call npm --version >nul 2>nul
if errorlevel 1 (
  echo [FEHLER] Node.js / npm wurde nicht gefunden.
  echo.
  echo Bitte Node.js ^(LTS-Version^) installieren von:  https://nodejs.org/
  echo.
  pause
  exit /b 1
)
if not exist "mtg-frontend\node_modules\" (
  echo [3/4] Installiere Frontend-Pakete ^(nur beim ersten Mal, dauert etwas^)...
  pushd mtg-frontend
  call npm install
  popd
) else (
  echo [3/4] Frontend-Pakete sind schon da.
)

REM ---------- 4) Backend + Frontend in eigenen Fenstern starten ----------
echo [4/4] Starte Backend und Frontend...
start "Grana Backend"  /d "%~dp0" cmd /k ".venv\Scripts\python.exe -m uvicorn main:app --port 8001 --reload"
start "Grana Frontend" /d "%~dp0mtg-frontend" cmd /k "npm run dev"

echo.
echo ============================================
echo    Fertig!
echo.
echo    Oeffne im Browser:   http://localhost:5175
echo ============================================
echo.
echo Es haben sich ZWEI neue Fenster geoeffnet (Backend + Frontend).
echo Lass beide offen, solange du die App benutzt.
echo.
echo Zum STOPPEN: die zwei neuen Fenster schliessen
echo              (oder dort jeweils Strg + C druecken).
echo.
pause
