@echo off
REM SC-Dash im Demo-Modus (simulierte Ereignisse, Spiel muss nicht laufen).
chcp 65001 >nul
cd /d "%~dp0"
call start.bat --demo %*
