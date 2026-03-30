@echo off
title ifcSQL Database Installation
color 0A

echo ===================================================
echo     ifcSQL Database Configuration and Installation
echo ===================================================
echo.
echo Format example: PC-NAME\SQLEXPRESS
echo.

:InputLoop
REM Azzeriamo la variabile in caso di ripetizione del ciclo
set "UserServerInput="
set /p UserServerInput="Enter your SQL Server name: "

REM Security check if the user leaves it blank
if "%UserServerInput%"=="" (
    echo.
    echo [ERROR] No server name entered. Please try again.
    echo.
    goto :InputLoop
)

REM Inject the "-C" flag to bypass the ODBC Driver 18 SSL Certificate error
set "SqlServer=%UserServerInput% -C"

echo.
echo [INFO] Testing connection to '%UserServerInput%'...
REM Esegue un test di connessione con timeout di 5 secondi (-l 5) per evitare blocchi
sqlcmd -S "%UserServerInput%" -C -E -Q "SELECT 1" -b -l 5 >nul 2>&1

if %ERRORLEVEL% NEQ 0 (
    echo [ERROR] Connection failed! 
    echo Please check if the server name is correct and the SQL Server service is running.
    echo.
    goto :InputLoop
)

echo [SUCCESS] Connected successfully to the SQL Server!
echo.
echo ===================================================
echo Server set to: %UserServerInput%
echo Starting the procedure...
echo.
echo Note: The procedure will pause several times to show progress.
echo Press "Enter" whenever prompted to continue.
echo ===================================================
echo.

REM Set the base directory where this script is located
set "BASE_DIR=%~dp0"

REM 1. Navigate to the Create folder and run the script
echo --- PHASE 1: Database Creation ---
cd /d "%BASE_DIR%..\IfcSQL Script\IfcSQL-main\1_ifcSQL_Create"
call ifcSQL_Create.bat

echo.
REM 2. Navigate to the Fill folder and run the script
echo --- PHASE 2: Database Population ---
cd /d "%BASE_DIR%..\IfcSQL Script\IfcSQL-main\2_ifcSQL_Fill"
call ifcSQL_Fill.bat

echo.
echo ===================================================
echo Procedure completed successfully!
echo ===================================================
pause