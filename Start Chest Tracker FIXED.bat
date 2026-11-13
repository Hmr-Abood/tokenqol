@echo off
setlocal
cd /d "%~dp0"
title Chest Tracker - Startup

set "APP=%~dp0chest_tracker_fixed.py"

if not exist "%APP%" (
    echo ERROR: chest_tracker_fixed.py was not found.
    pause
    exit /b 1
)

for /F %%a in ('echo prompt $E ^| cmd') do set "ESC=%%a"

echo %ESC%[96m==============================================================================%ESC%[0m
echo %ESC%[96m                 FORTNITE CHEST TRACKER - MADE BY:%ESC%[0m
echo %ESC%[93m _   _ __  __ ____           _    ____   ___   ___  ____  %ESC%[0m
echo %ESC%[93m^| ^| ^| ^|  \/  ^|  _ \         / \  ^| __ ) / _ \ / _ \^|  _ \ %ESC%[0m
echo %ESC%[93m^| ^|_^| ^| ^|\/^| ^| ^|_) ^|       / _ \ ^|  _ \^| ^| ^| ^| ^| ^| ^| ^| ^| ^|%ESC%[0m
echo %ESC%[93m^|  _  ^| ^|  ^| ^|  _ ^<       / ___ \^| ^|_) ^| ^|_^| ^| ^|_^| ^| ^|_^| ^|%ESC%[0m
echo %ESC%[93m^|_^| ^|_^|_^|  ^|_^|_^| \_\____ /_/   \_\____/ \___/ \___/^|____/ %ESC%[0m
echo %ESC%[93m                   ^|_____^|                                %ESC%[0m
echo %ESC%[96m==============================================================================%ESC%[0m
echo.

rem Check Python launcher
where py >nul 2>&1
if not errorlevel 1 (
    py -3 --version >nul 2>&1
    if not errorlevel 1 goto RUN_APP
)

rem Check Python command
where python >nul 2>&1
if not errorlevel 1 (
    python --version >nul 2>&1
    if not errorlevel 1 goto RUN_APP
)

echo Python 3 is not installed.
echo Downloading Python automatically...
echo.

set "INSTALLER=%TEMP%\chest_tracker_python_installer.exe"

rem Download official Python installer
powershell -NoProfile -ExecutionPolicy Bypass -Command ^
 "$ProgressPreference='SilentlyContinue'; Invoke-WebRequest -Uri 'https://www.python.org/ftp/python/3.13.9/python-3.13.9-amd64.exe' -OutFile '%INSTALLER%'"

if not exist "%INSTALLER%" (
    echo ERROR: Failed to download Python.
    pause
    exit /b 1
)

echo Installing Python for the current user...
echo Please wait.

rem Install without administrator permissions
"%INSTALLER%" /quiet InstallAllUsers=0 PrependPath=1 Include_launcher=1 Include_pip=1 Include_test=0

if errorlevel 1 (
    echo ERROR: Python installation failed.
    del "%INSTALLER%" >nul 2>&1
    pause
    exit /b 1
)

del "%INSTALLER%" >nul 2>&1

rem Refresh PATH for this BAT session
set "PATH=%LocalAppData%\Programs\Python\Python313;%LocalAppData%\Programs\Python\Python313\Scripts;%LocalAppData%\Programs\Python\Launcher;%PATH%"

echo.
echo Python installed successfully!
echo.

:RUN_APP
echo Starting Chest Tracker...
echo %ESC%[92mDO NOT CLOSE THIS%ESC%[0m
echo.

rem Prefer Python launcher
where py >nul 2>&1
if not errorlevel 1 (
    py -3 "%APP%"
    goto CHECK_ERROR
)

python "%APP%"

:CHECK_ERROR
if errorlevel 1 (
    echo.
    echo Chest Tracker stopped with an error.
    echo Copy the error above if you need help.
    pause
)

exit /b