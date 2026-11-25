@echo off
rem Costruisce l'installer Windows: dist\GareDiMate-Setup-<versione>.exe
rem Uso: build_installer.bat [versione]     (es. build_installer.bat 1.1.0)
setlocal
cd /d "%~dp0"

set VERSION=%~1
if "%VERSION%"=="" set VERSION=1.0.0

if exist "venv\Scripts\python.exe" (
    set PYTHON=venv\Scripts\python.exe
) else (
    set PYTHON=py
)

%PYTHON% -m PyInstaller --version >nul 2>&1
if errorlevel 1 (
    echo PyInstaller non trovato. Installarlo con:  %PYTHON% -m pip install pyinstaller
    exit /b 1
)

set ISCC=
if exist "%LOCALAPPDATA%\Programs\Inno Setup 6\ISCC.exe" set ISCC=%LOCALAPPDATA%\Programs\Inno Setup 6\ISCC.exe
if exist "%ProgramFiles(x86)%\Inno Setup 6\ISCC.exe" set ISCC=%ProgramFiles(x86)%\Inno Setup 6\ISCC.exe
if exist "%ProgramFiles%\Inno Setup 6\ISCC.exe" set ISCC=%ProgramFiles%\Inno Setup 6\ISCC.exe
if "%ISCC%"=="" (
    echo Inno Setup 6 non trovato. Installarlo con:  winget install JRSoftware.InnoSetup
    exit /b 1
)

echo [1/2] Creazione dell'eseguibile con PyInstaller...
%PYTHON% -m PyInstaller --noconfirm --clean --distpath dist --workpath build packaging\GareDiMate.spec
if errorlevel 1 exit /b 1

echo [2/2] Creazione dell'installer con Inno Setup...
"%ISCC%" /Q /DAppVersion=%VERSION% packaging\GareDiMate.iss
if errorlevel 1 exit /b 1

echo.
echo Installer pronto: dist\GareDiMate-Setup-%VERSION%.exe
