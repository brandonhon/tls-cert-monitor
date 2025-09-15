# TLS Certificate Monitor Ansible Deployment

This Ansible playbook automates the deployment of [tls-cert-monitor](https://github.com/brandonhon/tls-cert-monitor) across Linux and Windows hosts.

## Features

- **Cross-platform support**: Linux and Windows hosts
- **Automatic binary download**: Pulls latest release from GitHub
- **OS-specific configuration**: Separate templates for Linux and Windows
- **Service management**: systemd for Linux, native Windows service or NSSM for Windows
- **Security hardening**: Dedicated service user, filesystem restrictions
- **Monitoring ready**: Health checks and metrics endpoints

## Requirements

### Control Node
- Ansible 2.12+
- Python 3.8+

### Target Hosts

#### Linux
- SSH access with sudo privileges
- systemd-based distribution
- `tar` and `gzip` packages

#### Windows
- SSH access (OpenSSH Server)
- PowerShell 5.1+
- Administrator privileges

## Directory Structure

```
ansible/
├── ansible.cfg              # Ansible configuration
├── playbooks/
│   └── site.yml            # Main playbook
├── roles/
│   └── tls-cert-monitor/
│       ├── defaults/        # Default variables
│       ├── tasks/           # Task files
│       ├── templates/       # Jinja2 templates
│       ├── handlers/        # Event handlers
│       └── vars/           # Role variables
├── inventory/
│   └── hosts.yml           # Inventory example
└── group_vars/
    ├── linux_servers.yml   # Linux group variables
    └── windows_servers.yml # Windows group variables
```

## Quick Start

### 1. Setup Inventory

Copy and customize the inventory file:

```bash
cp inventory/hosts.yml inventory/production.yml
```

Edit `inventory/production.yml` with your hosts:

```yaml
all:
  children:
    linux_servers:
      hosts:
        webserver01:
          ansible_host: 192.168.1.10
          ansible_user: ubuntu
          ansible_ssh_private_key_file: ~/.ssh/id_rsa

    windows_servers:
      hosts:
        winserver01:
          ansible_host: 192.168.1.30
          ansible_user: ansible
          ansible_password: "{{ vault_windows_password }}"
          ansible_connection: ssh
          ansible_shell_type: powershell
```

### 2. Configure Variables

Edit group variables in `group_vars/`:

```yaml
# group_vars/linux_servers.yml
cert_dirs_linux:
  - /etc/ssl/certs
  - /etc/nginx/ssl
  - /opt/certificates

# group_vars/windows_servers.yml
cert_dirs_windows:
  - C:\inetpub\ssl
  - C:\certificates
```

### 3. Run Deployment

```bash
# Deploy to all hosts
ansible-playbook playbooks/site.yml

# Deploy to specific group
ansible-playbook playbooks/site.yml --limit linux_servers

# Check mode (dry run)
ansible-playbook playbooks/site.yml --check

# Verbose output
ansible-playbook playbooks/site.yml -vv
```

## Windows SSH Setup

For Windows hosts, you need SSH server configured:

### Install OpenSSH Server

```powershell
# Install OpenSSH Server
Add-WindowsCapability -Online -Name OpenSSH.Server

# Start and enable SSH service
Start-Service sshd
Set-Service -Name sshd -StartupType 'Automatic'

# Configure PowerShell as default shell
New-ItemProperty -Path "HKLM:\SOFTWARE\OpenSSH" -Name DefaultShell -Value "C:\Windows\System32\WindowsPowerShell\v1.0\powershell.exe" -PropertyType String -Force
```

### Configure Authentication

```powershell
# For password authentication (less secure)
# Edit C:\ProgramData\ssh\sshd_config
# PasswordAuthentication yes

# For key-based authentication (recommended)
# Copy public key to C:\Users\username\.ssh\authorized_keys
```

## Configuration Variables

### Global Variables (defaults/main.yml)

| Variable | Default | Description |
|----------|---------|-------------|
| `github_repo` | `"brandonhon/tls-cert-monitor"` | GitHub repository |
| `service_port` | `9090` | HTTP server port |
| `scan_interval_seconds` | `3600` | Scan interval |
| `scan_workers` | `4` | Number of worker threads |
| `log_level` | `"INFO"` | Logging level |
| `enable_cache` | `true` | Enable caching |
| `enable_hot_reload` | `true` | Enable hot reload |
| `windows_service_method` | `"native"` | Windows service method: "native" (v1.2.0+) or "nssm" |

### Host-Specific Variables

```yaml
# In inventory or host_vars/
cert_dirs_linux:
  - /custom/cert/path

service_port: 8080
scan_interval_seconds: 1800
```

## Service Management

### Linux (systemd)

```bash
# Check service status
systemctl status tls-cert-monitor

# View logs
journalctl -u tls-cert-monitor -f

# Restart service
systemctl restart tls-cert-monitor
```

### Windows

```powershell
# Check service status
Get-Service tls-cert-monitor

# View logs (NSSM method)
Get-Content "C:\ProgramData\tls-cert-monitor\logs\service.log"

# View logs (native method)
Get-EventLog -LogName Application -Source "TLS Certificate Monitor" -Newest 20

# Restart service
Restart-Service tls-cert-monitor

# Check service method in use (native or NSSM)
Get-Service tls-cert-monitor | Select-Object Name, Status, ServiceType
```

## Verification

After deployment, verify the installation:

```bash
# Check health endpoint
curl http://hostname:9090/healthz

# Check metrics
curl http://hostname:9090/metrics

# View configuration
curl http://hostname:9090/config
```

## Troubleshooting

### Common Issues

#### SSH Connection Failed
```bash
# Test SSH connectivity
ansible all -m ping

# Check SSH configuration
ansible-inventory --list
```

#### Service Not Starting
```bash
# Check service logs (Linux)
ansible linux_servers -m shell -a "journalctl -u tls-cert-monitor --no-pager -n 50"

# Check service status (Windows)
ansible windows_servers -m win_shell -a "Get-Service tls-cert-monitor | Format-List"
```

#### Permission Denied
```bash
# Check file permissions (Linux)
ansible linux_servers -m shell -a "ls -la /opt/tls-cert-monitor/"

# Check Windows service user
ansible windows_servers -m win_shell -a "Get-WmiObject win32_service | Where-Object {$_.name -eq 'tls-cert-monitor'}"
```

### Log Locations

| Platform | Location |
|----------|----------|
| Linux | `/var/log/tls-cert-monitor/` |
| Windows | `C:\ProgramData\tls-cert-monitor\logs\` |

## Advanced Configuration

### Windows Service Method Selection

Starting with v1.2.0, tls-cert-monitor supports native Windows service functionality without requiring NSSM:

```yaml
# group_vars/windows_servers.yml

# Use native Windows service (requires v1.2.0+)
windows_service_method: "native"

# Use NSSM for older versions or compatibility
windows_service_method: "nssm"
```

The native method offers:
- No third-party dependencies
- Direct integration with Windows Service Control Manager
- Built-in support for service install/uninstall/start/stop operations
- Better compatibility with security policies

### Custom Certificate Directories

```yaml
# host_vars/webserver01.yml
cert_dirs_linux:
  - /etc/ssl/certs
  - /etc/nginx/ssl
  - /var/www/ssl
  - /opt/custom/certificates
```

### Environment-Specific Variables

```yaml
# group_vars/production.yml
scan_interval_seconds: 1800  # 30 minutes
log_level: "WARN"

# group_vars/development.yml
scan_interval_seconds: 300   # 5 minutes
log_level: "DEBUG"
enable_hot_reload: true
```

### SSL/TLS Configuration

```yaml
# Enable HTTPS endpoints
server_tls_enabled: true
server_cert_file: "/path/to/server.crt"
server_key_file: "/path/to/server.key"
```

## Integration

### Prometheus Monitoring

The service exposes metrics at `/metrics` endpoint compatible with Prometheus:

```yaml
# prometheus.yml
scrape_configs:
  - job_name: 'tls-cert-monitor'
    static_configs:
      - targets: ['hostname:9090']
```

### Grafana Dashboard

Import the provided Grafana dashboard or create custom panels using metrics like:
- `ssl_cert_expiration_timestamp`
- `ssl_cert_files_total`
- `ssl_cert_parse_errors_total`

## Security Considerations

- Uses dedicated service user on Linux
- Filesystem restrictions via systemd
- Firewall rules for Windows
- Configuration files with restricted permissions
- No hardcoded passwords (use Ansible Vault)

## License

This playbook is provided under the same license as the tls-cert-monitor project.