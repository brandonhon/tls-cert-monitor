#Requires -RunAsAdministrator

<#
.SYNOPSIS
    Install TLS Certificate Monitor as a native Windows service.

.DESCRIPTION
    This script installs the TLS Certificate Monitor as a native Windows service
    without requiring third-party tools like NSSM. It uses the built-in Windows
    service support provided by the application.

.PARAMETER ConfigPath
    Path to the configuration file. If not specified, will look for config.yaml
    in the current directory or use defaults.

.PARAMETER InstallDir
    Installation directory for the service. Defaults to Program Files.

.PARAMETER Manual
    Install the service with manual start type instead of automatic.

.PARAMETER Force
    Force reinstallation if service already exists.

.EXAMPLE
    .\Install-WindowsService.ps1
    Install with default settings and automatic start.

.EXAMPLE
    .\Install-WindowsService.ps1 -ConfigPath "C:\MyConfig\config.yaml" -Manual
    Install with custom config and manual start.
#>

[CmdletBinding()]
param(
    [Parameter(Mandatory = $false)]
    [string]$ConfigPath,

    [Parameter(Mandatory = $false)]
    [string]$InstallDir = "$env:ProgramFiles\TLSCertMonitor",

    [Parameter(Mandatory = $false)]
    [switch]$Manual,

    [Parameter(Mandatory = $false)]
    [switch]$Force
)

# Service configuration
$ServiceName = "TLSCertMonitor"
$ServiceDisplay = "TLS Certificate Monitor"
$ConfigDir = "$env:ProgramData\TLSCertMonitor"
$LogDir = "$env:ProgramData\TLSCertMonitor\logs"

function Write-Header {
    Write-Host "===========================================" -ForegroundColor Cyan
    Write-Host "TLS Certificate Monitor Service Installer" -ForegroundColor Cyan
    Write-Host "(Native Windows Service)"                    -ForegroundColor Cyan
    Write-Host "===========================================" -ForegroundColor Cyan
    Write-Host ""
}

function Test-Administrator {
    $currentUser = [Security.Principal.WindowsIdentity]::GetCurrent()
    $principal = New-Object Security.Principal.WindowsPrincipal($currentUser)
    return $principal.IsInRole([Security.Principal.WindowsBuiltInRole]::Administrator)
}

function New-RequiredDirectories {
    Write-Host "Creating required directories..." -ForegroundColor Yellow

    @($InstallDir, $ConfigDir, $LogDir) | ForEach-Object {
        if (-not (Test-Path $_)) {
            New-Item -ItemType Directory -Path $_ -Force | Out-Null
            Write-Host "  Created: $_" -ForegroundColor Green
        } else {
            Write-Host "  Exists: $_" -ForegroundColor Gray
        }
    }
}

function Copy-ApplicationFiles {
    Write-Host "Copying application files..." -ForegroundColor Yellow

    $exePath = "tls-cert-monitor.exe"
    if (-not (Test-Path $exePath)) {
        Write-Error "ERROR: $exePath not found in current directory."
        Write-Host "Please run this script from the directory containing the binary." -ForegroundColor Red
        exit 1
    }

    $destPath = Join-Path $InstallDir "tls-cert-monitor.exe"
    Copy-Item $exePath $destPath -Force
    Write-Host "  Copied: $exePath -> $destPath" -ForegroundColor Green

    # Handle configuration
    if ($ConfigPath -and (Test-Path $ConfigPath)) {
        $configDest = Join-Path $ConfigDir "config.yaml"
        Copy-Item $ConfigPath $configDest -Force
        Write-Host "  Copied: $ConfigPath -> $configDest" -ForegroundColor Green
    } elseif (Test-Path "config.yaml") {
        $configDest = Join-Path $ConfigDir "config.yaml"
        Copy-Item "config.yaml" $configDest -Force
        Write-Host "  Copied: config.yaml -> $configDest" -ForegroundColor Green
    } elseif (Test-Path "config.example.yaml") {
        $configDest = Join-Path $ConfigDir "config.yaml"
        Copy-Item "config.example.yaml" $configDest -Force
        Write-Host "  Copied template: config.example.yaml -> $configDest" -ForegroundColor Green
        Write-Host "  Please edit $configDest before starting the service" -ForegroundColor Yellow
    } else {
        Write-Warning "No configuration file found. You'll need to create $ConfigDir\config.yaml manually."
    }
}

