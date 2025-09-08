"""
Configuration management for TLS Certificate Monitor.
"""

import logging
import os
from pathlib import Path
from typing import List, Optional

import yaml
from pydantic import BaseModel, Field, field_validator


class Config(BaseModel):
    """Configuration model for TLS Certificate Monitor."""

    # Server settings
    port: int = Field(default=3200, ge=1, le=65535)
    bind_address: str = Field(default="0.0.0.0")

    # TLS settings for metrics endpoint
    tls_cert: Optional[str] = None
    tls_key: Optional[str] = None

    # Certificate monitoring
    certificate_directories: List[str] = Field(default_factory=lambda: ["/etc/ssl/certs"])
    exclude_directories: List[str] = Field(default_factory=list)

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
    cache_dir: str = Field(default="./cache")
    cache_ttl: str = Field(default="1h")
    cache_max_size: int = Field(default=104857600)  # 100MB

    @field_validator("log_level")
    @classmethod
    def validate_log_level(cls, v):
        """Validate log level."""
        valid_levels = ["DEBUG", "INFO", "WARNING", "ERROR", "CRITICAL"]
        if v.upper() not in valid_levels:
            raise ValueError(f"Log level must be one of: {valid_levels}")
        return v.upper()

    @field_validator("certificate_directories")
    @classmethod
    def validate_cert_directories(cls, v):
        """Validate certificate directories exist."""
        for directory in v:
            path = Path(directory)
            if not path.exists():
                logging.warning(f"Certificate directory does not exist: {directory}")
        return v

    @field_validator("scan_interval", "cache_ttl")
    @classmethod
    def validate_duration(cls, v):
        """Validate duration format (e.g., '5m', '1h', '30s')."""
        if not v:
            raise ValueError("Duration cannot be empty")

        # Simple validation for duration format
        import re

        # Use raw string to avoid escaping issues
        pattern = r"^\d+[smhd]$"
        if not re.match(pattern, v):
            raise ValueError("Duration must be in format like '5m', '1h', '30s', '1d'")
        return v

    def parse_duration_seconds(self, duration: str) -> int:
        """Parse duration string to seconds."""
        import re

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
    config_data = {}

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
    env_mapping = {
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
        "TLS_MONITOR_CACHE_DIR": ("cache_dir", str),
        "TLS_MONITOR_CACHE_TTL": ("cache_ttl", str),
        "TLS_MONITOR_CACHE_MAX_SIZE": ("cache_max_size", int),
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

    p12_passwords = os.getenv("TLS_MONITOR_P12_PASSWORDS")
    if p12_passwords:
        overrides["p12_passwords"] = [p.strip() for p in p12_passwords.split(",")]

    return overrides


def create_example_config(output_path: str = "config.example.yaml") -> None:
    """Create an example configuration file."""
    example_config = {
        "port": 3200,
        "bind_address": "0.0.0.0",
        "certificate_directories": ["/etc/ssl/certs", "/etc/pki/tls/certs"],
        "exclude_directories": ["/etc/ssl/certs/private", "/etc/ssl/certs/backup"],
        "p12_passwords": ["", "changeit", "password", "123456"],
        "scan_interval": "5m",
        "workers": 4,
        "log_level": "INFO",
        "dry_run": False,
        "hot_reload": True,
        "cache_dir": "./cache",
        "cache_ttl": "1h",
        "cache_max_size": 104857600,
    }

    with open(output_path, "w", encoding="utf-8") as f:
        yaml.dump(example_config, f, default_flow_style=False, sort_keys=False)
