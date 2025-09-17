# TLS Certificate Monitor - Ansible Commands

Quick reference for deploying TLS Certificate Monitor using Ansible on Linux and Windows hosts.

## Prerequisites

- Ansible 2.12+
- SSH access to target hosts
- Inventory file configured (`ansible/inventory/hosts.yml`)

## Basic Deployment Commands

### Deploy to All Hosts
```bash
ansible-playbook ansible/playbooks/site.yml
```

### Deploy to Specific Groups
```bash
# Linux servers only
ansible-playbook ansible/playbooks/site.yml --limit linux_servers

# Windows servers only
ansible-playbook ansible/playbooks/site.yml --limit windows_servers
```

### Deploy to Specific Host
```bash
ansible-playbook ansible/playbooks/site.yml --limit webserver01
```

## Configuration Options

### Deploy with Custom Variables
```bash
# Custom port and scan interval
ansible-playbook ansible/playbooks/site.yml -e "service_port=8080 scan_interval_seconds=1800"

# Custom log level
ansible-playbook ansible/playbooks/site.yml -e "log_level=DEBUG"

# Multiple custom settings
ansible-playbook ansible/playbooks/site.yml \
  -e "service_port=9090 log_level=INFO scan_workers=8"
```

### IP Whitelisting Configuration
```bash
# Enable IP whitelisting with default IPs
ansible-playbook ansible/playbooks/site.yml -e "enable_ip_whitelist=true"

# Custom allowed IPs
ansible-playbook ansible/playbooks/site.yml \
  -e "enable_ip_whitelist=true" \
  -e "allowed_ips=['192.168.1.0/24','10.0.0.100','203.0.113.50']"

# Localhost only access
ansible-playbook ansible/playbooks/site.yml \
  -e "enable_ip_whitelist=true" \
  -e "allowed_ips=['127.0.0.1','::1']"
```

### TLS/SSL Configuration
```bash
# Deploy with self-signed certificates
ansible-playbook ansible/playbooks/site.yml -e "enable_tls=true"

# Deploy with custom certificates
ansible-playbook ansible/playbooks/site.yml \
  -e "enable_tls=true tls_cert_source=files" \
  -e "tls_cert_file_local=/path/to/cert.pem tls_key_file_local=/path/to/key.pem"
```

## Authentication Methods

### Password Authentication
```bash
# Interactive password prompts (recommended)
ansible-playbook ansible/playbooks/site.yml --ask-pass --ask-become-pass

# SSH password only
ansible-playbook ansible/playbooks/site.yml --ask-pass

# Sudo password only
ansible-playbook ansible/playbooks/site.yml --ask-become-pass
```

### Using Vault for Passwords
```bash
# Create vault file
ansible-vault create ansible/group_vars/all/vault.yml

# Deploy with vault
ansible-playbook ansible/playbooks/site.yml --ask-vault-pass
```

## Inventory-Specific Deployments

### Environment-Specific Inventories
```bash
# Production environment
ansible-playbook ansible/playbooks/site.yml -i ansible/inventory/production.yml

# Staging environment
ansible-playbook ansible/playbooks/site.yml -i ansible/inventory/staging.yml

# Development environment
ansible-playbook ansible/playbooks/site.yml -i ansible/inventory/development.yml
```

## Dry Run and Verification

### Check Mode (Dry Run)
```bash
# Dry run - show what would be changed
ansible-playbook ansible/playbooks/site.yml --check

# Dry run with specific group
ansible-playbook ansible/playbooks/site.yml --check --limit linux_servers
```

### Verbose Output
```bash
# Basic verbose output
ansible-playbook ansible/playbooks/site.yml -v

# More verbose output
ansible-playbook ansible/playbooks/site.yml -vv

# Maximum verbosity
ansible-playbook ansible/playbooks/site.yml -vvv
```

### Connectivity Testing
```bash
# Test SSH connectivity
ansible all -m ping

# Test specific group
ansible linux_servers -m ping
ansible windows_servers -m ping

# Test Windows connectivity
ansible windows_servers -m win_ping
```

## Uninstallation Commands

### Basic Uninstall
```bash
# Uninstall from all hosts (preserves config, logs, user)
ansible-playbook ansible/playbooks/uninstall.yml

# Uninstall from specific group
ansible-playbook ansible/playbooks/uninstall.yml --limit linux_servers
ansible-playbook ansible/playbooks/uninstall.yml --limit windows_servers
```

