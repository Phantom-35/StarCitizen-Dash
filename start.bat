@echo off
REM SC-Dash starten und das Dashboard-Fenster (ohne GPU) öffnen.
REM Zusätzliche Optionen einfach anhängen, z. B.:  start.bat --log "D:\StarCitizen\LIVE"
chcp 65001 >nul
cd /d "%~dp0"
title SC-Dash

where py >nul 2>nul
if %errorlevel%==0 (
    py -3 -m scdash --open %*
    goto :end
)
where python >nul 2>nul
if %errorlevel%==0 (
    python -m scdash --open %*
    goto :end
)
echo.
echo  Python 3 wurde nicht gefunden.
echo  Bitte installieren: https://www.python.org/downloads/  (Haken bei "Add python.exe to PATH" setzen)
echo.
:end
pause
