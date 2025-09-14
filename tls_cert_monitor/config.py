"""
Configuration management for TLS Certificate Monitor.
"""

import logging
import os
import re
from pathlib import Path
from typing import Any, Callable, Dict, List, Optional

import yaml
from pydantic import BaseModel, Field, field_validator


class Config(BaseModel):
    """Configuration model for TLS Certificate Monitor."""

    # Server settings
    port: int = Field(default=3200, ge=1, le=65535)
    bind_address: str = Field(default="0.0.0.0")  # nosec B104

    # TLS settings for metrics endpoint
    tls_cert: Optional[str] = None
    tls_key: Optional[str] = None

    # Certificate monitoring
    certificate_directories: List[str] = Field(default_factory=lambda: ["/etc/ssl/certs"])
    exclude_directories: List[str] = Field(default_factory=list)
    exclude_file_patterns: List[str] = Field(default_factory=lambda: ["dhparam.pem"])

    # P12/PFX certificate passwords
    p12_passwords: List[str] = Field(
        default_factory=lambda: [
            "",  # Empty password
            "changeit",  # Java keystore default
            "password",  # Common default
            "123456",  # Common weak password
        ]
    )

    # Scan settings
    scan_interval: str = Field(default="5m")
    workers: int = Field(default=4, ge=1, le=32)

    # Logging
    log_level: str = Field(default="INFO")
    log_file: Optional[str] = None

    # Operation modes
    dry_run: bool = Field(default=False)
    hot_reload: bool = Field(default=True)

    # Cache settings
    cache_type: str = Field(default="memory")  # "memory", "file", or "both"
    cache_dir: str = Field(default="./cache")
    cache_ttl: str = Field(default="1h")
    cache_max_size: int = Field(default=10485760)  # 10MB for memory default

    # Security settings
    allowed_ips: List[str] = Field(default_factory=lambda: ["127.0.0.1", "::1"])
    enable_ip_whitelist: bool = Field(default=True)

    @field_validator("cache_type")
    @classmethod
    def validate_cache_type(cls, v: str) -> str:
        """Validate cache type."""
        valid_types = {"memory", "file", "both"}
        if v.lower() not in valid_types:
            raise ValueError(f"cache_type must be one of {valid_types}, got '{v}'")
        return v.lower()

    @field_validator("log_level")
    @classmethod
    def validate_log_level(cls, v: str) -> str:
        """Validate log level."""
        valid_levels = ["DEBUG", "INFO", "WARNING", "ERROR", "CRITICAL"]
        if v.upper() not in valid_levels:
            raise ValueError(f"Log level must be one of: {valid_levels}")
        return v.upper()

    @field_validator("certificate_directories")
    @classmethod
    def validate_cert_directories(cls, v: List[str]) -> List[str]:
        """Validate certificate directories exist and are safe to access."""
        validated_dirs = []

        # Forbidden system directories for security
        forbidden_paths = [
            "/etc/shadow",
            "/etc/passwd",
            "/etc/sudoers",
            "/private/etc/shadow",
            "/private/etc/passwd",  # macOS paths
            "/proc",
            "/sys",
            "/dev",
            "/root/.ssh",
            "/home/*/.ssh",
            "/Users/*/.ssh",  # macOS user paths
            "/var/log/auth.log",
            "/var/log/secure",
        ]

        for directory in v:
            try:
                # Resolve path to absolute form and check for symlink attacks
                path = Path(directory).resolve()

                # Check if path is forbidden
                path_str = str(path)
                is_forbidden = False

                for forbidden in forbidden_paths:
                    if "*" in forbidden:
                        # Handle wildcard patterns
                        pattern = forbidden.replace("*", "[^/]*")
                        if re.match(pattern, path_str):
                            is_forbidden = True
                            break
                    elif path_str.startswith(forbidden) or path_str == forbidden:
                        is_forbidden = True
                        break

                if is_forbidden:
                    logging.error(
                        f"Access to directory {directory} is forbidden for security reasons"
                    )
                    continue

                # Warn if directory doesn't exist but include it anyway
                # (it might be created later, especially in containerized environments)
                if not path.exists():
                    logging.warning(f"Certificate directory does not exist: {directory}")
                elif not path.is_dir():
                    logging.error(f"Certificate directory path is not a directory: {directory}")
                    continue

                validated_dirs.append(str(path))

            except (OSError, RuntimeError) as e:
                logging.error(f"Invalid certificate directory {directory}: {e}")
                continue

        if not validated_dirs:
            logging.warning("No valid certificate directories configured")

        return validated_dirs

    @field_validator("exclude_file_patterns")
    @classmethod
    def validate_exclude_patterns(cls, v: List[str]) -> List[str]:
        """Validate exclude file patterns are valid regex."""
        validated_patterns = []
        for pattern in v:
            try:
                re.compile(pattern)
                validated_patterns.append(pattern)
            except re.error as e:
                logging.warning(f"Invalid regex pattern '{pattern}': {e}")
        return validated_patterns

    @field_validator("allowed_ips")
    @classmethod
    def validate_allowed_ips(cls, v: List[str]) -> List[str]:
        """Validate IP addresses and CIDR blocks in allowed_ips list."""
        import ipaddress

        validated_ips = []
        for ip_str in v:
            try:
                # Try to parse as IP address or network
                if "/" in ip_str:
                    # CIDR notation
                    ipaddress.ip_network(ip_str, strict=False)
                else:
                    # Single IP address
                    ipaddress.ip_address(ip_str)
                validated_ips.append(ip_str)
            except (ipaddress.AddressValueError, ValueError) as e:
                logging.error(f"Invalid IP address or network '{ip_str}': {e}")

        # Ensure localhost is always allowed for health checks
        localhost_ips = ["127.0.0.1", "::1"]
        for localhost in localhost_ips:
            if localhost not in validated_ips:
                validated_ips.append(localhost)
                logging.info(f"Added {localhost} to allowed IPs for localhost access")

        return validated_ips

    @field_validator("scan_interval", "cache_ttl")
    @classmethod
    def validate_duration(cls, v: str) -> str:
        """Validate duration format (e.g., '5m', '1h', '30s')."""
        if not v:
            raise ValueError("Duration cannot be empty")

        # Simple validation for duration format
        # Use raw string to avoid escaping issues
        pattern = r"^\d+[smhd]$"
        if not re.match(pattern, v):
            raise ValueError("Duration must be in format like '5m', '1h', '30s', '1d'")
        return v

    def parse_duration_seconds(self, duration: str) -> int:
        """Parse duration string to seconds."""
        match = re.match(r"^(\d+)([smhd])$", duration)
        if not match:
            raise ValueError(f"Invalid duration format: {duration}")

        value, unit = match.groups()
        value = int(value)

        multipliers = {"s": 1, "m": 60, "h": 3600, "d": 86400}

        return value * multipliers[unit]

    @property
    def scan_interval_seconds(self) -> int:
        """Get scan interval in seconds."""
        return self.parse_duration_seconds(self.scan_interval)

    @property
    def cache_ttl_seconds(self) -> int:
        """Get cache TTL in seconds."""
        return self.parse_duration_seconds(self.cache_ttl)


