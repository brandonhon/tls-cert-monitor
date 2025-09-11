#!/bin/bash
# TLS Certificate Monitor - macOS LaunchDaemon Installation Script
# This script installs the TLS Certificate Monitor as a macOS system service

set -e

# Configuration
SERVICE_NAME="com.tlscertmonitor.service"
SERVICE_USER="_tlscertmonitor"
SERVICE_GROUP="_tlscertmonitor"
INSTALL_DIR="/usr/local/bin"
CONFIG_DIR="/usr/local/etc/tls-cert-monitor"
DATA_DIR="/usr/local/var/lib/tls-cert-monitor"
LOG_DIR="/usr/local/var/log/tls-cert-monitor"
PLIST_PATH="/Library/LaunchDaemons/${SERVICE_NAME}.plist"

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

echo "Installing TLS Certificate Monitor as a macOS system service..."
echo

# Check if binary exists
if [[ ! -f "tls-cert-monitor" ]]; then
    echo "ERROR: tls-cert-monitor binary not found in current directory"
    echo "Please run this script from the directory containing the binary"
    exit 1
fi

# Stop existing service if running
if launchctl list | grep -q "$SERVICE_NAME"; then
    echo "Stopping existing service..."
    launchctl unload "$PLIST_PATH" 2>/dev/null || true
    sleep 2
fi

# Create service user and group if they don't exist
echo "Creating service user and group..."
if ! dscl . -read /Groups/$SERVICE_GROUP &>/dev/null; then
    # Find next available GID starting from 200
    GID=200
    while dscl . -read /Groups -q | grep -q "PrimaryGroupID: $GID"; do
        ((GID++))
    done
    
    echo "Creating group '$SERVICE_GROUP' with GID $GID..."
    dscl . -create /Groups/$SERVICE_GROUP
    dscl . -create /Groups/$SERVICE_GROUP PrimaryGroupID $GID
    dscl . -create /Groups/$SERVICE_GROUP Password "*"
    dscl . -create /Groups/$SERVICE_GROUP RealName "TLS Certificate Monitor Service"
fi

if ! dscl . -read /Users/$SERVICE_USER &>/dev/null; then
    # Find next available UID starting from 200
    UID=200
    while dscl . -read /Users -q | grep -q "UniqueID: $UID"; do
        ((UID++))
    done
    
    GID=$(dscl . -read /Groups/$SERVICE_GROUP PrimaryGroupID | awk '{print $2}')
    
    echo "Creating user '$SERVICE_USER' with UID $UID..."
    dscl . -create /Users/$SERVICE_USER
    dscl . -create /Users/$SERVICE_USER UniqueID $UID
    dscl . -create /Users/$SERVICE_USER PrimaryGroupID $GID
    dscl . -create /Users/$SERVICE_USER UserShell /usr/bin/false
    dscl . -create /Users/$SERVICE_USER NFSHomeDirectory /var/empty
    dscl . -create /Users/$SERVICE_USER Password "*"
    dscl . -create /Users/$SERVICE_USER RealName "TLS Certificate Monitor Service"
fi

# Create directories
echo "Creating directories..."
mkdir -p "$INSTALL_DIR"
mkdir -p "$CONFIG_DIR"
mkdir -p "$DATA_DIR"
mkdir -p "$LOG_DIR"

# Install binary
echo "Installing binary..."
cp "tls-cert-monitor" "$INSTALL_DIR/"
chown root:wheel "$INSTALL_DIR/tls-cert-monitor"
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
chown -R $SERVICE_USER:$SERVICE_GROUP "$CONFIG_DIR"
chown -R $SERVICE_USER:$SERVICE_GROUP "$DATA_DIR"
chown -R $SERVICE_USER:$SERVICE_GROUP "$LOG_DIR"
chmod -R 755 "$CONFIG_DIR"
chmod -R 755 "$DATA_DIR"
chmod -R 755 "$LOG_DIR"

# Install plist file
echo "Installing LaunchDaemon..."
if [[ -f "scripts/com.tlscertmonitor.service.plist" ]]; then
    cp "scripts/com.tlscertmonitor.service.plist" "$PLIST_PATH"
elif [[ -f "com.tlscertmonitor.service.plist" ]]; then
    cp "com.tlscertmonitor.service.plist" "$PLIST_PATH"
else
    echo "ERROR: LaunchDaemon plist file not found"
    exit 1
fi

chown root:wheel "$PLIST_PATH"
chmod 644 "$PLIST_PATH"

# Load and start the service
echo "Loading and starting service..."
launchctl load "$PLIST_PATH"
sleep 3

# Check service status
if launchctl list | grep -q "$SERVICE_NAME"; then
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
    echo
    echo "Service Management Commands:"
    echo "  Check status:    sudo launchctl list | grep tlscertmonitor"
    echo "  Stop service:    sudo launchctl unload $PLIST_PATH"
    echo "  Start service:   sudo launchctl load $PLIST_PATH"
    echo "  Restart service: sudo launchctl unload $PLIST_PATH && sudo launchctl load $PLIST_PATH"
    echo
    echo "Logs:"
    echo "  Service output:  $LOG_DIR/service.log"
    echo "  Service errors:  $LOG_DIR/service-error.log"
    echo "  System logs:     sudo log show --predicate 'process == \"tls-cert-monitor\"'"
    echo
    echo "The service will automatically start on system boot."
else
    echo "❌ Service installation failed. Check the logs for details:"
    echo "  sudo log show --predicate 'process == \"launchctl\"' --last 5m"
    exit 1
fi