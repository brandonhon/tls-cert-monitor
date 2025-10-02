# Windows Deployment Guide

This guide covers deploying TLS Certificate Monitor on Windows systems and handling common antivirus issues.

## Quick Start

1. Download the latest `windows-amd64.tar.gz` from [Releases](https://github.com/brandonhon/tls-cert-monitor/releases)
2. Extract the archive to get `tls-cert-monitor.exe`
3. Verify the signature (see below)
4. Run the executable

## Antivirus / Windows Defender Issues

### Common Error Messages

If you encounter errors like:
- `Error, load DLL. ([Error 225] Operation did not complete successfully because the file contains a virus or potentially unwanted software.)`
- Windows Defender quarantines the executable
- Other antivirus software blocks execution

### Why This Happens

1. **Nuitka Compilation**: The binary is compiled with Nuitka, which creates self-extracting executables
2. **Cryptographic Libraries**: Includes cryptography libraries that may appear suspicious
3. **Unknown Publisher**: The executable may not be widely recognized by reputation systems
4. **Packing Behavior**: Self-extracting behavior can trigger heuristic detection

### Solutions

#### 1. Verify the Signature (Recommended)

All binaries are signed with Sigstore cosign. Verify authenticity:

```powershell
# Install cosign first (see https://docs.sigstore.dev/cosign/installation/)
cosign verify-blob --certificate tls-cert-monitor.exe.crt --signature tls-cert-monitor.exe.sig --certificate-identity-regexp 'https://github.com/brandonhon/tls-cert-monitor' --certificate-oidc-issuer 'https://token.actions.githubusercontent.com' tls-cert-monitor.exe
```

#### 2. Windows Defender Exclusions

**Method 1: PowerShell (Run as Administrator)**
```powershell
# Add file exclusion
Add-MpPreference -ExclusionPath "C:\path\to\tls-cert-monitor.exe"

# Add directory exclusion
Add-MpPreference -ExclusionPath "C:\path\to\tls-cert-monitor\"

# Add temporary directory exclusion (where Nuitka extracts)
Add-MpPreference -ExclusionPath "C:\opt\tls-cert-monitor\tmp"
```

**Method 2: Windows Security GUI**
1. Open Windows Security (Start → Settings → Update & Security → Windows Security)
2. Go to "Virus & threat protection"
3. Click "Manage settings" under "Virus & threat protection settings"
4. Scroll down to "Exclusions" and click "Add or remove exclusions"
5. Click "Add an exclusion" and select "File"
6. Navigate to and select `tls-cert-monitor.exe`

#### 3. Third-Party Antivirus

For other antivirus software:
1. Check vendor documentation for exclusion procedures
2. Add both the executable and temp directory to exclusions
3. Consider adding the entire application directory
4. Some enterprise antivirus may require IT administrator assistance

#### 4. Enterprise Environments

In enterprise environments:
1. Contact your IT administrator
2. Provide the signature verification commands above
3. Request whitelisting for the application
4. Consider running from a approved software location

## Windows Service Installation

### Prerequisites

1. Run Command Prompt or PowerShell as Administrator
2. Ensure exclusions are configured (see above)

### Enhanced Service Support

The application now includes **native Windows service detection and handling**. When running as a service, it automatically:

- ✅ Detects Windows service environment
- ✅ Configures proper startup timing to prevent 1053 errors
- ✅ Sets up Windows Event Log integration
- ✅ Handles service shutdown signals gracefully
- ✅ Manages async event loops in service context

### Installation Commands

```powershell
# Install service with automatic start using PowerShell
$binaryPath = "C:\path\to\tls-cert-monitor.exe --config C:\path\to\config.yaml"
sc.exe create TLSCertMonitor binPath= $binaryPath DisplayName= "TLS Certificate Monitor" start= auto

# Start the service (now with enhanced startup coordination)
sc.exe start TLSCertMonitor

# Check service status
sc.exe query TLSCertMonitor

# Or use PowerShell cmdlets
Get-Service TLSCertMonitor
```

### Service Behavior

When the application detects it's running as a Windows service:

1. **Startup Coordination**: Uses threading and event coordination to signal successful startup to SCM within 30 seconds
2. **Signal Handling**: Properly responds to service stop/shutdown requests
3. **Event Logging**: Automatically logs to Windows Event Log (Application log, source: TLSCertMonitor)
4. **Environment Setup**: Configures working directory, temp paths, and logging for service context

### Troubleshooting Service Installation

If service installation fails:

1. **Check Administrator Rights**: Ensure running as Administrator
2. **Antivirus Interference**: Temporarily disable real-time protection during installation
3. **Service Dependencies**: Ensure required Windows services are running
4. **Firewall**: Configure Windows Firewall to allow the application

## Configuration for Windows

### Sample Configuration

Create `config.yaml`:

```yaml
directories:
  - path: "C:\\certs"
    recursive: true
  - path: "C:\\ProgramData\\certificates"
    recursive: false

server:
  port: 8080
  bind_address: "0.0.0.0"

logging:
  level: "INFO"
  file: "C:\\logs\\tls-cert-monitor.log"

cache:
  enabled: true
  directory: "C:\\ProgramData\\tls-cert-monitor\\cache"
```

### Windows-Specific Paths

- **Logs**: `C:\logs\` or `C:\ProgramData\tls-cert-monitor\logs\`
- **Cache**: `C:\ProgramData\tls-cert-monitor\cache\`
- **Config**: Same directory as executable or `C:\ProgramData\tls-cert-monitor\`
- **Temp**: `C:\opt\tls-cert-monitor\tmp` (automatically created)

## Performance Considerations

### Windows Defender Impact

1. **Real-time Protection**: May slow initial startup
2. **Exclusions**: Recommended for production deployments
3. **Scheduled Scans**: Exclude application directories

### File System Permissions

Ensure the service account has:
- Read access to certificate directories
- Write access to log and cache directories
- Execute permissions on the binary

## Updating

1. Stop the service: `sc.exe stop TLSCertMonitor`
2. Download new version
3. Verify signature
4. Replace executable
5. Start the service: `sc.exe start TLSCertMonitor`

## Getting Help

If you continue to experience issues:

1. Check the [Issues](https://github.com/brandonhon/tls-cert-monitor/issues) page
2. Provide your Windows version and antivirus software details
3. Include any error messages or logs
4. Mention if you've followed the signature verification steps

## Security Best Practices

1. **Always verify signatures** before running
2. **Download only from official releases**
3. **Use HTTPS** when downloading
4. **Keep antivirus updated** but add appropriate exclusions
5. **Monitor logs** for suspicious activity
6. **Use minimal permissions** for service accounts