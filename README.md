# README.md

# TLS Certificate Monitor

A Go-based monitoring tool that scans directories for TLS/SSL certificates and exposes detailed metrics via Prometheus. Monitor certificate health, expiration dates, key strengths, and issuer classifications across your infrastructure.

## Features

### 🔍 **Comprehensive Certificate Discovery**
- **Smart File Detection**: Automatically identifies certificate files by extension and naming patterns
- **Private Key Exclusion**: Intelligently excludes private key files to prevent parsing errors
- **Multi-Format Support**: Handles PEM, DER, CRT, CER, P7B, P12, and other certificate formats
- **Recursive Directory Scanning**: Monitors multiple certificate directories simultaneously

### 📊 **Rich Prometheus Metrics**
- **Certificate Expiration**: Track expiration timestamps for proactive renewal
- **Key Strength Analysis**: Detect weak cryptographic keys (< 2048 bits)
- **Algorithm Security**: Identify deprecated signature algorithms (MD5, SHA1)
- **Subject Alternative Names**: Count and monitor SAN entries
- **Issuer Classification**: Categorize certificates by CA (DigiCert, Amazon, Let's Encrypt, etc.)
- **Duplicate Detection**: Identify identical certificates across directories
- **Operational Metrics**: Scan duration, parse errors, and file counts

### ⚡ **Performance & Reliability**
- **Concurrent Processing**: Configurable worker pools for efficient scanning
- **Intelligent Caching**: File-based caching with TTL to reduce I/O overhead
- **Real-time Monitoring**: File system watching for immediate certificate changes
- **Hot Configuration Reload**: Update settings without restart
- **Graceful Shutdown**: Clean termination with proper resource cleanup

### 🛡️ **Security & Compliance**
- **Path Traversal Protection**: Validates all file paths against configured directories
- **Non-root Execution**: Runs with minimal privileges (user 1001 in containers)
- **TLS-enabled Metrics**: Optional HTTPS for metrics endpoint
- **Comprehensive Logging**: Structured logging with configurable levels

## Quick Start

### Using Docker Compose

```bash
# Clone the repository
git clone https://github.com/brandonhon/tls-cert-monitor.git
cd tls-cert-monitor

# Start with monitoring stack
docker-compose --profile monitoring up -d

# Access Prometheus: http://localhost:9090
# Access Grafana: http://localhost:3000 (admin/admin)
# Access Metrics: http://localhost:3200/metrics
```

### Binary Installation

```bash
# Download latest release
curl -L -o tls-cert-monitor https://github.com/brandonhon/tls-cert-monitor/releases/latest/download/tls-cert-monitor-linux-amd64

# Make executable
chmod +x tls-cert-monitor

# Create configuration
cp example.config.yaml config.yaml

# Edit certificate directories
vim config.yaml

# Run
./tls-cert-monitor -config=config.yaml
```

### Building from Source

```bash
# Clone and build
git clone https://github.com/brandonhon/tls-cert-monitor.git
cd tls-cert-monitor
make build

# Generate example certificates for testing
make example-certs

# Run with development config
make run-dev
```

## Configuration

### Basic Configuration (`config.yaml`)

```yaml
# Server settings
port: 3200
bind_address: "0.0.0.0"

# Certificate monitoring
certificate_directories:
  - "/etc/ssl/certs"
  - "/etc/pki/tls/certs"
  - "/opt/certificates"

# Scan frequency
scan_interval: "5m"

# Performance tuning
workers: 4

# Logging
log_level: "info"
log_file: "/var/log/tls-monitor.log"

# Caching for performance
cache_dir: "./cache"
cache_ttl: "1h"
cache_max_size: 104857600  # 100MB

# Optional TLS for metrics endpoint
# tls_cert: "/path/to/server.crt"
# tls_key: "/path/to/server.key"
```

### Environment Variables

All configuration options can be set via environment variables with the `TLS_MONITOR_` prefix:

```bash
export TLS_MONITOR_PORT=3200
export TLS_MONITOR_LOG_LEVEL=debug
export TLS_MONITOR_CERTIFICATE_DIRECTORIES="/etc/ssl/certs,/opt/certs"
```

### Advanced Configuration

```yaml
# Hot reload configuration changes
hot_reload: true

# Dry run mode (validate config only)
dry_run: false

# Directory exclusion - skip these paths during scanning
exclude_directories:
  - "/etc/ssl/certs/private"    # Skip private key directories
  - "/etc/ssl/certs/backup"     # Skip backup directories
  - "/var/log"                  # Skip log directories

# File patterns (automatically detected)
# Extensions: .pem, .crt, .cer, .cert, .der, .p7b, .p7c, .pfx, .p12
# Patterns: cert, certificate, chain, bundle, ca-cert, cacert

# Private key exclusion (automatic)
# Extensions: .key, .pem.key, .private, .priv
# Patterns: private, *_key, *-key, *key.pem
```

## Key Metrics

### Certificate Health
```prometheus
# Certificate expiration (Unix timestamp)
ssl_cert_expiration_timestamp{path="...", subject="...", issuer="..."}

# Weak cryptographic keys (< 2048 bits)
ssl_cert_weak_key_total

# Deprecated signature algorithms
ssl_cert_deprecated_sigalg_total
```

### Certificate Details
```prometheus
# Subject Alternative Names count
ssl_cert_san_count{path="..."}

# Certificate information
ssl_cert_info{path="...", subject="...", issuer="...", serial="...", signature_algorithm="..."}

# Issuer classification (30=DigiCert, 31=Amazon, 32=Other, 33=Self-signed)
ssl_cert_issuer_code{issuer="...", common_name="...", file_name="..."}
```

### Operational Metrics
```prometheus
# File processing statistics
ssl_cert_files_total
ssl_certs_parsed_total
ssl_cert_parse_errors_total

# Scan performance
ssl_cert_scan_duration_seconds
ssl_cert_last_scan_timestamp

# Duplicate detection
ssl_cert_duplicate_count{fingerprint="..."}
```

## Monitoring Setup

### Prometheus Configuration

```yaml
scrape_configs:
  - job_name: 'tls-cert-monitor'
    static_configs:
      - targets: ['localhost:3200']
    metrics_path: '/metrics'
    scrape_interval: 30s
```

### Sample Grafana Queries

**Certificates Expiring Soon:**
```promql
(ssl_cert_expiration_timestamp - time()) / 86400 < 30
```

**Weak Key Detection:**
```promql
ssl_cert_weak_key_total > 0
```

**Certificate Count by Issuer:**
```promql
count by (issuer) (ssl_cert_info)
```

**Scan Performance:**
```promql
rate(ssl_cert_scan_duration_seconds[5m])
```

## API Endpoints

- **`GET /`** - Web dashboard with configuration overview
- **`GET /metrics`** - Prometheus metrics endpoint
- **`GET /healthz`** - Health check with detailed system status

## Development

### Running Tests

```bash
# Run all tests
make test

# Run with coverage
make test-cover

# Run with race detection
make test-race

# Integration tests
make test-integration
```

### Code Quality

```bash
# Format code
make fmt

# Run linter
make lint

# Run all quality checks
make check
```

### Building

```bash
# Build binary
make build

# Build with race detection
make build-race

# Cross-platform release builds
make release
```

## Docker Usage

### Standalone Container

```bash
docker run -d \
  --name tls-monitor \
  -p 3200:3200 \
  -v /etc/ssl/certs:/etc/ssl/certs:ro \
  -v $(pwd)/config.yaml:/app/config.yaml:ro \
  tls-cert-monitor:latest
```

### With Custom Configuration

```bash
docker run -d \
  --name tls-monitor \
  -p 3200:3200 \
  -v /path/to/certs:/certs:ro \
  -v $(pwd)/config.yaml:/app/config.yaml:ro \
  -e TLS_MONITOR_LOG_LEVEL=debug \
  -e TLS_MONITOR_WORKERS=8 \
  tls-cert-monitor:latest
```

## Security Considerations

### File System Access
- **Read-only mounting**: Mount certificate directories as read-only
- **Path validation**: All paths are validated against configured directories
- **No privilege escalation**: Runs as non-root user (UID 1001)

### Network Security
- **Optional TLS**: Enable HTTPS for metrics endpoint in production
- **Firewall rules**: Restrict access to metrics port (3200)
- **Authentication**: Use reverse proxy for authentication if needed

### Resource Limits
```yaml
# Docker Compose resource limits
deploy:
  resources:
    limits:
      memory: 256M
      cpus: '0.5'
```

## Troubleshooting

### Common Issues

**No certificates found:**
```bash
# Check directory permissions
ls -la /etc/ssl/certs

# Verify configuration
./tls-cert-monitor -config=config.yaml -dry-run

# Enable debug logging
export TLS_MONITOR_LOG_LEVEL=debug
```

**High memory usage:**
```bash
# Reduce cache size
export TLS_MONITOR_CACHE_MAX_SIZE=52428800  # 50MB

# Reduce worker count
export TLS_MONITOR_WORKERS=2
```

**Parse errors:**
```bash
# Check file formats - private keys are automatically excluded
# Invalid certificate files will be logged but won't stop scanning
```

### Debug Mode

```bash
# Enable detailed logging
export TLS_MONITOR_LOG_LEVEL=debug

# Watch file detection in real-time
tail -f /var/log/tls-monitor.log | grep "Excluding\|Including"
```

## Contributing

1. **Fork the repository**
2. **Create feature branch**: `git checkout -b feature/amazing-feature`
3. **Add tests**: Ensure new functionality is tested
4. **Run quality checks**: `make check`
5. **Commit changes**: `git commit -m 'Add amazing feature'`
6. **Push branch**: `git push origin feature/amazing-feature`
7. **Open Pull Request**

### Development Guidelines

- **Test-driven development**: Write tests first
- **Follow existing patterns**: Study similar implementations
- **Document changes**: Update README and comments
- **Performance considerations**: Profile changes if they affect scanning

## License

This project is licensed under the MIT License - see the [LICENSE](LICENSE) file for details.

## Acknowledgments

- **Prometheus**: Metrics collection and alerting
- **Go crypto/x509**: Certificate parsing and validation
- **fsnotify**: File system event monitoring
- **Viper**: Configuration management
- **Zap**: Structured logging

---

**Built with ❤️ for infrastructure security and observability**