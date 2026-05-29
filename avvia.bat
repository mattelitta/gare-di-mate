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

echo Server in ascolto su http://0.0.0.0:8000
echo Premi CTRL+C per fermare.
echo.

%PYTHON% -m uvicorn main:app --host 0.0.0.0 --port 8000

rem Per la modalita sviluppo (ricarica automatica), sostituire la riga sopra con:
rem %PYTHON% -m uvicorn main:app --host 0.0.0.0 --port 8000 --reload

echo.
echo Server arrestato.
pause
