"""
Tests for metrics collection.
"""

import time
from datetime import datetime, timedelta

import pytest

from tls_cert_monitor.metrics import (
    MetricsCollector,
    is_deprecated_signature_algorithm,
    is_weak_key,
)


class TestMetricsCollector:
    """Test metrics collector functionality."""

    def test_metrics_collector_initialization(self):
        """Test metrics collector initialization."""
        metrics = MetricsCollector()

        assert metrics.registry is not None
        assert metrics.ssl_cert_expiration_timestamp is not None
        assert metrics.ssl_cert_san_count is not None
        assert metrics.app_memory_bytes is not None

    def test_update_certificate_metrics(self):
        """Test updating certificate metrics."""
        metrics = MetricsCollector()

        cert_data = {
            "common_name": "test.example.com",
            "issuer": "Test CA",
            "path": "/test/cert.pem",
            "serial": "12345",
            "subject": "CN=test.example.com",
            "expiration_timestamp": time.time() + 86400,  # 1 day from now
            "san_count": 3,
            "signature_algorithm": "sha256WithRSAEncryption",
            "key_size": 2048,
            "key_algorithm": "RSA",
            "is_weak_key": False,
            "is_deprecated_algorithm": False,
        }

        # Should not raise any exceptions
        metrics.update_certificate_metrics(cert_data)

        # Get metrics output
        metrics_output = metrics.get_metrics()
        assert "ssl_cert_expiration_timestamp" in metrics_output
        assert "test.example.com" in metrics_output

    def test_update_scan_metrics(self):
        """Test updating scan metrics."""
        metrics = MetricsCollector()

        metrics.update_scan_metrics(
            directory="/test/dir", duration=1.5, files_total=10, parsed_total=8, errors_total=2
        )

        metrics_output = metrics.get_metrics()
        assert "ssl_cert_files_total" in metrics_output
        assert "ssl_cert_scan_duration_seconds" in metrics_output

    def test_record_parse_error(self):
        """Test recording parse errors."""
        metrics = MetricsCollector()

        metrics.record_parse_error(
            filename="bad_cert.pem",
            error_type="ParseError",
            error_message="Invalid certificate format",
        )

        metrics_output = metrics.get_metrics()
        assert "ssl_cert_parse_errors_total" in metrics_output

    def test_update_duplicate_metrics(self):
        """Test updating duplicate certificate metrics."""
        metrics = MetricsCollector()

        # Add certificates with same serial
        cert_data_1 = {
            "common_name": "test1.example.com",
            "issuer": "Test CA",
            "path": "/test/cert1.pem",
            "serial": "12345",
            "subject": "CN=test1.example.com",
        }

        cert_data_2 = {
            "common_name": "test2.example.com",
            "issuer": "Test CA",
            "path": "/test/cert2.pem",
            "serial": "12345",  # Same serial
            "subject": "CN=test2.example.com",
        }

        metrics.update_certificate_metrics(cert_data_1)
        metrics.update_certificate_metrics(cert_data_2)
        metrics.update_duplicate_metrics()

        metrics_output = metrics.get_metrics()
        assert "ssl_cert_duplicate_count" in metrics_output

    def test_system_metrics(self):
        """Test system metrics update."""
        metrics = MetricsCollector()

        metrics.update_system_metrics()

        metrics_output = metrics.get_metrics()
        assert "app_memory_bytes" in metrics_output
        assert "app_cpu_percent" in metrics_output
        assert "app_thread_count" in metrics_output

    def test_get_registry_status(self):
        """Test getting registry status."""
        metrics = MetricsCollector()

        status = metrics.get_registry_status()

        assert "prometheus_registry" in status
        assert "status" in status["prometheus_registry"]
        assert status["prometheus_registry"]["status"] == "healthy"


class TestMetricHelpers:
    """Test metric helper functions."""

    def test_is_weak_key_rsa(self):
        """Test weak key detection for RSA."""
        assert is_weak_key(1024, "RSA") is True
        assert is_weak_key(2048, "RSA") is False
        assert is_weak_key(4096, "RSA") is False

    def test_is_weak_key_dsa(self):
        """Test weak key detection for DSA."""
        assert is_weak_key(1024, "DSA") is True
        assert is_weak_key(2048, "DSA") is False

    def test_is_weak_key_ecdsa(self):
        """Test weak key detection for ECDSA."""
        assert is_weak_key(160, "ECDSA") is True
        assert is_weak_key(256, "ECDSA") is False
        assert is_weak_key(384, "ECDSA") is False

    def test_is_weak_key_unknown(self):
        """Test weak key detection for unknown algorithm."""
        assert is_weak_key(1024, "UNKNOWN") is True
        assert is_weak_key(2048, "UNKNOWN") is False

    def test_is_deprecated_signature_algorithm(self):
        """Test deprecated signature algorithm detection."""
        assert is_deprecated_signature_algorithm("md5WithRSAEncryption") is True
        assert is_deprecated_signature_algorithm("sha1WithRSAEncryption") is True
        assert is_deprecated_signature_algorithm("sha256WithRSAEncryption") is False
        assert is_deprecated_signature_algorithm("sha384WithECDSA") is False

        # Case insensitive
        assert is_deprecated_signature_algorithm("MD5WithRSAEncryption") is True
        assert is_deprecated_signature_algorithm("SHA1WithRSAEncryption") is True


class TestIssuerCodes:
    """Test issuer code classification."""

    def test_digicert_classification(self):
        """Test DigiCert issuer classification."""
        metrics = MetricsCollector()

        assert metrics._get_issuer_code("DigiCert Inc") == 30
        assert metrics._get_issuer_code("digicert.com") == 30
        assert metrics._get_issuer_code("DigiCert SHA2 Secure Server CA") == 30

    def test_amazon_classification(self):
        """Test Amazon issuer classification."""
        metrics = MetricsCollector()

        assert metrics._get_issuer_code("Amazon") == 31
        assert metrics._get_issuer_code("AWS Certificate Manager") == 31
        assert metrics._get_issuer_code("amazon.com") == 31

    def test_self_signed_classification(self):
        """Test self-signed issuer classification."""
        metrics = MetricsCollector()

        assert metrics._get_issuer_code("self-signed") == 33
        assert metrics._get_issuer_code("localhost") == 33
        assert metrics._get_issuer_code("127.0.0.1") == 33

    def test_unknown_classification(self):
        """Test unknown issuer classification."""
        metrics = MetricsCollector()

        assert metrics._get_issuer_code("Unknown CA") == 32
        assert metrics._get_issuer_code("Custom Corporate CA") == 32
        assert metrics._get_issuer_code("") == 32
