#Requires -RunAsAdministrator

<#
.SYNOPSIS
    Test script for validating Windows service installation and operation.

.DESCRIPTION
    This script tests the enhanced Windows service capabilities of TLS Certificate Monitor.
    It validates service installation, startup, operation, and cleanup.
#>

[CmdletBinding()]
param(
    [Parameter(Mandatory = $false)]
    [string]$BinaryPath = "C:\Program Files\TLSCertMonitor\tls-cert-monitor.exe",

    [Parameter(Mandatory = $false)]
    [string]$ConfigPath = "C:\ProgramData\TLSCertMonitor\config.yaml",

    [Parameter(Mandatory = $false)]
    [switch]$SkipCleanup
)

$ServiceName = "TLSCertMonitor"
$TestTimeout = 60  # seconds

function Write-TestResult {
    param([string]$Test, [bool]$Success, [string]$Details = "")
    $status = if ($Success) { "✅ PASS" } else { "❌ FAIL" }
    $color = if ($Success) { "Green" } else { "Red" }

    Write-Host "[$status] $Test" -ForegroundColor $color
    if ($Details) {
        Write-Host "    $Details" -ForegroundColor Gray
    }
}

function Test-ServiceInstallation {
    Write-Host "`n🔧 Testing Service Installation..." -ForegroundColor Cyan

    try {
        # Create service
        $binaryPathName = "`"$BinaryPath`" --config `"$ConfigPath`""
        $result = sc.exe create $ServiceName binPath= $binaryPathName DisplayName= "TLS Certificate Monitor Test" start= demand description= "Test installation of TLS Certificate Monitor"

        if ($LASTEXITCODE -eq 0) {
            Write-TestResult "Service Creation" $true "Service created successfully"
            return $true
        } else {
            Write-TestResult "Service Creation" $false "sc.exe create failed with exit code $LASTEXITCODE"
            return $false
        }
    } catch {
        Write-TestResult "Service Creation" $false "Exception: $_"
        return $false
    }
}

function Test-ServiceStartup {
    Write-Host "`n🚀 Testing Service Startup..." -ForegroundColor Cyan

    try {
        # Start service
        $result = sc.exe start $ServiceName
        $startExitCode = $LASTEXITCODE

        if ($startExitCode -ne 0) {
            Write-TestResult "Service Start Command" $false "sc.exe start failed with exit code $startExitCode"
            return $false
        }

        Write-TestResult "Service Start Command" $true "Start command executed"

        # Wait for service to reach running state
        $timeout = $TestTimeout
        $running = $false

        while ($timeout -gt 0 -and -not $running) {
            Start-Sleep -Seconds 2
            $timeout -= 2

            $service = Get-Service -Name $ServiceName -ErrorAction SilentlyContinue
            if ($service -and $service.Status -eq 'Running') {
                $running = $true
                Write-TestResult "Service Startup" $true "Service reached Running state in $([int]($TestTimeout - $timeout)) seconds"
            } elseif ($service -and $service.Status -eq 'StartPending') {
                Write-Host "    Service status: StartPending (waiting...)" -ForegroundColor Yellow
            } else {
                Write-TestResult "Service Startup" $false "Unexpected service status: $($service.Status)"
                return $false
            }
        }

        if (-not $running) {
            Write-TestResult "Service Startup" $false "Service failed to start within $TestTimeout seconds"
            return $false
        }

        return $true

    } catch {
        Write-TestResult "Service Startup" $false "Exception: $_"
        return $false
    }
}

function Test-ServiceOperation {
    Write-Host "`n🔍 Testing Service Operation..." -ForegroundColor Cyan

    try {
        # Check if service is responding
        $service = Get-Service -Name $ServiceName
        if ($service.Status -ne 'Running') {
            Write-TestResult "Service Status Check" $false "Service not running: $($service.Status)"
            return $false
        }

        Write-TestResult "Service Status Check" $true "Service is running"

        # Test basic service responsiveness
        Start-Sleep -Seconds 5

        $service = Get-Service -Name $ServiceName
        if ($service.Status -eq 'Running') {
            Write-TestResult "Service Stability" $true "Service remained stable for 5 seconds"
        } else {
            Write-TestResult "Service Stability" $false "Service status changed to: $($service.Status)"
            return $false
        }

        # Check Windows Event Log for service messages
        try {
            $events = Get-WinEvent -FilterHashtable @{LogName='Application'; ProviderName='TLSCertMonitor'} -MaxEvents 5 -ErrorAction SilentlyContinue
            if ($events) {
                Write-TestResult "Event Log Integration" $true "Found $($events.Count) event log entries"
            } else {
                Write-TestResult "Event Log Integration" $false "No event log entries found (may be normal for short test)"
            }
        } catch {
            Write-TestResult "Event Log Integration" $false "Could not check event log: $_"
        }

        return $true

    } catch {
        Write-TestResult "Service Operation" $false "Exception: $_"
        return $false
    }
}

