@echo off
title ifcSQL Database Setup and TDS FDW Installation
echo ===================================================
echo   PostgreSQL 16 Database Setup ^& FDW Installation
echo ===================================================
echo.

:: --- 0. CHECK ADMINISTRATOR PRIVILEGES ---
net session >nul 2>&1
if %errorLevel% neq 0 (
    echo [FATAL ERROR] Administrator privileges are required!
    echo To copy the FDW files and restart services,
    echo please right-click this .bat file and select "Run as administrator".
    echo.
    pause
    exit /b 1
)

:: --- 1. SEARCHING FOR POSTGRESQL PATH ---
set "PG_BIN_PATH="
set "PG_BASE_PATH="

:: Attempt A: Default installation path
set "DEFAULT_PATH=C:\Program Files\PostgreSQL\16\bin"
if exist "%DEFAULT_PATH%\psql.exe" (
    set "PG_BIN_PATH=%DEFAULT_PATH%"
    set "PG_BASE_PATH=C:\Program Files\PostgreSQL\16"
    goto :path_found
)

:: Attempt B: If not found, ask the user (Fallback)
echo [WARNING] The default PostgreSQL 16 path was not found.
echo Please enter the full path to your PostgreSQL 16 'bin' folder.
echo (Example: D:\Programs\PostgreSQL\16\bin)
set /p USER_BIN_PATH="Path: "

:: Remove accidental quotes
set USER_BIN_PATH=%USER_BIN_PATH:"=%
set "PG_BIN_PATH=%USER_BIN_PATH%"
for %%I in ("%PG_BIN_PATH%\..") do set "PG_BASE_PATH=%%~fI"

if not exist "%PG_BIN_PATH%\psql.exe" (
    echo.
    echo [FATAL ERROR] psql.exe is not present in that path. Aborting.
    pause
    exit /b 1
)

:path_found
echo [INFO] PostgreSQL base path found at: %PG_BASE_PATH%
echo.

:: --- 2. DEPLOYING TDS FDW FILES ---
echo [INFO] Deploying TDS FDW files to PostgreSQL directories...
set "SRC_DIR=%~dp0..\tds_FDW_16"

if not exist "%SRC_DIR%" (
    echo [ERROR] Source folder not found: %SRC_DIR%
    echo Make sure the script is in the correct 'first_installation' folder.
    pause
    exit /b 1
)

echo Copying extension files (.control, .sql)...
copy /Y "%SRC_DIR%\tds_fdw.control" "%PG_BASE_PATH%\share\extension\" >nul
copy /Y "%SRC_DIR%\tds_fdw--2.0.3.sql" "%PG_BASE_PATH%\share\extension\" >nul

echo Updating module_pathname in tds_fdw.control...
set "PS_CMD=(Get-Content '%PG_BASE_PATH%\share\extension\tds_fdw.control') -replace 'module_pathname\s*=\s*.*', 'module_pathname = ''C:/Program Files/PostgreSQL/16/lib/tds_fdw''' | Set-Content '%PG_BASE_PATH%\share\extension\tds_fdw.control'"
powershell -Command "%PS_CMD%"

echo Stopping PostgreSQL service to unlock DLL files...
net stop postgresql-x64-16 >nul 2>&1

echo Copying DLL binaries to bin folder...
copy /Y "%SRC_DIR%\libcrypto-3-x64.dll" "%PG_BIN_PATH%\" >nul
copy /Y "%SRC_DIR%\libssl-3-x64.dll" "%PG_BIN_PATH%\" >nul
copy /Y "%SRC_DIR%\sybdb.dll" "%PG_BIN_PATH%\" >nul

echo Copying tds_fdw.dll to lib folder...
copy /Y "%SRC_DIR%\tds_fdw.dll" "%PG_BASE_PATH%\lib\" >nul

echo Restarting PostgreSQL service...
net start postgresql-x64-16 >nul 2>&1

echo [SUCCESS] FDW files deployed successfully!
echo.

:PgCredsLoop
:: --- 3. REQUEST CREDENTIALS FOR DB CREATION ---
echo --- PostgreSQL Authentication ---
set "PGUSER="
set "PGPASSWORD="
set /p PGUSER="Enter PostgreSQL username (e.g., postgres): "
set /p PGPASSWORD="Enter password for user %PGUSER%: "

