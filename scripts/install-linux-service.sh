#!/bin/bash
# TLS Certificate Monitor - Linux systemd Service Installation Script
# This script installs the TLS Certificate Monitor as a Linux systemd service

set -e

# Configuration
SERVICE_NAME="tls-cert-monitor"
SERVICE_USER="tls-monitor"
SERVICE_GROUP="tls-monitor"
INSTALL_DIR="/usr/local/bin"
CONFIG_DIR="/etc/tls-cert-monitor"
DATA_DIR="/var/lib/tls-cert-monitor"
LOG_DIR="/var/log/tls-cert-monitor"
SYSTEMD_DIR="/etc/systemd/system"
SERVICE_FILE="${SYSTEMD_DIR}/${SERVICE_NAME}.service"

echo "==========================================="
echo "TLS Certificate Monitor Service Installer"
echo "==========================================="
echo

# Check if running as root
if [[ $EUID -ne 0 ]]; then
    echo "ERROR: This script must be run as root (use sudo)"
    echo "Usage: sudo $0"
    exit 1
fi

# Detect system type
if command -v systemctl >/dev/null 2>&1; then
    echo "Detected systemd-based Linux system"
else
    echo "ERROR: systemd not found. This script requires a systemd-based Linux distribution."
    exit 1
fi

echo "Installing TLS Certificate Monitor as a Linux systemd service..."
echo

# Check if binary exists
if [[ ! -f "tls-cert-monitor" ]]; then
    echo "ERROR: tls-cert-monitor binary not found in current directory"
    echo "Please run this script from the directory containing the binary"
    exit 1
fi

# Stop existing service if running
if systemctl is-active --quiet "$SERVICE_NAME"; then
    echo "Stopping existing service..."
    systemctl stop "$SERVICE_NAME"
fi

# Create service user and group if they don't exist
echo "Creating service user and group..."
if ! getent group "$SERVICE_GROUP" >/dev/null 2>&1; then
    echo "Creating group '$SERVICE_GROUP'..."
    groupadd --system "$SERVICE_GROUP"
fi

if ! getent passwd "$SERVICE_USER" >/dev/null 2>&1; then
    echo "Creating user '$SERVICE_USER'..."
    useradd --system --gid "$SERVICE_GROUP" --home-dir /var/empty \
        --shell /usr/sbin/nologin --comment "TLS Certificate Monitor Service" \
        "$SERVICE_USER"
fi

# Create directories
echo "Creating directories..."
mkdir -p "$INSTALL_DIR"
mkdir -p "$CONFIG_DIR"
mkdir -p "$DATA_DIR"
mkdir -p "$LOG_DIR"
mkdir -p "$SYSTEMD_DIR"

# Install binary
echo "Installing binary..."
cp "tls-cert-monitor" "$INSTALL_DIR/"
chown root:root "$INSTALL_DIR/tls-cert-monitor"
chmod 755 "$INSTALL_DIR/tls-cert-monitor"

# Install configuration
echo "Installing configuration..."
if [[ -f "config.yaml" ]]; then
    cp "config.yaml" "$CONFIG_DIR/"
elif [[ -f "config.example.yaml" ]]; then
    cp "config.example.yaml" "$CONFIG_DIR/config.yaml"
    echo "Configuration template installed. Please edit $CONFIG_DIR/config.yaml"
else
    echo "WARNING: No configuration file found. You'll need to create $CONFIG_DIR/config.yaml manually"
fi

# Set permissions on directories
echo "Setting permissions..."
chown root:root "$CONFIG_DIR"
chmod 755 "$CONFIG_DIR"
if [[ -f "$CONFIG_DIR/config.yaml" ]]; then
    chown root:$SERVICE_GROUP "$CONFIG_DIR/config.yaml"
    chmod 640 "$CONFIG_DIR/config.yaml"
fi

chown $SERVICE_USER:$SERVICE_GROUP "$DATA_DIR"
chown $SERVICE_USER:$SERVICE_GROUP "$LOG_DIR"
chmod 755 "$DATA_DIR"
chmod 755 "$LOG_DIR"

# Install systemd service file
echo "Installing systemd service..."
if [[ -f "scripts/tls-cert-monitor.service" ]]; then
    cp "scripts/tls-cert-monitor.service" "$SERVICE_FILE"
elif [[ -f "tls-cert-monitor.service" ]]; then
    cp "tls-cert-monitor.service" "$SERVICE_FILE"
else
    echo "ERROR: systemd service file not found"
    exit 1
fi

chown root:root "$SERVICE_FILE"
chmod 644 "$SERVICE_FILE"

# Reload systemd and enable service
echo "Reloading systemd configuration..."
systemctl daemon-reload

echo "Enabling service to start on boot..."
systemctl enable "$SERVICE_NAME"

# Start the service
echo "Starting service..."
systemctl start "$SERVICE_NAME"

# Wait a moment and check status
sleep 3

if systemctl is-active --quiet "$SERVICE_NAME"; then
    echo
    echo "✅ Service installed and started successfully!"
    echo
    echo "Service Details:"
    echo "  Name: $SERVICE_NAME"
    echo "  User: $SERVICE_USER"
    echo "  Binary: $INSTALL_DIR/tls-cert-monitor"
    echo "  Config: $CONFIG_DIR/config.yaml"
    echo "  Data: $DATA_DIR"
    echo "  Logs: $LOG_DIR"
    echo "  Service File: $SERVICE_FILE"
    echo
    echo "Service Management Commands:"
    echo "  Check status:    sudo systemctl status $SERVICE_NAME"
    echo "  Start service:   sudo systemctl start $SERVICE_NAME"
    echo "  Stop service:    sudo systemctl stop $SERVICE_NAME"
    echo "  Restart service: sudo systemctl restart $SERVICE_NAME"
    echo "  Reload config:   sudo systemctl reload $SERVICE_NAME"
    echo "  Enable startup:  sudo systemctl enable $SERVICE_NAME"
    echo "  Disable startup: sudo systemctl disable $SERVICE_NAME"
    echo
    echo "Logs:"
    echo "  View logs:       sudo journalctl -u $SERVICE_NAME -f"
    echo "  Recent logs:     sudo journalctl -u $SERVICE_NAME --since '1 hour ago'"
    echo "  All logs:        sudo journalctl -u $SERVICE_NAME --no-pager"
    echo
    echo "The service is now running and will start automatically on system boot."
    echo
    echo "Current status:"
    systemctl status "$SERVICE_NAME" --no-pager -l
else
    echo "❌ Service installation completed but service failed to start."
    echo "Check the logs for details:"
    echo "  sudo journalctl -u $SERVICE_NAME --no-pager -l"
    echo "  sudo systemctl status $SERVICE_NAME"
    exit 1
fi