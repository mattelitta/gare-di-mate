@echo off
title Gare di Mate — Server
cd /d "%~dp0"

echo ============================================
echo  Gare di Mate -- Server
echo ============================================
echo.

rem Usa il venv locale se esiste, altrimenti il Python di sistema
if exist "venv\Scripts\python.exe" (
    echo Ambiente virtuale rilevato.
    echo.
    set PYTHON=venv\Scripts\python.exe
) else (
    set PYTHON=py
)

echo Questo computer:     http://localhost:8000
echo Altri dispositivi:   https://IP-DEL-COMPUTER:8443  (avviso del certificato da accettare)
echo Premi CTRL+C per fermare.
echo.

%PYTHON% server.py

echo.
echo Server arrestato.
pause
