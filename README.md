# TLS Certificate Monitor

A cross-platform application for monitoring SSL/TLS certificates, providing comprehensive metrics and health status information. Available as pre-compiled binaries for Linux, Windows, and macOS, or as a Python application.

## Features

### 🔍 Certificate Monitoring
- **Multi-format support**: PEM, DER, PKCS#12/PFX certificates
- **Automatic discovery**: Scans configured directories for certificates
- **Security analysis**: Detects weak keys and deprecated algorithms
- **Expiration tracking**: Monitors certificate expiration dates
- **Duplicate detection**: Identifies duplicate certificates

### 📊 Metrics & Monitoring
- **Prometheus metrics**: Complete metrics endpoint at `/metrics`
- **Health status**: JSON health information at `/healthz`
- **Performance metrics**: CPU, memory, and thread monitoring
- **Operational metrics**: Scan duration, parse errors, file counts

### ⚡ Performance & Reliability
- **Concurrent processing**: Multi-worker certificate parsing
- **Intelligent caching**: LRU cache with persistence
- **Hot reload**: Configuration and certificate changes detection
- **Graceful shutdown**: Clean resource management

### 🔧 Configuration
- **YAML configuration**: Flexible configuration file support
- **Environment variables**: Override any setting via environment
- **TLS support**: Optional HTTPS for metrics endpoint
- **Customizable passwords**: P12/PFX password list support

### 🔒 Security Features
- **IP Whitelisting**: Restrict API access to specific IP addresses and networks
- **Input Validation**: Comprehensive validation of file paths and configuration
- **Path Protection**: Blocks access to sensitive system directories
- **Data Redaction**: Sensitive information masked in API responses

## Installation

### 📦 Pre-compiled Binaries (Recommended)

Download the latest release for your platform:

- **Linux (AMD64)**: `linux-amd64.tar.gz`  
- **Windows (AMD64)**: `windows-amd64.tar.gz`
- **macOS (Intel)**: `darwin-amd64.tar.gz`
- **macOS (Apple Silicon)**: `darwin-arm64.tar.gz`

```bash
# Download and extract (replace with your platform)
curl -L https://github.com/brandonhon/tls-cert-monitor/releases/latest/download/linux-amd64.tar.gz | tar -xz
chmod +x tls-cert-monitor
./tls-cert-monitor --help
```

### 🐍 From Source

#### Using Virtual Environment (Recommended)

```bash
# Clone and setup
git clone https://github.com/brandonhon/tls-cert-monitor.git
cd tls-cert-monitor

# Setup development environment
make setup-dev

# Create configuration
make config

# Edit configuration (optional)
nano config.yaml

# Run the application
make run
```

### Using System Python

```bash
# Install dependencies
make install-dev-system

# Create configuration
make config

# Run the application
make run-system
```

### 🐳 Docker Images

Pre-built container images are available supporting Linux AMD64 and ARM64 architectures:

```bash
# Pull and run the latest image
docker run -d \
  --name tls-cert-monitor \
  -p 3200:3200 \
  -v /etc/ssl/certs:/etc/ssl/certs:ro \
  -v ./config.yaml:/app/config.yaml:ro \
  ghcr.io/brandonhon/tls-cert-monitor:latest

# Or use docker-compose
make docker-compose
```

### 🛠️ Development Setup

```bash
# Build and run with Docker Compose
make compose-up

# Or build Docker image locally
make docker-build
make docker-run
```

## Configuration

Create a `config.yaml` file (or copy from `config.example.yaml`):

```yaml
# Server settings
port: 3200
bind_address: "0.0.0.0"

# Certificate directories to monitor
certificate_directories:
  - "/etc/ssl/certs"
  - "/etc/pki/tls/certs"

# Directories to exclude
exclude_directories:
  - "/etc/ssl/certs/private"

# P12/PFX passwords to try
p12_passwords:
  - ""           # No password
  - "changeit"   # Default Java keystore
  - "password"   # Common default

# Scan settings
scan_interval: "5m"
workers: 4

# Logging
log_level: "INFO"
# log_file: "/var/log/tls-monitor.log"

# Features
hot_reload: true
dry_run: false

# Cache settings
cache_dir: "./cache"
cache_ttl: "1h"
cache_max_size: 104857600  # 100MB

# Security settings
enable_ip_whitelist: true
allowed_ips:
  - "127.0.0.1"           # Localhost IPv4
  - "::1"                 # Localhost IPv6  
  - "192.168.1.0/24"      # Local network CIDR
  - "10.0.0.100"          # Specific monitoring server
```