echo [INFO] Testing PostgreSQL connection...
"%PG_BIN_PATH%\psql.exe" -U "%PGUSER%" -d postgres -tAc "SELECT 1;" >nul 2>&1

if %ERRORLEVEL% NEQ 0 (
    echo.
    echo [ERROR] Connection failed! Invalid username, password, or service not running.
    echo Please try again.
    echo.
    goto :PgCredsLoop
)
echo [SUCCESS] Connected successfully to PostgreSQL!
echo.

:: --- 4. SMART DATABASE CREATION ---
set "DB_BASENAME=ifcSQL"
set "TARGET_DB=%DB_BASENAME%"
set "SUFFIX_COUNTER=1"

:CheckDB
"%PG_BIN_PATH%\psql.exe" -U "%PGUSER%" -d postgres -tAc "SELECT 1 FROM pg_database WHERE datname='%TARGET_DB%'" | find "1" >nul
if %ERRORLEVEL% NEQ 0 goto :CreateDB

echo [INFO] The database '%TARGET_DB%' already exists.
set /p CREATE_NEW="Do you want to create a new numbered database? (Y/N): "
if /I "%CREATE_NEW%"=="Y" goto :FindNextAvailable

:: Se l'utente dice NO alla creazione di un nuovo DB:
echo.
echo [INFO] Skipping database creation.
set /p MODIFY_FDW="Do you want to modify the FDW connection parameters with MSSQL? (Y/N): "
if /I "%MODIFY_FDW%"=="Y" (
    echo [INFO] Proceeding to update FDW parameters on existing '%TARGET_DB%'...
    goto :ExtensionsSetup
) else (
    echo [INFO] Exiting setup.
    goto :EndScript
)

:FindNextAvailable
set "PAD_SUFFIX=0%SUFFIX_COUNTER%"
set "PAD_SUFFIX=%PAD_SUFFIX:~-2%"
set "TARGET_DB=%DB_BASENAME%%PAD_SUFFIX%"

"%PG_BIN_PATH%\psql.exe" -U "%PGUSER%" -d postgres -tAc "SELECT 1 FROM pg_database WHERE datname='%TARGET_DB%'" | find "1" >nul
if %ERRORLEVEL% NEQ 0 goto :CreateDB

set /a SUFFIX_COUNTER+=1
if %SUFFIX_COUNTER% GTR 99 (
    echo [ERROR] Reached maximum number of test databases. Aborting.
    goto :EndScript
)
goto :FindNextAvailable

:CreateDB
echo Creating '%TARGET_DB%' database...
"%PG_BIN_PATH%\psql.exe" -U "%PGUSER%" -d postgres -c "CREATE DATABASE \"%TARGET_DB%\";"

:ExtensionsSetup
:: --- 5. CREATE EXTENSIONS ---
echo.
echo --- Installing Extensions ---
echo Installing tds_fdw and postgis on '%TARGET_DB%'...
"%PG_BIN_PATH%\psql.exe" -U "%PGUSER%" -d "%TARGET_DB%" -c "CREATE EXTENSION IF NOT EXISTS tds_fdw;"
"%PG_BIN_PATH%\psql.exe" -U "%PGUSER%" -d "%TARGET_DB%" -c "CREATE EXTENSION IF NOT EXISTS postgis;"

:FdwSetupLoop
:: --- 6. FDW CONFIGURATION (MSSQL) ---
echo.
echo --- MSSQL Foreign Data Wrapper Setup ---
:: Azzeriamo le variabili ad ogni ciclo per evitare bug nei ritentativi
set "MSSQL_SERVER="
set "MSSQL_PORT="
set "MSSQL_USER="
set "MSSQL_PASS="

set /p MSSQL_SERVER="Enter MSSQL Server Name without SQLEXPRESS (e.g., NB-8988): "
set /p MSSQL_PORT="Enter MSSQL Port [Press Enter for 1433]: "
if "%MSSQL_PORT%"=="" set "MSSQL_PORT=1433"
set /p MSSQL_USER="Enter MSSQL Username (e.g., mssql_user): "
set /p MSSQL_PASS="Enter MSSQL Password: "