function Remove-ExistingService {
    Write-Host "Checking for existing service..." -ForegroundColor Yellow

    $exePath = Join-Path $InstallDir "tls-cert-monitor.exe"

    try {
        $service = Get-Service -Name $ServiceName -ErrorAction SilentlyContinue
        if ($service) {
            if ($Force) {
                Write-Host "  Stopping existing service..." -ForegroundColor Yellow
                & $exePath --service-stop
                Start-Sleep -Seconds 3

                Write-Host "  Uninstalling existing service..." -ForegroundColor Yellow
                & $exePath --service-uninstall
                Start-Sleep -Seconds 2
            } else {
                Write-Error "Service already exists. Use -Force to reinstall."
                exit 1
            }
        }
    } catch {
        # Service doesn't exist, continue
    }
}

function Install-Service {
    Write-Host "Installing native Windows service..." -ForegroundColor Yellow

    $exePath = Join-Path $InstallDir "tls-cert-monitor.exe"
    $configPath = Join-Path $ConfigDir "config.yaml"

    $args = @("--service-install")

    if (Test-Path $configPath) {
        $args += "--config=`"$configPath`""
    }

    if ($Manual) {
        $args += "--service-manual"
    }

    Write-Host "  Command: $exePath $($args -join ' ')" -ForegroundColor Gray

    $result = & $exePath @args
    $exitCode = $LASTEXITCODE

    if ($exitCode -eq 0) {
        Write-Host "  Service installed successfully!" -ForegroundColor Green
    } else {
        Write-Error "Failed to install service (exit code: $exitCode)"
        Write-Host "Make sure pywin32 is properly installed." -ForegroundColor Red
        exit 1
    }
}

function Show-ServiceInfo {
    $exePath = Join-Path $InstallDir "tls-cert-monitor.exe"
    $configPath = Join-Path $ConfigDir "config.yaml"

    Write-Host ""
    Write-Host "Service installed successfully!" -ForegroundColor Green
    Write-Host ""
    Write-Host "Service Details:" -ForegroundColor Cyan
    Write-Host "  Name:              $ServiceName"
    Write-Host "  Display Name:      $ServiceDisplay"
    Write-Host "  Install Directory: $InstallDir"
    Write-Host "  Config Directory:  $ConfigDir"
    Write-Host "  Log Directory:     $LogDir"
    Write-Host ""
    Write-Host "Service Management Commands:" -ForegroundColor Cyan
    Write-Host "  Install:    $exePath --service-install [--config=path]"
    Write-Host "  Start:      $exePath --service-start"
    Write-Host "  Stop:       $exePath --service-stop"
    Write-Host "  Status:     $exePath --service-status"
    Write-Host "  Uninstall:  $exePath --service-uninstall"
    Write-Host ""
    Write-Host "Alternative Windows commands:" -ForegroundColor Cyan
    Write-Host "  Start:      Start-Service -Name '$ServiceName'"
    Write-Host "  Stop:       Stop-Service -Name '$ServiceName'"
    Write-Host "  Status:     Get-Service -Name '$ServiceName'"
    Write-Host ""
    Write-Host "Configuration file: $configPath"
    Write-Host ""
}

function Start-ServicePrompt {
    $response = Read-Host "Start the service now? (Y/n)"

    if ($response -eq "" -or $response -eq "Y" -or $response -eq "y") {
        Write-Host "Starting service..." -ForegroundColor Yellow

        $exePath = Join-Path $InstallDir "tls-cert-monitor.exe"
        & $exePath --service-start

        Start-Sleep -Seconds 3

        Write-Host "Service status:" -ForegroundColor Yellow
        & $exePath --service-status
    }
}

# Main execution
try {
    Write-Header

    if (-not (Test-Administrator)) {
        Write-Error "This script must be run as Administrator."
        Write-Host "Right-click PowerShell and select 'Run as administrator'" -ForegroundColor Red
        exit 1
    }

    New-RequiredDirectories
    Copy-ApplicationFiles
    Remove-ExistingService
    Install-Service
    Show-ServiceInfo
    Start-ServicePrompt

    Write-Host ""
    Write-Host "Installation complete!" -ForegroundColor Green

} catch {
    Write-Error "Installation failed: $($_.Exception.Message)"
    exit 1
}