### Environment Variables

Override any configuration setting using environment variables:

```bash
export TLS_MONITOR_PORT=8080
export TLS_MONITOR_LOG_LEVEL=DEBUG
export TLS_MONITOR_CERT_DIRECTORIES="/path1,/path2"
export TLS_MONITOR_WORKERS=8

# Security settings
export TLS_MONITOR_ENABLE_IP_WHITELIST=true
export TLS_MONITOR_ALLOWED_IPS="127.0.0.1,192.168.1.0/24,10.0.0.100"
```

## Security Configuration

### IP Whitelisting

Protect your TLS Certificate Monitor API by restricting access to specific IP addresses and networks:

```yaml
# Enable IP whitelisting (default: true)
enable_ip_whitelist: true

# Allowed IP addresses and networks
allowed_ips:
  - "127.0.0.1"           # Localhost IPv4
  - "::1"                 # Localhost IPv6
  - "192.168.1.0/24"      # Local network (CIDR notation)
  - "10.0.0.0/8"          # Private network range
  - "172.16.0.100"        # Specific server IP
```

**Key Features:**
- Supports both IPv4 and IPv6 addresses
- CIDR network notation for ranges (e.g., `192.168.1.0/24`)
- Localhost (`127.0.0.1`, `::1`) always allowed for health checks
- Detailed logging of blocked access attempts
- 403 Forbidden response for unauthorized IPs

**Environment Variable:**
```bash
export TLS_MONITOR_ENABLE_IP_WHITELIST=true
export TLS_MONITOR_ALLOWED_IPS="127.0.0.1,::1,192.168.1.0/24"
```

### Path Security

The application automatically validates and protects against access to sensitive system directories:

**Forbidden Paths (automatically blocked):**
- `/etc/shadow`, `/etc/passwd` - System password files
- `/proc`, `/sys`, `/dev` - System filesystems  
- `/root/.ssh`, `/home/*/.ssh` - SSH key directories
- `/var/log/auth.log` - Authentication logs

**Input Validation:**
- Certificate directory paths are resolved and validated
- Regex patterns in `exclude_file_patterns` are syntax-checked
- IP addresses are validated using Python's `ipaddress` module

### API Security

**Information Protection:**
- Sensitive data redacted in `/config` endpoint responses
- Certificate directory paths masked (only basename shown)
- P12 passwords and TLS keys completely hidden
- IP whitelist configuration redacted

**Example redacted `/config` response:**
```json
{
  "port": 3200,
  "certificate_directories": ["***/certs", "***/ssl"],
  "p12_passwords": ["***REDACTED*** (4 passwords)"],
  "allowed_ips": ["***REDACTED*** (3 IPs/networks)"],
  "tls_key": "***REDACTED***"
}
```

## API Endpoints

### Metrics Endpoint
- **URL**: `/metrics`
- **Method**: GET
- **Content-Type**: `text/plain; version=0.0.4; charset=utf-8`
- **Description**: Prometheus metrics in text format

### Health Endpoint
- **URL**: `/healthz`
- **Method**: GET
- **Content-Type**: `application/json`
- **Description**: Health status and system information

### Manual Scan
- **URL**: `/scan`
- **Method**: GET
- **Content-Type**: `application/json`
- **Description**: Trigger manual certificate scan

### Configuration
- **URL**: `/config`
- **Method**: GET
- **Content-Type**: `application/json`
- **Description**: Current configuration (sensitive data redacted)

### Cache Operations
- **URL**: `/cache/stats` (GET) - Cache statistics
- **URL**: `/cache/clear` (POST) - Clear cache

## Metrics Reference

### Certificate Metrics
- `ssl_cert_expiration_timestamp` - Certificate expiration time (Unix timestamp)
- `ssl_cert_san_count` - Number of Subject Alternative Names
- `ssl_cert_info` - Certificate information with labels
- `ssl_cert_duplicate_count` - Number of duplicate certificates
- `ssl_cert_issuer_code` - Numeric issuer classification (30=DigiCert, 31=Amazon, 32=Other, 33=Self-signed)

