@echo off
REM SC-Dash auf die neueste Version von GitHub bringen.
REM Notizen, Timer, Verlauf und Ortsgedächtnis bleiben erhalten (sie liegen nicht im Programmordner).
chcp 65001 >nul
if /i not "%~1"=="--run" (
    REM Diese Datei wird beim Update evtl. selbst ersetzt - deshalb läuft eine Kopie aus dem Temp-Ordner.
    copy /y "%~f0" "%TEMP%\scdash-update.bat" >nul
    "%TEMP%\scdash-update.bat" --run "%~dp0."
)
title SC-Dash Update
powershell -NoProfile -ExecutionPolicy Bypass -File "%~2\tools\update.ps1" -Dir "%~2"
echo.
pause
