#!/usr/bin/env bash
set -euo pipefail

# ---------------------------
# TLS-Cert-Monitor Development Config Generator
# ---------------------------

# Resolve the project root directory based on script location
BASE_DIR="$(cd "$(dirname "$0")/.." && pwd)"
EXAMPLE_DIR="$BASE_DIR/test/fixtures"
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
  - "$EXAMPLE_DIR/certs"

exclude_directories:
  - "$EXAMPLE_DIR/certs/exclude"

scan_interval: "1m"
workers: 4
log_level: "info"    # debug, info, warn, error
dry_run: false
hot_reload: true
cache_dir: "./cache"
cache_ttl: "1h"
cache_max_size: 104857600  # 100MB
EOF

# Success messages
echo "✅ Development configuration created: $CONFIG_FILE"
echo "📝 Use with: ./build/$BINARY_NAME -config=$CONFIG_FILE"
