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

certificate_directories:
  - "tests/fixtures/certs"

exclude_directories:
  - "tests/fixtures/certs/exclude"

p12_passwords:
  - ""                   # Empty password (no password)
  - "changeit"           # Java keystore default
  - "password"           # Common default
  - "123456"             # Common weak password

scan_interval: "5m"
workers: 4
log_level: "INFO"  # DEBUG, INFO, WARNING, ERROR, CRITICAL
dry_run: false
hot_reload: true
cache_dir: "./cache"
cache_ttl: "1h"
cache_max_size: 104857600  # 100MB in bytes
EOF

# Success messages
echo "✅ Development configuration created: $CONFIG_FILE"
echo "📝 Use with: ./build/$BINARY_NAME -config=$CONFIG_FILE"