@echo off
title ifcSQL Database Installation
color 0A

echo ===================================================
echo     ifcSQL Database Configuration and Installation
echo ===================================================
echo.
echo Format example: PC-NAME\SQLEXPRESS
echo.

REM Prompt the user for the SQL Server name
set /p UserServerInput="Enter your SQL Server name: "

REM Security check if the user leaves it blank
if "%UserServerInput%"=="" (
    echo.
    echo ERROR: No server name entered. The installation will be aborted.
    pause
    exit /b
)

REM Inject the "-C" flag to bypass the ODBC Driver 18 SSL Certificate error
set SqlServer=%UserServerInput% -C

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