"""
Tests for configuration management.
"""

import os
import tempfile
from pathlib import Path

import pytest
import yaml

from tls_cert_monitor.config import Config, create_example_config, load_config


class TestConfig:
    """Test configuration model."""

    def test_default_config(self):
        """Test default configuration values."""
        config = Config()

        assert config.port == 3200
        assert config.bind_address == "0.0.0.0"
        assert config.log_level == "INFO"
        assert config.workers == 4
        assert config.scan_interval == "5m"
        assert config.hot_reload is True
        assert config.dry_run is False

    def test_duration_parsing(self):
        """Test duration parsing."""
        config = Config(scan_interval="10m", cache_ttl="2h")

        assert config.scan_interval_seconds == 600  # 10 minutes
        assert config.cache_ttl_seconds == 7200  # 2 hours

    def test_invalid_duration(self):
        """Test invalid duration format."""
        with pytest.raises(ValueError):
            Config(scan_interval="invalid")

    def test_invalid_log_level(self):
        """Test invalid log level."""
        with pytest.raises(ValueError):
            Config(log_level="INVALID")

    def test_port_validation(self):
        """Test port validation."""
        with pytest.raises(ValueError):
            Config(port=0)

        with pytest.raises(ValueError):
            Config(port=70000)


class TestLoadConfig:
    """Test configuration loading."""

    def test_load_from_file(self):
        """Test loading configuration from YAML file."""
        config_data = {
            "port": 8080,
            "bind_address": "127.0.0.1",
            "certificate_directories": ["/test/path"],
            "workers": 8,
        }

        with tempfile.NamedTemporaryFile(mode="w", suffix=".yaml", delete=False) as f:
            yaml.dump(config_data, f)
            config_path = f.name

        try:
            config = load_config(config_path)

            assert config.port == 8080
            assert config.bind_address == "127.0.0.1"
            assert config.certificate_directories == ["/test/path"]
            assert config.workers == 8
        finally:
            os.unlink(config_path)

    def test_load_nonexistent_file(self):
        """Test loading from nonexistent file."""
        with pytest.raises(FileNotFoundError):
            load_config("/nonexistent/config.yaml")

    def test_load_without_file(self):
        """Test loading without config file (defaults)."""
        config = load_config()
        assert config.port == 3200  # Default value

    def test_environment_variable_override(self):
        """Test environment variable overrides."""
        os.environ["TLS_MONITOR_PORT"] = "9090"
        os.environ["TLS_MONITOR_LOG_LEVEL"] = "DEBUG"

        try:
            config = load_config()
            assert config.port == 9090
            assert config.log_level == "DEBUG"
        finally:
            del os.environ["TLS_MONITOR_PORT"]
            del os.environ["TLS_MONITOR_LOG_LEVEL"]

    def test_environment_list_variables(self):
        """Test environment variables for lists."""
        os.environ["TLS_MONITOR_CERT_DIRECTORIES"] = "/path1,/path2,/path3"
        os.environ["TLS_MONITOR_P12_PASSWORDS"] = "pass1,pass2,pass3"

        try:
            config = load_config()
            assert config.certificate_directories == ["/path1", "/path2", "/path3"]
            assert config.p12_passwords == ["pass1", "pass2", "pass3"]
        finally:
            del os.environ["TLS_MONITOR_CERT_DIRECTORIES"]
            del os.environ["TLS_MONITOR_P12_PASSWORDS"]


class TestCreateExampleConfig:
    """Test example configuration creation."""

    def test_create_example_config(self):
        """Test creating example configuration file."""
        with tempfile.TemporaryDirectory() as temp_dir:
            example_path = Path(temp_dir) / "example.yaml"
            create_example_config(str(example_path))

            assert example_path.exists()

            # Load and validate the example config
            with open(example_path, "r") as f:
                config_data = yaml.safe_load(f)

            assert "port" in config_data
            assert "certificate_directories" in config_data
            assert "p12_passwords" in config_data

            # Should be valid configuration
            config = Config(**config_data)
            assert config.port == 3200