### Security Metrics
- `ssl_cert_weak_key_total` - Certificates with weak cryptographic keys
- `ssl_cert_deprecated_sigalg_total` - Certificates using deprecated signature algorithms

### Operational Metrics
- `ssl_cert_files_total` - Total certificate files processed
- `ssl_certs_parsed_total` - Successfully parsed certificates
- `ssl_cert_parse_errors_total` - Certificate parsing errors
- `ssl_cert_scan_duration_seconds` - Directory scan duration
- `ssl_cert_last_scan_timestamp` - Last successful scan time

### Application Metrics
- `app_memory_bytes` - Application memory usage
- `app_cpu_percent` - CPU usage percentage
- `app_thread_count` - Number of threads
- `app_info` - Application information

## Development

### Available Make Targets

```bash
# Setup and dependencies
make setup-dev          # Complete development setup
make install            # Install dependencies in venv
make install-dev        # Install dev dependencies in venv

# Code quality
make format             # Format code with black and isort
make lint               # Run linting with flake8 and pylint
make type-check         # Run type checking with mypy
make security           # Run security checks with bandit
make check              # Run all code quality checks

# Testing
make test               # Run tests with pytest
make test-coverage      # Run tests with coverage report
make test-watch         # Run tests in watch mode

# Running
make run                # Run with virtual environment
make run-system         # Run with system Python
make run-config         # Run with config file
make run-dev            # Run in development mode

# Building
make build-native       # Build native binary for current platform
make build-dev          # Build development binary
make check-build-deps   # Check build dependencies

# Docker
make docker-build       # Build Docker image
make docker-run         # Run Docker container
make compose-up         # Start with docker-compose
make compose-down       # Stop docker-compose

# Utilities
make clean              # Clean build artifacts
make clean-all          # Clean everything including venv
make info               # Show project information
```

### Project Structure

```
tls-cert-monitor/
├── main.py                      # Application entry point
├── tls_cert_monitor/            # Main package
│   ├── __init__.py
│   ├── config.py                # Configuration management
│   ├── logger.py                # Logging setup
│   ├── cache.py                 # Cache management
│   ├── metrics.py               # Prometheus metrics
│   ├── scanner.py               # Certificate scanner
│   ├── api.py                   # FastAPI application
│   └── hot_reload.py            # Hot reload functionality
├── build/                       # Build configurations
│   ├── Dockerfile.linux         # Linux binary build container
│   └── Dockerfile.windows       # Windows binary build container
├── tests/                       # Test suite
│   ├── test_config.py
│   ├── test_metrics.py
│   └── test_cache.py
├── .github/workflows/           # GitHub Actions workflows
│   └── build.yml                # Multi-platform build and release
├── scripts/                     # Installation and service scripts
│   ├── install-linux-service.sh              # Linux systemd service installer
│   ├── install-windows-service.bat           # Windows service installer (NSSM)
│   ├── install-windows-service-native.bat    # Windows native service installer
│   ├── Install-WindowsService.ps1            # PowerShell Windows service installer
│   ├── install-macos-service.sh              # macOS service installer
│   ├── tls-cert-monitor.service              # systemd service file
│   └── com.tlscertmonitor.service.plist      # macOS LaunchDaemon config
├── docker/                      # Docker development setup
├── config.example.yaml          # Example configuration
├── config.windows.example.yaml  # Windows-specific config example
├── requirements.txt             # Production dependencies
├── requirements-dev.txt         # Development dependencies
├── Makefile                     # Build and development tasks
├── setup.py                     # Package setup
├── pyproject.toml              # Modern Python project config
├── Dockerfile                   # Multi-platform container image
├── docker-compose.yml           # Production docker compose
├── docker-compose.dev.yml       # Development docker compose
└── README.md                   # This file
```

### Testing

Run the test suite:

```bash
# Run all tests
make test

# Run with coverage
make test-coverage

# Run specific test file
python -m pytest tests/test_config.py -v

# Run tests matching pattern
python -m pytest -k "test_cache" -v
```

### Code Quality

Maintain code quality with the included tools:

```bash
# Format code
make format

# Run linters
make lint

# Type checking
make type-check

# Security scan
make security

# Run all checks
make check
```

## Production Deployment

### Linux System Service (systemd)