def load_config(config_path: Optional[str] = None) -> Config:
    """
    Load configuration from file or environment variables.

    Args:
        config_path: Path to configuration file

    Returns:
        Config object
    """
    config_data: Dict[str, Any] = {}

    # Load from file if provided
    if config_path:
        config_file = Path(config_path)
        if config_file.exists():
            with open(config_file, "r", encoding="utf-8") as f:
                config_data = yaml.safe_load(f) or {}
        else:
            raise FileNotFoundError(f"Configuration file not found: {config_path}")

    # Override with environment variables
    env_overrides = _get_env_overrides()
    config_data.update(env_overrides)

    return Config(**config_data)


def _get_env_overrides() -> dict:
    """Get configuration overrides from environment variables."""
    env_mapping: Dict[str, tuple[str, Callable[[str], Any]]] = {
        "TLS_MONITOR_PORT": ("port", int),
        "TLS_MONITOR_BIND_ADDRESS": ("bind_address", str),
        "TLS_MONITOR_TLS_CERT": ("tls_cert", str),
        "TLS_MONITOR_TLS_KEY": ("tls_key", str),
        "TLS_MONITOR_SCAN_INTERVAL": ("scan_interval", str),
        "TLS_MONITOR_WORKERS": ("workers", int),
        "TLS_MONITOR_LOG_LEVEL": ("log_level", str),
        "TLS_MONITOR_LOG_FILE": ("log_file", str),
        "TLS_MONITOR_DRY_RUN": ("dry_run", lambda x: x.lower() in ("true", "1", "yes")),
        "TLS_MONITOR_HOT_RELOAD": ("hot_reload", lambda x: x.lower() in ("true", "1", "yes")),
        "TLS_MONITOR_CACHE_TYPE": ("cache_type", str),
        "TLS_MONITOR_CACHE_DIR": ("cache_dir", str),
        "TLS_MONITOR_CACHE_TTL": ("cache_ttl", str),
        "TLS_MONITOR_CACHE_MAX_SIZE": ("cache_max_size", int),
        "TLS_MONITOR_ENABLE_IP_WHITELIST": (
            "enable_ip_whitelist",
            lambda x: x.lower() in ("true", "1", "yes"),
        ),
    }

    overrides = {}
    for env_var, (config_key, converter) in env_mapping.items():
        value = os.getenv(env_var)
        if value is not None:
            try:
                overrides[config_key] = converter(value)
            except (ValueError, TypeError) as e:
                logging.warning(f"Invalid value for {env_var}: {value} - {e}")

    # Handle list environment variables
    cert_dirs = os.getenv("TLS_MONITOR_CERT_DIRECTORIES")
    if cert_dirs:
        overrides["certificate_directories"] = [d.strip() for d in cert_dirs.split(",")]

    exclude_dirs = os.getenv("TLS_MONITOR_EXCLUDE_DIRECTORIES")
    if exclude_dirs:
        overrides["exclude_directories"] = [d.strip() for d in exclude_dirs.split(",")]

    exclude_patterns = os.getenv("TLS_MONITOR_EXCLUDE_FILE_PATTERNS")
    if exclude_patterns:
        overrides["exclude_file_patterns"] = [p.strip() for p in exclude_patterns.split(",")]

    p12_passwords = os.getenv("TLS_MONITOR_P12_PASSWORDS")
    if p12_passwords:
        overrides["p12_passwords"] = [p.strip() for p in p12_passwords.split(",")]

    # Handle allowed IPs list
    allowed_ips = os.getenv("TLS_MONITOR_ALLOWED_IPS")
    if allowed_ips:
        overrides["allowed_ips"] = [ip.strip() for ip in allowed_ips.split(",")]

    return overrides


def create_example_config(output_path: str = "config.example.yaml") -> None:
    """Create an example configuration file."""
    example_config = {
        "port": 3200,
        "bind_address": "0.0.0.0",  # nosec B104  # Intentional for production - allows external access
        "certificate_directories": ["/etc/ssl/certs", "/etc/pki/tls/certs"],
        "exclude_directories": ["/etc/ssl/certs/private", "/etc/ssl/certs/backup"],
        "exclude_file_patterns": ["dhparam.pem", ".*\\.key$", ".*backup.*"],
        "p12_passwords": ["", "changeit", "password", "123456"],
        "scan_interval": "5m",
        "workers": 4,
        "log_level": "INFO",
        "dry_run": False,
        "hot_reload": True,
        "cache_type": "memory",
        "cache_dir": "./cache",
        "cache_ttl": "1h",
        "cache_max_size": 10485760,  # 10MB for memory, 30MB (31457280) for file
        "allowed_ips": ["127.0.0.1", "::1", "192.168.1.0/24"],  # localhost + local network
        "enable_ip_whitelist": True,
    }

    with open(output_path, "w", encoding="utf-8") as f:
        yaml.dump(example_config, f, default_flow_style=False, sort_keys=False)
