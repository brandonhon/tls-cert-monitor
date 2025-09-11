@echo off
REM TLS Certificate Monitor - Windows Service Installation Script
REM This script installs the TLS Certificate Monitor as a Windows service using NSSM (Non-Sucking Service Manager)

setlocal EnableDelayedExpansion

echo ===========================================
echo TLS Certificate Monitor Service Installer
echo ===========================================
echo.

REM Check if running as administrator
net session >nul 2>&1
if %errorLevel% neq 0 (
    echo ERROR: This script must be run as Administrator.
    echo Right-click on this script and select "Run as administrator"
    pause
    exit /b 1
)

REM Service configuration
set SERVICE_NAME=TLSCertMonitor
set SERVICE_DISPLAY=TLS Certificate Monitor
set SERVICE_DESC=Monitors TLS/SSL certificates and provides Prometheus metrics
set INSTALL_DIR=%ProgramFiles%\TLSCertMonitor
set CONFIG_DIR=%ProgramData%\TLSCertMonitor
set LOG_DIR=%ProgramData%\TLSCertMonitor\logs

echo Checking for NSSM (Non-Sucking Service Manager)...

REM Check if NSSM is available
nssm version >nul 2>&1
if %errorLevel% neq 0 (
    echo ERROR: NSSM is not installed or not in PATH.
    echo.
    echo Please install NSSM:
    echo 1. Download from: https://nssm.cc/download
    echo 2. Extract nssm.exe to a directory in your PATH (e.g., C:\Windows\System32)
    echo 3. Or extract to the same directory as this script
    echo.
    pause
    exit /b 1
)

echo NSSM found. Proceeding with service installation...
echo.

REM Create directories
echo Creating directories...
if not exist "%INSTALL_DIR%" mkdir "%INSTALL_DIR%"
if not exist "%CONFIG_DIR%" mkdir "%CONFIG_DIR%"
if not exist "%LOG_DIR%" mkdir "%LOG_DIR%"

REM Copy files
echo Copying application files...
if exist "tls-cert-monitor.exe" (
    copy "tls-cert-monitor.exe" "%INSTALL_DIR%\"
) else (
    echo ERROR: tls-cert-monitor.exe not found in current directory.
    echo Please place this script in the same directory as the binary.
    pause
    exit /b 1
)

REM Copy configuration
if exist "config.yaml" (
    copy "config.yaml" "%CONFIG_DIR%\"
) else if exist "config.example.yaml" (
    copy "config.example.yaml" "%CONFIG_DIR%\config.yaml"
    echo Configuration template copied. Please edit %CONFIG_DIR%\config.yaml
) else (
    echo WARNING: No configuration file found. You'll need to create %CONFIG_DIR%\config.yaml manually.
)

REM Stop service if it exists
echo Checking for existing service...
sc query "%SERVICE_NAME%" >nul 2>&1
if %errorLevel% equ 0 (
    echo Stopping existing service...
    nssm stop "%SERVICE_NAME%"
    timeout /t 5 /nobreak >nul
)

REM Install service
echo Installing Windows service...
nssm install "%SERVICE_NAME%" "%INSTALL_DIR%\tls-cert-monitor.exe"

REM Configure service
echo Configuring service parameters...
nssm set "%SERVICE_NAME%" DisplayName "%SERVICE_DISPLAY%"
nssm set "%SERVICE_NAME%" Description "%SERVICE_DESC%"
nssm set "%SERVICE_NAME%" Start SERVICE_AUTO_START
nssm set "%SERVICE_NAME%" AppDirectory "%INSTALL_DIR%"
nssm set "%SERVICE_NAME%" AppParameters "--config=%CONFIG_DIR%\config.yaml"

REM Configure logging
nssm set "%SERVICE_NAME%" AppStdout "%LOG_DIR%\service.log"
nssm set "%SERVICE_NAME%" AppStderr "%LOG_DIR%\service-error.log"
nssm set "%SERVICE_NAME%" AppRotateFiles 1
nssm set "%SERVICE_NAME%" AppRotateOnline 1
nssm set "%SERVICE_NAME%" AppRotateSeconds 86400
nssm set "%SERVICE_NAME%" AppRotateBytes 10485760

REM Configure restart behavior
nssm set "%SERVICE_NAME%" AppThrottle 1500
nssm set "%SERVICE_NAME%" AppExit Default Restart
nssm set "%SERVICE_NAME%" AppRestartDelay 0

REM Set environment variables if needed
nssm set "%SERVICE_NAME%" AppEnvironmentExtra "TLS_MONITOR_CONFIG_FILE=%CONFIG_DIR%\config.yaml"

echo.
echo Service installed successfully!
echo.
echo Service Details:
echo   Name: %SERVICE_NAME%
echo   Display Name: %SERVICE_DISPLAY%
echo   Install Directory: %INSTALL_DIR%
echo   Config Directory: %CONFIG_DIR%
echo   Log Directory: %LOG_DIR%
echo.
echo To start the service:
echo   sc start "%SERVICE_NAME%"
echo   OR
echo   nssm start "%SERVICE_NAME%"
echo.
echo To stop the service:
echo   sc stop "%SERVICE_NAME%"
echo   OR
echo   nssm stop "%SERVICE_NAME%"
echo.
echo To uninstall the service:
echo   nssm remove "%SERVICE_NAME%"
echo.
echo Configuration file: %CONFIG_DIR%\config.yaml
echo Service logs: %LOG_DIR%\service.log
echo.

REM Ask if user wants to start the service now
set /p START_NOW="Start the service now? (y/n): "
if /i "%START_NOW%"=="y" (
    echo Starting service...
    nssm start "%SERVICE_NAME%"
    timeout /t 3 /nobreak >nul
    sc query "%SERVICE_NAME%"
)

echo.
echo Installation complete!
pause