### Advanced Uninstall Options
```bash
# Remove configuration files
ansible-playbook ansible/playbooks/uninstall.yml -e "remove_config=true"

# Remove log files
ansible-playbook ansible/playbooks/uninstall.yml -e "remove_logs=true"

# Remove service user (Linux only)
ansible-playbook ansible/playbooks/uninstall.yml -e "remove_user=true"

# Complete removal
ansible-playbook ansible/playbooks/uninstall.yml \
  -e "remove_config=true remove_logs=true remove_user=true"

# Skip confirmation prompt
ansible-playbook ansible/playbooks/uninstall.yml -e "confirm_uninstall=false"
```

### Uninstall with Authentication
```bash
# Uninstall with password prompts
ansible-playbook ansible/playbooks/uninstall.yml --ask-pass --ask-become-pass

# Uninstall with vault
ansible-playbook ansible/playbooks/uninstall.yml --ask-vault-pass
```

## Combined Commands

### Complete Deployment Examples
```bash
# Linux servers with IP whitelisting and custom scan interval
ansible-playbook ansible/playbooks/site.yml --limit linux_servers \
  -e "enable_ip_whitelist=true scan_interval_seconds=1800" \
  -e "allowed_ips=['192.168.0.0/16','10.0.0.0/8']" \
  --ask-pass --ask-become-pass

# Windows servers with TLS and custom port
ansible-playbook ansible/playbooks/site.yml --limit windows_servers \
  -e "enable_tls=true service_port=8443" \
  --ask-pass

# Production deployment with vault and specific inventory
ansible-playbook ansible/playbooks/site.yml \
  -i ansible/inventory/production.yml \
  -e "log_level=WARN scan_interval_seconds=3600" \
  --ask-vault-pass

# Development deployment with debug logging
ansible-playbook ansible/playbooks/site.yml \
  -i ansible/inventory/development.yml \
  -e "log_level=DEBUG scan_interval_seconds=300" \
  --ask-pass --ask-become-pass
```

## Service Management Commands

### Linux Service Management
```bash
# Check service status
ansible linux_servers -m shell -a "systemctl status tls-cert-monitor"

# Restart service
ansible linux_servers -m shell -a "systemctl restart tls-cert-monitor" --become

# View logs
ansible linux_servers -m shell -a "journalctl -u tls-cert-monitor --no-pager -n 20"
```

### Windows Service Management
```bash
# Check service status
ansible windows_servers -m win_shell -a "Get-Service tls-cert-monitor"

# Restart service
ansible windows_servers -m win_shell -a "Restart-Service tls-cert-monitor"

# View logs
ansible windows_servers -m win_shell -a "Get-Content 'C:\ProgramData\tls-cert-monitor\logs\service.log' -Tail 20"
```

## Verification Commands

### Application Health Check
```bash
# Test HTTP endpoints
ansible all -m uri -a "url=http://{{ ansible_host }}:9090/healthz"

# Test HTTPS endpoints (when TLS enabled)
ansible all -m uri -a "url=https://{{ ansible_host }}:9090/healthz validate_certs=no"

# Check metrics endpoint
ansible all -m uri -a "url=http://{{ ansible_host }}:9090/metrics"
```

### File and Permission Verification
```bash
# Check binary permissions (Linux)
ansible linux_servers -m shell -a "ls -la /opt/tls-cert-monitor/"

# Check configuration files (Linux)
ansible linux_servers -m shell -a "ls -la /etc/tls-cert-monitor/"

# Check Windows installation
ansible windows_servers -m win_shell -a "Get-ChildItem 'C:\Program Files\tls-cert-monitor\'"
```

## Quick Reference

| Command | Description |
|---------|-------------|
| `ansible-playbook ansible/playbooks/site.yml` | Basic deployment |
| `ansible-playbook ansible/playbooks/site.yml --limit linux_servers` | Linux only |
| `ansible-playbook ansible/playbooks/site.yml --limit windows_servers` | Windows only |
| `ansible-playbook ansible/playbooks/site.yml --check` | Dry run |
| `ansible-playbook ansible/playbooks/site.yml --ask-pass --ask-become-pass` | With password prompts |
| `ansible-playbook ansible/playbooks/uninstall.yml` | Basic uninstall |
| `ansible all -m ping` | Test connectivity |
| `ansible linux_servers -m shell -a "systemctl status tls-cert-monitor"` | Check Linux service |
| `ansible windows_servers -m win_shell -a "Get-Service tls-cert-monitor"` | Check Windows service |