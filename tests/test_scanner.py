"""
Tests for certificate scanner.
"""

from pathlib import Path
from unittest.mock import AsyncMock, MagicMock, patch

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
        cache = AsyncMock(spec=CacheManager)
        cache.get.return_value = None
        return cache

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

    @pytest.mark.asyncio
    async def test_start_stop_scanner(self, scanner):
        """Test starting and stopping the scanner."""
        # Mock the scanning loop to avoid infinite loop
        with patch.object(scanner, "_scan_loop") as mock_scan_loop:
            mock_scan_loop.return_value = None

            # Start scanner
            await scanner.start()
            assert scanner._task is not None
            assert not scanner._task.done()

            # Stop scanner
            await scanner.stop()
            assert scanner._task.cancelled() or scanner._task.done()

    def test_should_exclude_file(self, scanner):
        """Test file exclusion logic."""
        # Test exclusion patterns
        assert scanner._should_exclude("/path/test.backup") is True
        assert scanner._should_exclude("/path/test.crt") is False

        # Test hidden files
        assert scanner._should_exclude("/path/.hidden") is True
        assert scanner._should_exclude("/path/visible.pem") is False

    @patch("tls_cert_monitor.scanner.Path.exists")
    @patch("tls_cert_monitor.scanner.Path.is_file")
    def test_discover_certificates(self, mock_is_file, mock_exists, scanner):
        """Test certificate discovery."""
        # Mock file system
        mock_exists.return_value = True
        mock_is_file.return_value = True

        with patch("tls_cert_monitor.scanner.Path.rglob") as mock_rglob:
            mock_files = [
                Path("/test/certs/cert1.pem"),
                Path("/test/certs/cert2.crt"),
                Path("/test/certs/cert3.p12"),
                Path("/test/certs/backup.backup"),  # Should be excluded
            ]
            mock_rglob.return_value = mock_files

            discovered = scanner._discover_certificates()

            # Should exclude .backup files
            assert len(discovered) == 3
            assert Path("/test/certs/backup.backup") not in discovered

    def test_parse_pkcs12_certificate_success(self, scanner):
        """Test successful PKCS12 certificate parsing."""
        # Create a mock certificate
        mock_cert = MagicMock()
        mock_cert.subject.rfc4514_string.return_value = "CN=test.example.com"
        mock_cert.serial_number = 12345

        with patch("tls_cert_monitor.scanner.pkcs12.load_key_and_certificates") as mock_load:
            mock_load.return_value = (None, mock_cert, None)

            with patch.object(scanner, "_extract_certificate_info") as mock_extract:
                mock_extract.return_value = {"subject": "CN=test.example.com"}

                result = scanner._parse_pkcs12_certificate(b"mock_p12_data")

                assert result == {"subject": "CN=test.example.com"}
                mock_load.assert_called_once_with(b"mock_p12_data", None)

    def test_parse_pkcs12_certificate_with_password(self, scanner):
        """Test PKCS12 certificate parsing with password."""
        mock_cert = MagicMock()

        with patch("tls_cert_monitor.scanner.pkcs12.load_key_and_certificates") as mock_load:
            # First call (no password) fails, second call (with password) succeeds
            mock_load.side_effect = [Exception("Bad password"), (None, mock_cert, None)]

            with patch.object(scanner, "_extract_certificate_info") as mock_extract:
                mock_extract.return_value = {"subject": "CN=test.example.com"}

                result = scanner._parse_pkcs12_certificate(b"mock_p12_data")

                assert result == {"subject": "CN=test.example.com"}
                # Should try multiple passwords
                assert mock_load.call_count >= 2

    def test_parse_pkcs12_certificate_all_passwords_fail(self, scanner):
        """Test PKCS12 certificate parsing when all passwords fail."""
        with patch("tls_cert_monitor.scanner.pkcs12.load_key_and_certificates") as mock_load:
            mock_load.side_effect = Exception("Invalid PKCS12 data")

            result = scanner._parse_pkcs12_certificate(b"invalid_p12_data")

            assert result is None
            # Should try all configured passwords
            assert mock_load.call_count == len(scanner.config.p12_passwords)

    def test_extract_certificate_info(self, scanner):
        """Test certificate information extraction."""
        mock_cert = MagicMock()
        mock_cert.subject.rfc4514_string.return_value = "CN=test.example.com"
        mock_cert.issuer.rfc4514_string.return_value = "CN=Test CA"
        mock_cert.serial_number = 12345
        mock_cert.not_valid_before = "2023-01-01T00:00:00"
        mock_cert.not_valid_after = "2024-01-01T00:00:00"
        mock_cert.signature_algorithm_oid._name = "sha256WithRSAEncryption"

        # Mock public key
        mock_public_key = MagicMock()
        mock_public_key.key_size = 2048
        mock_cert.public_key.return_value = mock_public_key

        # Mock extensions
        mock_cert.extensions = []

        result = scanner._extract_certificate_info(mock_cert)

        assert result["subject"] == "CN=test.example.com"
        assert result["issuer"] == "CN=Test CA"
        assert result["serial_number"] == 12345
        assert result["signature_algorithm"] == "sha256WithRSAEncryption"
        assert result["key_size"] == 2048

    @patch("tls_cert_monitor.scanner.Path.read_bytes")
    def test_parse_certificate_file_pem(self, mock_read_bytes, scanner):
        """Test parsing PEM certificate file."""
        mock_cert_data = b"-----BEGIN CERTIFICATE-----\nMOCK_CERT_DATA\n-----END CERTIFICATE-----"
        mock_read_bytes.return_value = mock_cert_data

        with patch("tls_cert_monitor.scanner.x509.load_pem_x509_certificate") as mock_load_pem:
            mock_cert = MagicMock()
            mock_load_pem.return_value = mock_cert

            with patch.object(scanner, "_extract_certificate_info") as mock_extract:
                mock_extract.return_value = {"format": "PEM"}

                result = scanner._parse_certificate_file(Path("/test/cert.pem"))

                assert result == {"format": "PEM"}
                mock_load_pem.assert_called_once_with(mock_cert_data)

    @patch("tls_cert_monitor.scanner.Path.read_bytes")
    def test_parse_certificate_file_p12(self, mock_read_bytes, scanner):
        """Test parsing PKCS12 certificate file."""
        mock_p12_data = b"MOCK_P12_DATA"
        mock_read_bytes.return_value = mock_p12_data

        with patch.object(scanner, "_parse_pkcs12_certificate") as mock_parse_p12:
            mock_parse_p12.return_value = {"format": "PKCS12"}

            result = scanner._parse_certificate_file(Path("/test/cert.p12"))

            assert result == {"format": "PKCS12"}
            mock_parse_p12.assert_called_once_with(mock_p12_data)

    @patch("tls_cert_monitor.scanner.Path.read_bytes")
    def test_parse_certificate_file_invalid(self, mock_read_bytes, scanner):
        """Test parsing invalid certificate file."""
        mock_read_bytes.return_value = b"INVALID_CERT_DATA"

        result = scanner._parse_certificate_file(Path("/test/invalid.crt"))

        assert result is None

    @pytest.mark.asyncio
    async def test_scan_certificates_with_cache_hit(self, scanner):
        """Test certificate scanning with cache hit."""
        mock_files = [Path("/test/cert1.pem")]
        cached_data = {"subject": "CN=cached.example.com"}

        with patch.object(scanner, "_discover_certificates", return_value=mock_files):
            scanner.cache.get.return_value = cached_data

            await scanner._scan_certificates()

            # Should use cached data
            scanner.cache.get.assert_called_once()
            scanner.metrics.certificates_parsed.inc.assert_called_once()

    @pytest.mark.asyncio
    async def test_scan_certificates_with_cache_miss(self, scanner):
        """Test certificate scanning with cache miss."""
        mock_files = [Path("/test/cert1.pem")]
        parsed_data = {"subject": "CN=parsed.example.com"}

        with patch.object(scanner, "_discover_certificates", return_value=mock_files):
            with patch.object(scanner, "_parse_certificate_file", return_value=parsed_data):
                scanner.cache.get.return_value = None  # Cache miss

                await scanner._scan_certificates()

                # Should parse and cache data
                scanner.cache.set.assert_called_once()
                scanner.metrics.certificates_parsed.inc.assert_called_once()

    @pytest.mark.asyncio
    async def test_scan_certificates_parse_error(self, scanner):
        """Test certificate scanning with parse error."""
        mock_files = [Path("/test/invalid.crt")]

        with patch.object(scanner, "_discover_certificates", return_value=mock_files):
            with patch.object(scanner, "_parse_certificate_file", return_value=None):
                scanner.cache.get.return_value = None

                await scanner._scan_certificates()

                # Should handle parse errors gracefully
                scanner.metrics.certificates_failed.inc.assert_called_once()

    def test_weak_key_detection_integration(self, scanner):
        """Test integration with metrics module weak key detection."""
        # These functions are in the metrics module, not scanner
        from tls_cert_monitor.metrics import is_deprecated_signature_algorithm, is_weak_key

        assert is_weak_key("RSA", 1024) is True
        assert is_weak_key("RSA", 2048) is False
        assert is_deprecated_signature_algorithm("md5WithRSAEncryption") is True
        assert is_deprecated_signature_algorithm("sha256WithRSAEncryption") is False
