#!/usr/bin/env bash
set -euo pipefail

# ---------------------------
# TLS-Cert-Monitor Development Config Generator
# ---------------------------

# Resolve the project root directory based on script location
BASE_DIR="$(cd "$(dirname "$0")/.." && pwd)"
EXAMPLE_DIR="$BASE_DIR/tests/fixtures"
CONFIG_DIR="$EXAMPLE_DIR/configs"
CONFIG_FILE="$CONFIG_DIR/config.dev.yaml"
BINARY_NAME="tls-cert-monitor"

echo "🛠️  Creating development configuration..."

# Ensure the configs directory exists
mkdir -p "$CONFIG_DIR"

# Generate the YAML config
cat > "$CONFIG_FILE" <<EOF
port: 3200
bind_address: "0.0.0.0"

# tls_cert: "/path/to/server.crt"
# tls_key: "/path/to/server.key"

certificate_directories:
  - "tests/fixtures/certs"

exclude_directories:
  - "tests/fixtures/certs/exclude"

exclude_file_patterns:
  - "dhparam.pem"       # Exclude Diffie-Hellman parameter files
  - ".*\\\.key$"         # Exclude private key files
  - ".*backup.*"        # Exclude backup files

p12_passwords:
  - ""                    # Empty password (no password)
  - "changeit"           # Java keystore default
  - "password"           # Common default
  - "123456"             # Common weak password

scan_interval: "5m"
workers: 4
log_level: "INFO"  # DEBUG, INFO, WARNING, ERROR, CRITICAL
# log_file: "/var/log/tls-monitor.log"  # If not set, logs to stdout
dry_run: false
hot_reload: true

cache_type: "memory"       # "memory", "file", or "both"
cache_dir: "./cache"       # Only used when cache_type is "file" or "both"
cache_ttl: "5m"
cache_max_size: 10485760   # 10MB (memory), use 31457280 for file cache (30MB)

# Security settings (disabled for development)
enable_ip_whitelist: false  # Disabled for development - enable in production
allowed_ips:
  - "127.0.0.1"           # Localhost IPv4
  - "::1"                 # Localhost IPv6
  - "192.168.1.0/24"      # Local network for development
EOF

# Success messages
echo "✅ Development configuration created: $CONFIG_FILE"
