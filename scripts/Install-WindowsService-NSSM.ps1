#Requires -RunAsAdministrator

<#
.SYNOPSIS
    Install TLS Certificate Monitor as a Windows service using NSSM.

.DESCRIPTION
    This script provides an alternative service installation method using NSSM
    (Non-Sucking Service Manager) which can wrap any executable as a Windows service.
    This avoids the need for pywin32 and complex service integration.

.PARAMETER ConfigPath
    Path to the configuration file.

.PARAMETER InstallDir
    Installation directory for the service.

.PARAMETER NSSMPath
    Path to NSSM executable. If not provided, script will try to download it.

.EXAMPLE
    .\Install-WindowsService-NSSM.ps1 -ConfigPath "C:\config\config.yaml"
#>

[CmdletBinding()]
param(
    [Parameter(Mandatory = $false)]
    [string]$ConfigPath,

    [Parameter(Mandatory = $false)]
    [string]$InstallDir = "$env:ProgramFiles\TLSCertMonitor",

    [Parameter(Mandatory = $false)]
    [string]$NSSMPath
)

# Service configuration
$ServiceName = "TLSCertMonitor"
$ServiceDisplay = "TLS Certificate Monitor"
$ServiceDescription = "Monitor TLS/SSL certificates for expiration and security issues"

function Get-NSSM {
    param([string]$TargetDir)

    $nssmUrl = "https://nssm.cc/release/nssm-2.24.zip"
    $nssmZip = Join-Path $env:TEMP "nssm-2.24.zip"
    $nssmExtract = Join-Path $env:TEMP "nssm-2.24"

    Write-Host "Downloading NSSM..." -ForegroundColor Yellow
    Invoke-WebRequest -Uri $nssmUrl -OutFile $nssmZip

    Write-Host "Extracting NSSM..." -ForegroundColor Yellow
    Expand-Archive -Path $nssmZip -DestinationPath $env:TEMP -Force

    # Copy appropriate architecture
    $arch = if ([Environment]::Is64BitOperatingSystem) { "win64" } else { "win32" }
    $nssmExe = Join-Path $nssmExtract "nssm-2.24\$arch\nssm.exe"
    $targetNssm = Join-Path $TargetDir "nssm.exe"

    Copy-Item $nssmExe $targetNssm

    # Cleanup
    Remove-Item $nssmZip -Force
    Remove-Item $nssmExtract -Recurse -Force

    return $targetNssm
}

function Install-ServiceWithNSSM {
    param(
        [string]$NSSMExe,
        [string]$ExePath,
        [string]$ConfigPath
    )

    Write-Host "Installing service with NSSM..." -ForegroundColor Yellow

    # Remove existing service if it exists
    $existingService = Get-Service -Name $ServiceName -ErrorAction SilentlyContinue
    if ($existingService) {
        Write-Host "Stopping and removing existing service..." -ForegroundColor Gray
        & $NSSMExe stop $ServiceName
        & $NSSMExe remove $ServiceName confirm
    }

    # Install service
    & $NSSMExe install $ServiceName $ExePath

    # Configure service parameters
    if ($ConfigPath) {
        & $NSSMExe set $ServiceName AppParameters "--config `"$ConfigPath`""
    }

    # Set service properties
    & $NSSMExe set $ServiceName DisplayName $ServiceDisplay
    & $NSSMExe set $ServiceName Description $ServiceDescription
    & $NSSMExe set $ServiceName Start SERVICE_AUTO_START

    # Configure application directory
    $appDir = Split-Path $ExePath -Parent
    & $NSSMExe set $ServiceName AppDirectory $appDir

    # Configure logging
    $logDir = Join-Path $env:ProgramData "TLSCertMonitor\logs"
    if (-not (Test-Path $logDir)) {
        New-Item -ItemType Directory -Path $logDir -Force | Out-Null
    }

    & $NSSMExe set $ServiceName AppStdout (Join-Path $logDir "service-stdout.log")
    & $NSSMExe set $ServiceName AppStderr (Join-Path $logDir "service-stderr.log")

    # Configure service recovery
    & $NSSMExe set $ServiceName AppThrottle 5000  # 5 second throttle
    & $NSSMExe set $ServiceName AppExit Default Restart
    & $NSSMExe set $ServiceName AppRestartDelay 5000

    Write-Host "Service installed successfully with NSSM" -ForegroundColor Green
}

# Main execution
try {
    Write-Host "TLS Certificate Monitor - NSSM Service Installation" -ForegroundColor Cyan
    Write-Host "=" * 60 -ForegroundColor Cyan

    # Validate executable
    $exePath = Join-Path $InstallDir "tls-cert-monitor.exe"
    if (-not (Test-Path $exePath)) {
        throw "TLS Certificate Monitor executable not found at: $exePath"
    }

    # Validate config if provided
    if ($ConfigPath -and -not (Test-Path $ConfigPath)) {
        throw "Configuration file not found at: $ConfigPath"
    }

    # Get or download NSSM
    if (-not $NSSMPath) {
        $NSSMPath = Join-Path $InstallDir "nssm.exe"
        if (-not (Test-Path $NSSMPath)) {
            $NSSMPath = Get-NSSM -TargetDir $InstallDir
        }
    }

    if (-not (Test-Path $NSSMPath)) {
        throw "NSSM executable not found at: $NSSMPath"
    }

    # Install service
    Install-ServiceWithNSSM -NSSMExe $NSSMPath -ExePath $exePath -ConfigPath $ConfigPath

    # Start service
    Write-Host ""
    $response = Read-Host "Start the service now? (Y/n)"
    if ($response -eq "" -or $response -eq "Y" -or $response -eq "y") {
        Write-Host "Starting service..." -ForegroundColor Yellow
        & $NSSMPath start $ServiceName

        Start-Sleep -Seconds 3

        $service = Get-Service -Name $ServiceName
        if ($service.Status -eq 'Running') {
            Write-Host "Service started successfully!" -ForegroundColor Green
        } else {
            Write-Warning "Service status: $($service.Status)"
        }
    }

    Write-Host ""
    Write-Host "Service Management Commands:" -ForegroundColor Cyan
    Write-Host "  Start:      $NSSMPath start $ServiceName" -ForegroundColor Gray
    Write-Host "  Stop:       $NSSMPath stop $ServiceName" -ForegroundColor Gray
    Write-Host "  Restart:    $NSSMPath restart $ServiceName" -ForegroundColor Gray
    Write-Host "  Status:     Get-Service -Name $ServiceName" -ForegroundColor Gray
    Write-Host "  Remove:     $NSSMPath remove $ServiceName confirm" -ForegroundColor Gray
    Write-Host ""
    Write-Host "Logs are available at: $env:ProgramData\TLSCertMonitor\logs\" -ForegroundColor Cyan

} catch {
    Write-Error "Installation failed: $_"
    exit 1
}