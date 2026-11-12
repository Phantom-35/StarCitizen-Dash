@echo off
REM SC-Dash starten und das Dashboard-Fenster (ohne GPU) öffnen.
REM Zusätzliche Optionen einfach anhängen, z. B.:  start.bat --log "D:\StarCitizen\LIVE"
REM Mit Windows starten (Fenster öffnet sich dann mit dem Spiel):  start.bat --autostart on
chcp 65001 >nul
cd /d "%~dp0"
title SC-Dash

set "PY="
where py >nul 2>nul && set "PY=py -3"
if not defined PY where python >nul 2>nul && set "PY=python"
if not defined PY goto :nopython

%PY% -m scdash --open %*
REM Fenster nur bei einem Fehler offen lassen (z. B. wenn SC-Dash schon im Hintergrund läuft, ist alles gut)
if errorlevel 1 pause
exit /b

:nopython
echo.
echo  Python 3 wurde nicht gefunden.
echo  Bitte installieren: https://www.python.org/downloads/  (Haken bei "Add python.exe to PATH" setzen)
echo.
pause
