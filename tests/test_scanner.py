"""
Simplified scanner tests to verify basic functionality.
"""

from unittest.mock import MagicMock, patch

import pytest

from tls_cert_monitor.cache import CacheManager
from tls_cert_monitor.config import Config
from tls_cert_monitor.metrics import MetricsCollector
from tls_cert_monitor.scanner import CertificateScanner


class TestCertificateScanner:
    """Test certificate scanner functionality."""

    @pytest.fixture
    def mock_config(self):
        """Create a mock configuration."""
        config = MagicMock(spec=Config)
        config.directories = ["/test/certs"]
        config.exclude_patterns = ["*.backup"]
        config.p12_passwords = ["", "password", "test"]
        config.scan_interval = 300
        config.workers = 2
        return config

    @pytest.fixture
    def mock_cache(self):
        """Create a mock cache manager."""
        return MagicMock(spec=CacheManager)

    @pytest.fixture
    def mock_metrics(self):
        """Create a mock metrics collector."""
        return MagicMock(spec=MetricsCollector)

    @pytest.fixture
    def scanner(self, mock_config, mock_cache, mock_metrics):
        """Create a certificate scanner instance."""
        with patch("tls_cert_monitor.scanner.get_logger") as mock_get_logger, patch(
            "tls_cert_monitor.scanner.ThreadPoolExecutor"
        ) as mock_executor:
            mock_get_logger.return_value = MagicMock()
            mock_executor.return_value = MagicMock()
            return CertificateScanner(
                config=mock_config,
                cache=mock_cache,
                metrics=mock_metrics,
            )

    def test_scanner_initialization(self, scanner):
        """Test scanner initialization."""
        assert scanner.config is not None
        assert scanner.cache is not None
        assert scanner.metrics is not None
        assert scanner.logger is not None

    def test_weak_key_detection_integration(self, scanner):
        """Test integration with metrics module weak key detection."""
        # These functions are in the metrics module, not scanner
        from tls_cert_monitor.metrics import is_deprecated_signature_algorithm, is_weak_key

        # Correct parameter order: key_size first, then algorithm
        assert is_weak_key(1024, "RSA") is True
        assert is_weak_key(2048, "RSA") is False
        assert is_deprecated_signature_algorithm("md5WithRSAEncryption") is True
        assert is_deprecated_signature_algorithm("sha256WithRSAEncryption") is False
