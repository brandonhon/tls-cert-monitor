@echo off
REM TLS Certificate Monitor - Native Windows Service Installation Script
REM This script installs the TLS Certificate Monitor as a native Windows service

setlocal EnableDelayedExpansion

echo ===========================================
echo TLS Certificate Monitor Service Installer
echo (Native Windows Service)
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

echo Using native Windows service support (no NSSM required)
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

REM Check for existing service and stop it
echo Checking for existing service...
sc query "%SERVICE_NAME%" >nul 2>&1
if %errorLevel% equ 0 (
    echo Stopping existing service...
    sc.exe stop "%SERVICE_NAME%"
    timeout /t 5 /nobreak >nul

    echo Uninstalling existing service...
    sc.exe delete "%SERVICE_NAME%"
    timeout /t 2 /nobreak >nul
)

REM Install service using native Windows service support
echo Installing native Windows service...
if exist "%CONFIG_DIR%\config.yaml" (
    sc.exe create "%SERVICE_NAME%" binPath= "\"%INSTALL_DIR%\tls-cert-monitor.exe\" --config \"%CONFIG_DIR%\config.yaml\"" DisplayName= "%SERVICE_DISPLAY%" start= auto
) else (
    sc.exe create "%SERVICE_NAME%" binPath= "\"%INSTALL_DIR%\tls-cert-monitor.exe\"" DisplayName= "%SERVICE_DISPLAY%" start= auto
)

if %errorLevel% neq 0 (
    echo ERROR: Failed to install service.
    pause
    exit /b 1
)

REM Set service description
sc.exe description "%SERVICE_NAME%" "%SERVICE_DESC%"

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
echo Service Management Commands (sc.exe):
echo   Start:     sc.exe start "%SERVICE_NAME%"
echo   Stop:      sc.exe stop "%SERVICE_NAME%"
echo   Query:     sc.exe query "%SERVICE_NAME%"
echo   Delete:    sc.exe delete "%SERVICE_NAME%"
echo.
echo Service Management Commands (net.exe):
echo   Start:     net start "%SERVICE_NAME%"
echo   Stop:      net stop "%SERVICE_NAME%"
echo.
echo Alternative Windows commands:
echo   Start:     sc start "%SERVICE_NAME%"
echo   Stop:      sc stop "%SERVICE_NAME%"
echo   Status:    sc query "%SERVICE_NAME%"
echo.
echo Configuration file: %CONFIG_DIR%\config.yaml
echo.

REM Ask if user wants to start the service now
set /p START_NOW="Start the service now? (y/n): "
if /i "%START_NOW%"=="y" (
    echo Starting service...
    sc.exe start "%SERVICE_NAME%"
    timeout /t 3 /nobreak >nul
    sc.exe query "%SERVICE_NAME%"
)

echo.
echo Installation complete!
pause