Install as a Linux systemd service:

#### Installation
```bash
# Download the Linux binary: linux-amd64.tar.gz
tar -xzf linux-amd64.tar.gz

# Run installation script as root
sudo scripts/install-linux-service.sh
```

#### Manual Installation
```bash
# Create service user
sudo groupadd --system tls-monitor
sudo useradd --system --gid tls-monitor --home-dir /var/empty \
    --shell /usr/sbin/nologin --comment "TLS Certificate Monitor Service" tls-monitor

# Install binary and configuration
sudo mkdir -p /usr/local/bin /etc/tls-cert-monitor /var/lib/tls-cert-monitor /var/log/tls-cert-monitor
sudo cp tls-cert-monitor /usr/local/bin/
sudo cp config.yaml /etc/tls-cert-monitor/
sudo chown tls-monitor:tls-monitor /var/lib/tls-cert-monitor /var/log/tls-cert-monitor

# Install systemd service
sudo cp scripts/tls-cert-monitor.service /etc/systemd/system/
sudo systemctl daemon-reload
sudo systemctl enable tls-cert-monitor
sudo systemctl start tls-cert-monitor
```

#### Service Management
```bash
# Check status
sudo systemctl status tls-cert-monitor

# Start/Stop/Restart service
sudo systemctl start tls-cert-monitor
sudo systemctl stop tls-cert-monitor
sudo systemctl restart tls-cert-monitor

# Enable/Disable auto-start
sudo systemctl enable tls-cert-monitor
sudo systemctl disable tls-cert-monitor

# View logs
sudo journalctl -u tls-cert-monitor -f
```

### Windows Service

Install as a Windows service using native Windows service support (recommended) or NSSM.

#### Option 1: Native Windows Service (Recommended)

The application now includes built-in Windows service support without requiring third-party tools:

**Prerequisites:**
- Windows with Administrator privileges
- pywin32 package (automatically included in pre-compiled binaries)

**Installation:**
```cmd
# Run as Administrator
# Using PowerShell (recommended)
.\scripts\Install-WindowsService.ps1

# Or using batch script
scripts\install-windows-service-native.bat
```

**Manual Installation:**
```cmd
# Install service with automatic start
tls-cert-monitor.exe --service-install --config="C:\ProgramData\TLSCertMonitor\config.yaml"

# Install service with manual start
tls-cert-monitor.exe --service-install --service-manual --config="C:\ProgramData\TLSCertMonitor\config.yaml"
```

**Service Management:**
```cmd
# Application commands
tls-cert-monitor.exe --service-start
tls-cert-monitor.exe --service-stop
tls-cert-monitor.exe --service-status
tls-cert-monitor.exe --service-uninstall

# Standard Windows service commands
sc start TLSCertMonitor
sc stop TLSCertMonitor
sc query TLSCertMonitor

# PowerShell commands
Start-Service -Name TLSCertMonitor
Stop-Service -Name TLSCertMonitor
Get-Service -Name TLSCertMonitor
```

#### Option 2: NSSM (Legacy)

If you prefer using NSSM (Non-Sucking Service Manager):

