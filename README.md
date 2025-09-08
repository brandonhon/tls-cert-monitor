# TLS Certificate Monitor

A cross-platform Python application for monitoring SSL/TLS certificates, providing comprehensive metrics and health status information.

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

## Quick Start

### Using Virtual Environment (Recommended)

```bash
# Clone and setup
git clone <repository-url>
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

### Using Docker

```bash
# Build and run with Docker Compose
make compose-up

# Or build Docker image
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
```

### Environment Variables

Override any configuration setting using environment variables:

```bash
export TLS_MONITOR_PORT=8080
export TLS_MONITOR_LOG_LEVEL=DEBUG
export TLS_MONITOR_CERT_DIRECTORIES="/path1,/path2"
export TLS_MONITOR_WORKERS=8
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
├── main.py                    # Application entry point
├── tls_cert_monitor/          # Main package
│   ├── __init__.py
│   ├── config.py              # Configuration management
│   ├── logger.py              # Logging setup
│   ├── cache.py               # Cache management
│   ├── metrics.py             # Prometheus metrics
│   ├── scanner.py             # Certificate scanner
│   ├── api.py                 # FastAPI application
│   └── hot_reload.py          # Hot reload functionality
├── tests/                     # Test suite
│   ├── test_config.py
│   ├── test_metrics.py
│   └── test_cache.py
├── config.example.yaml        # Example configuration
├── requirements.txt           # Production dependencies
├── requirements-dev.txt       # Development dependencies
├── Makefile                   # Build and development tasks
├── setup.py                   # Package setup
├── pyproject.toml            # Modern Python project config
└── README.md                 # This file
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

### System Service (systemd)

Create `/etc/systemd/system/tls-cert-monitor.service`:

```ini
[Unit]
Description=TLS Certificate Monitor
After=network.target

[Service]
Type=simple
User=tls-monitor
Group=tls-monitor
WorkingDirectory=/opt/tls-cert-monitor
Environment=PATH=/opt/tls-cert-monitor/venv/bin
ExecStart=/opt/tls-cert-monitor/venv/bin/python main.py --config=/etc/tls-cert-monitor/config.yaml
Restart=always
RestartSec=5

[Install]
WantedBy=multi-user.target
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