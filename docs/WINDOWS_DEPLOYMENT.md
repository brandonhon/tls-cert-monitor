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

### Native Windows Service Support (Nuitka-winsvc)

The Windows binary is compiled with **Nuitka-winsvc** and includes native Windows service support built directly into the executable. No external scripts or dependencies are required.

**Key Features:**
- ✅ **Built-in service support**: Native Windows service functionality
- ✅ **Dual functionality**: Same executable works as service and console application
- ✅ **Simple installation**: No external scripts required
- ✅ **Config path support**: Pass configuration file during service installation
- ✅ **Administrator privileges**: Required only for installation/uninstallation

### Installation Commands (Simple)

```powershell
# Basic service installation
.\tls-cert-monitor.exe install

# Install service with custom config path
.\tls-cert-monitor.exe install --config "C:\path\to\config.yaml"

# Uninstall service
.\tls-cert-monitor.exe uninstall
```

### Service Management

```powershell
# Install service
.\tls-cert-monitor.exe install

# Uninstall service
.\tls-cert-monitor.exe uninstall

# Start/stop service using Windows built-in commands
sc start TLSCertMonitor
sc stop TLSCertMonitor
sc query TLSCertMonitor

# PowerShell service management
Start-Service -Name TLSCertMonitor
Stop-Service -Name TLSCertMonitor
Get-Service -Name TLSCertMonitor
```

### Console Mode

```powershell
# Run in console mode (not as service)
.\tls-cert-monitor.exe --config config.yaml
.\tls-cert-monitor.exe --dry-run
.\tls-cert-monitor.exe --help
```

### Service Behavior

The Nuitka-winsvc compiled service automatically:

1. **Service Detection**: Automatically detects when running as a Windows service
2. **Startup Coordination**: Handles proper startup timing to prevent 1053 errors
3. **Signal Handling**: Properly responds to service stop/shutdown requests
4. **Event Logging**: Integrated Windows Event Log support
5. **Configuration**: Uses config path passed during installation or default locations

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

### Service Mode

1. Uninstall service: `.\tls-cert-monitor.exe uninstall`
2. Download new version
3. Verify signature
4. Replace executable
5. Install service: `.\tls-cert-monitor.exe install --config "C:\path\to\config.yaml"`
6. Start service: `sc.exe start TLSCertMonitor`

### Alternative (Manual Service Management)

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