function Test-ServiceShutdown {
    Write-Host "`n🛑 Testing Service Shutdown..." -ForegroundColor Cyan

    try {
        # Stop service
        $result = sc.exe stop $ServiceName
        $stopExitCode = $LASTEXITCODE

        if ($stopExitCode -ne 0) {
            Write-TestResult "Service Stop Command" $false "sc.exe stop failed with exit code $stopExitCode"
            return $false
        }

        Write-TestResult "Service Stop Command" $true "Stop command executed"

        # Wait for service to stop
        $timeout = 30
        $stopped = $false

        while ($timeout -gt 0 -and -not $stopped) {
            Start-Sleep -Seconds 2
            $timeout -= 2

            $service = Get-Service -Name $ServiceName -ErrorAction SilentlyContinue
            if ($service -and $service.Status -eq 'Stopped') {
                $stopped = $true
                Write-TestResult "Service Shutdown" $true "Service stopped gracefully in $([int](30 - $timeout)) seconds"
            } elseif ($service -and $service.Status -eq 'StopPending') {
                Write-Host "    Service status: StopPending (waiting...)" -ForegroundColor Yellow
            }
        }

        if (-not $stopped) {
            Write-TestResult "Service Shutdown" $false "Service failed to stop within 30 seconds"
            return $false
        }

        return $true

    } catch {
        Write-TestResult "Service Shutdown" $false "Exception: $_"
        return $false
    }
}

function Remove-TestService {
    Write-Host "`n🧹 Cleaning Up Test Service..." -ForegroundColor Cyan

    try {
        # Ensure service is stopped
        $service = Get-Service -Name $ServiceName -ErrorAction SilentlyContinue
        if ($service -and $service.Status -ne 'Stopped') {
            sc.exe stop $ServiceName | Out-Null
            Start-Sleep -Seconds 5
        }

        # Remove service
        $result = sc.exe delete $ServiceName
        if ($LASTEXITCODE -eq 0) {
            Write-TestResult "Service Removal" $true "Test service removed successfully"
        } else {
            Write-TestResult "Service Removal" $false "Failed to remove test service"
        }
    } catch {
        Write-TestResult "Service Removal" $false "Exception: $_"
    }
}

# Main test execution
try {
    Write-Host "🧪 TLS Certificate Monitor - Windows Service Test Suite" -ForegroundColor Cyan
    Write-Host "=" * 60 -ForegroundColor Cyan
    Write-Host "Binary Path: $BinaryPath" -ForegroundColor Gray
    Write-Host "Config Path: $ConfigPath" -ForegroundColor Gray
    Write-Host ""

    # Prerequisites check
    if (-not (Test-Path $BinaryPath)) {
        Write-Host "❌ Binary not found at: $BinaryPath" -ForegroundColor Red
        Write-Host "Please ensure the binary is installed or specify correct path with -BinaryPath" -ForegroundColor Yellow
        exit 1
    }

    # Check if service already exists
    $existingService = Get-Service -Name $ServiceName -ErrorAction SilentlyContinue
    if ($existingService) {
        Write-Host "⚠️  Service $ServiceName already exists. Removing..." -ForegroundColor Yellow
        Remove-TestService
        Start-Sleep -Seconds 2
    }

    # Run tests
    $testResults = @()

    $testResults += Test-ServiceInstallation
    if ($testResults[-1]) {
        $testResults += Test-ServiceStartup
        if ($testResults[-1]) {
            $testResults += Test-ServiceOperation
            $testResults += Test-ServiceShutdown
        }
    }

    # Cleanup unless skipped
    if (-not $SkipCleanup) {
        Remove-TestService
    }

    # Summary
    $passCount = ($testResults | Where-Object { $_ }).Count
    $totalCount = $testResults.Count

    Write-Host "`n📊 Test Summary" -ForegroundColor Cyan
    Write-Host "=" * 30 -ForegroundColor Cyan
    Write-Host "Tests Passed: $passCount / $totalCount" -ForegroundColor $(if ($passCount -eq $totalCount) { "Green" } else { "Yellow" })

    if ($passCount -eq $totalCount) {
        Write-Host "🎉 All tests passed! Windows service functionality is working correctly." -ForegroundColor Green
        exit 0
    } else {
        Write-Host "⚠️  Some tests failed. Please check the detailed output above." -ForegroundColor Yellow
        exit 1
    }

} catch {
    Write-Host "💥 Test suite failed with exception: $_" -ForegroundColor Red
    if (-not $SkipCleanup) {
        Remove-TestService
    }
    exit 1
}