echo.
echo Configuring FDW Server 'mssql_ifcsql' and User Mapping...
:: Eliminiamo a cascata il server precedente (se stiamo riprovando) per azzerare le dipendenze errate
"%PG_BIN_PATH%\psql.exe" -U "%PGUSER%" -d "%TARGET_DB%" -c "DROP SERVER IF EXISTS mssql_ifcsql CASCADE;" >nul 2>&1

"%PG_BIN_PATH%\psql.exe" -U "%PGUSER%" -d "%TARGET_DB%" -c "CREATE SERVER mssql_ifcsql FOREIGN DATA WRAPPER tds_fdw OPTIONS (servername '%MSSQL_SERVER%', port '%MSSQL_PORT%', database 'ifcSQL');"
"%PG_BIN_PATH%\psql.exe" -U "%PGUSER%" -d "%TARGET_DB%" -c "CREATE USER MAPPING FOR \"%PGUSER%\" SERVER mssql_ifcsql OPTIONS (username '%MSSQL_USER%', password '%MSSQL_PASS%');"

:: --- 7. SCHEMA CREATION AND TABLE IMPORT ---
echo.
echo --- Schema Creation and Table Import ---
echo Creating schemas: ifcinstance, ifcgeometry, territory...
"%PG_BIN_PATH%\psql.exe" -U "%PGUSER%" -d "%TARGET_DB%" -c "CREATE SCHEMA IF NOT EXISTS ifcinstance;"
"%PG_BIN_PATH%\psql.exe" -U "%PGUSER%" -d "%TARGET_DB%" -c "CREATE SCHEMA IF NOT EXISTS ifcgeometry;"
"%PG_BIN_PATH%\psql.exe" -U "%PGUSER%" -d "%TARGET_DB%" -c "CREATE SCHEMA IF NOT EXISTS ifcproject;"
"%PG_BIN_PATH%\psql.exe" -U "%PGUSER%" -d "%TARGET_DB%" -c "CREATE SCHEMA IF NOT EXISTS territory;"

:: Define the folder path containing the SQL scripts
set "SQL_FOLDER_PATH=%~dp0..\IfcSQL_scripts\IfcSQL-PostgreSQL"

if exist "%SQL_FOLDER_PATH%\*.sql" (
    echo.
    echo Executing all found SQL scripts...
    for %%f in ("%SQL_FOLDER_PATH%\*.sql") do (
        echo.
        echo ---------------------------------------------------
        echo Importing: %%~nxf
        "%PG_BIN_PATH%\psql.exe" -v ON_ERROR_STOP=1 -U "%PGUSER%" -d "%TARGET_DB%" -f "%%f"
        
        if errorlevel 1 (
            echo [ERROR] Script execution failed: %%~nxf
        ) else (
            echo [SUCCESS] Script imported correctly: %%~nxf
        )
    )
    echo ---------------------------------------------------
) else (
    echo [WARNING] No SQL scripts found in path: %SQL_FOLDER_PATH%
)

:: --- 8. TEST CONNECTION ---
echo.
echo --- Connection Test ---
echo Attempting to read the first 5 rows from 'ifcinstance.entity'...
"%PG_BIN_PATH%\psql.exe" -U "%PGUSER%" -d "%TARGET_DB%" -c "SELECT * FROM ifcinstance.entity LIMIT 5;"

if %ERRORLEVEL% EQU 0 goto :TestSuccess
goto :TestFail

:TestSuccess
echo.
echo [SUCCESS] Everything is working perfectly! Connection to MSSQL established.
goto :EndScript

:TestFail
echo.
echo [ERROR] Could not read from MSSQL. Check if the MSSQL server is reachable and credentials are correct (server name; port; username; password).
echo.
set /p RETRY_FDW="Do you want to re-enter the MSSQL credentials and try again? (Y/N): "
if /I "%RETRY_FDW%"=="Y" goto :FdwSetupLoop
goto :EndScript

:EndScript
:: Clear passwords from memory
set PGPASSWORD=
set MSSQL_PASS=

echo.
pause