**Prerequisites:**
1. Download [NSSM](https://nssm.cc/download) and add to PATH
2. Download the Windows binary: `windows-amd64.tar.gz`
3. Extract and place the installation script in the same directory

**Installation:**
```cmd
# Run as Administrator
scripts\install-windows-service.bat
```

**Manual NSSM Installation:**
```cmd
# Install NSSM service
nssm install TLSCertMonitor "C:\Program Files\TLSCertMonitor\tls-cert-monitor.exe"
nssm set TLSCertMonitor AppParameters "--config=C:\ProgramData\TLSCertMonitor\config.yaml"
nssm set TLSCertMonitor DisplayName "TLS Certificate Monitor"
nssm set TLSCertMonitor Description "Monitors TLS/SSL certificates and provides Prometheus metrics"
nssm set TLSCertMonitor Start SERVICE_AUTO_START

# Configure logging
nssm set TLSCertMonitor AppStdout "C:\ProgramData\TLSCertMonitor\logs\service.log"
nssm set TLSCertMonitor AppStderr "C:\ProgramData\TLSCertMonitor\logs\service-error.log"

# Start service
nssm start TLSCertMonitor
```

**NSSM Service Management:**
```cmd
# Check status
sc query TLSCertMonitor

# Start/Stop service
sc start TLSCertMonitor
sc stop TLSCertMonitor

# Uninstall service
nssm remove TLSCertMonitor
```

### macOS Service (LaunchDaemon)

Install as a macOS system service using LaunchDaemon:

#### Installation
```bash
# Download the macOS binary: darwin-amd64.tar.gz or darwin-arm64.tar.gz
tar -xzf darwin-amd64.tar.gz  # or darwin-arm64.tar.gz

# Run installation script as root
sudo scripts/install-macos-service.sh
```

#### Manual Installation
```bash
# Create service user
sudo dscl . -create /Groups/_tlscertmonitor
sudo dscl . -create /Groups/_tlscertmonitor PrimaryGroupID 250
sudo dscl . -create /Users/_tlscertmonitor
sudo dscl . -create /Users/_tlscertmonitor UniqueID 250
sudo dscl . -create /Users/_tlscertmonitor PrimaryGroupID 250
sudo dscl . -create /Users/_tlscertmonitor UserShell /usr/bin/false
sudo dscl . -create /Users/_tlscertmonitor NFSHomeDirectory /var/empty

# Install binary and configuration
sudo mkdir -p /usr/local/bin /usr/local/etc/tls-cert-monitor /usr/local/var/{lib,log}/tls-cert-monitor
sudo cp tls-cert-monitor /usr/local/bin/
sudo cp config.yaml /usr/local/etc/tls-cert-monitor/
sudo chown -R _tlscertmonitor:_tlscertmonitor /usr/local/etc/tls-cert-monitor /usr/local/var/{lib,log}/tls-cert-monitor

# Install LaunchDaemon
sudo cp scripts/com.tlscertmonitor.service.plist /Library/LaunchDaemons/
sudo chown root:wheel /Library/LaunchDaemons/com.tlscertmonitor.service.plist
sudo launchctl load /Library/LaunchDaemons/com.tlscertmonitor.service.plist
```

#### Service Management
```bash
# Check status
sudo launchctl list | grep tlscertmonitor

# Start/Stop service
sudo launchctl unload /Library/LaunchDaemons/com.tlscertmonitor.service.plist
sudo launchctl load /Library/LaunchDaemons/com.tlscertmonitor.service.plist

# View logs
sudo log show --predicate 'process == "tls-cert-monitor"' --last 1h
```

### Docker Deployment

```bash
# Build image
docker build -t tls-cert-monitor .

# Run container
docker run -d \
  --name tls-cert-monitor \
  -p 3200:3200 \
  -v /etc/ssl/certs:/etc/ssl/certs:ro \
  -v /etc/pki/tls/certs:/etc/pki/tls/certs:ro \
  -v ./config.yaml:/app/config.yaml:ro \
  tls-cert-monitor
```

### Monitoring Integration

The application provides Prometheus metrics that can be scraped:

```yaml
# prometheus.yml
scrape_configs:
  - job_name: 'tls-cert-monitor'
    static_configs:
      - targets: ['localhost:3200']
    metrics_path: '/metrics'
    scrape_interval: 30s
```

## Security Considerations

- **File Permissions**: Ensure certificate files are readable by the application user
- **TLS Configuration**: Use TLS for the metrics endpoint in production
- **Password Security**: Store P12 passwords securely, consider using environment variables
- **Access Control**: Restrict access to metrics and health endpoints as needed
- **Log Security**: Be cautious about logging sensitive information

## Troubleshooting

### Common Issues

1. **Permission Denied**: Ensure the application has read access to certificate directories
2. **Parse Errors**: Check certificate format and P12 passwords
3. **High Memory Usage**: Adjust cache settings or scan frequency
4. **Port Already in Use**: Change the port in configuration

### Debug Mode

Enable debug logging for troubleshooting:

```yaml
log_level: "DEBUG"
```

Or via environment variable:

```bash
export TLS_MONITOR_LOG_LEVEL=DEBUG
```

## License

MIT License - see LICENSE file for details.

## Contributing

1. Fork the repository
2. Create a feature branch
3. Make your changes
4. Run tests and quality checks: `make check test`
5. Submit a pull request

## Support

- Create an issue for bug reports or feature requests
- Check the documentation for configuration help
- Review logs for troubleshooting information