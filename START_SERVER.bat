@echo off
title SAMS 4th Year Project - Flask Server
color 0A
cls
echo ============================================================
echo    SAMS 4th Year Project - Starting Flask Server...
echo ============================================================
echo.
echo  Server will be available at: http://127.0.0.1:5000
echo  Press CTRL+C to stop the server.
echo ============================================================
echo.

cd /d "%~dp0"

REM ---- MySQL binary paths (primary = the one with drk_college data) ----
set MYSQL_PRIMARY=%USERPROFILE%\Downloads\D\mysql\bin\mysqld.exe
set MYSQL_PRIMARY_INI=%USERPROFILE%\Downloads\D\mysql\bin\my.ini
set MYSQL_FALLBACK=C:\xampp\mysql\bin\mysqld.exe
set MYSQL_FALLBACK_INI=C:\xampp\mysql\bin\my.ini

REM ---- Step 1: Check if MySQL is already running on port 3306 ----
netstat -an | findstr "3306" | findstr "LISTENING" >nul 2>&1
if %errorlevel% equ 0 (
    echo [+] MySQL is already running on port 3306. 
    goto :mysql_ready
)

echo [*] MySQL is not running. Starting MySQL...

REM ---- Try primary MySQL (has drk_college data) ----
if exist "%MYSQL_PRIMARY%" (
    echo [*] Starting primary MySQL from Downloads\D\mysql ...
    start "" /B "%MYSQL_PRIMARY%" "--defaults-file=%MYSQL_PRIMARY_INI%"
    echo [*] Waiting for MySQL to start...
    timeout /t 6 /nobreak >nul
    netstat -an | findstr "3306" | findstr "LISTENING" >nul 2>&1
    if %errorlevel% equ 0 (
        echo [+] Primary MySQL started successfully!
        goto :mysql_ready
    )
    echo [!] Primary MySQL did not start. Trying XAMPP MySQL...
)

REM ---- Try XAMPP MySQL as fallback ----
if exist "%MYSQL_FALLBACK%" (
    echo [*] Starting XAMPP MySQL...
    start "" /B "%MYSQL_FALLBACK%" "--defaults-file=%MYSQL_FALLBACK_INI%" --standalone
    echo [*] Waiting for MySQL to start...
    timeout /t 6 /nobreak >nul
    netstat -an | findstr "3306" | findstr "LISTENING" >nul 2>&1
    if %errorlevel% equ 0 (
        echo [+] XAMPP MySQL started successfully!
        goto :mysql_ready
    )
)

echo.
echo [!] ERROR: Could not start MySQL on port 3306.
echo     Please start MySQL manually using the XAMPP Control Panel,
echo     or start it from: %MYSQL_PRIMARY%
echo.
pause
exit /b 1

:mysql_ready
echo.

REM ---- Step 2: Check virtual environment ----
if not exist ".venv\Scripts\python.exe" (
    echo [!] ERROR: Virtual environment not found!
    echo     Please run: python -m venv .venv
    echo     Then:       .venv\Scripts\pip install -r requirements.txt
    pause
    exit /b 1
)

REM ---- Step 3: Activate venv ----
call .venv\Scripts\activate.bat 2>nul

REM ---- Step 4: Start Flask server ----
echo [*] Starting Flask server...
echo.
start "SAMS Flask Server" /B .venv\Scripts\python.exe app.py

REM Give Flask time to bind before opening the browser.
timeout /t 3 /nobreak >nul
echo [*] Opening browser at http://127.0.0.1:5000 ...
start http://127.0.0.1:5000

echo.
echo [+] Server started. Close this window to stop.
pause
