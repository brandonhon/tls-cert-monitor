"""
Tests for FastAPI endpoints.
"""

from unittest.mock import AsyncMock, MagicMock

import pytest
from fastapi.testclient import TestClient

from tls_cert_monitor.api import create_app
from tls_cert_monitor.cache import CacheManager
from tls_cert_monitor.config import Config
from tls_cert_monitor.metrics import MetricsCollector
from tls_cert_monitor.scanner import CertificateScanner


class TestAPI:
    """Test API endpoints."""

    @pytest.fixture
    def mock_config(self):
        """Create a mock configuration."""
        config = MagicMock(spec=Config)
        config.server.host = "0.0.0.0"
        config.server.port = 8080
        config.server.metrics_path = "/metrics"
        config.server.health_path = "/healthz"
        return config

    @pytest.fixture
    def mock_scanner(self):
        """Create a mock scanner."""
        return AsyncMock(spec=CertificateScanner)

    @pytest.fixture
    def mock_cache(self):
        """Create a mock cache manager."""
        return AsyncMock(spec=CacheManager)

    @pytest.fixture
    def mock_metrics(self):
        """Create a mock metrics collector."""
        metrics = MagicMock(spec=MetricsCollector)
        metrics.generate_metrics.return_value = "# Mock metrics\ntest_metric 1.0\n"
        return metrics

    @pytest.fixture
    def client(self, mock_config, mock_scanner, mock_cache, mock_metrics):
        """Create a test client."""
        app = create_app(
            config=mock_config, scanner=mock_scanner, cache=mock_cache, metrics=mock_metrics
        )
        return TestClient(app)

    def test_health_endpoint(self, client):
        """Test health check endpoint."""
        response = client.get("/healthz")
        assert response.status_code == 200
        data = response.json()
        assert data["status"] == "healthy"
        assert "timestamp" in data
        assert "uptime" in data

    def test_metrics_endpoint(self, client, mock_metrics):
        """Test metrics endpoint."""
        response = client.get("/metrics")
        assert response.status_code == 200
        assert response.headers["content-type"] == "text/plain; charset=utf-8"
        assert "test_metric 1.0" in response.text
        mock_metrics.generate_metrics.assert_called_once()

    def test_scan_endpoint_trigger(self, client, mock_scanner):
        """Test manual scan trigger endpoint."""
        mock_scanner.scan_once.return_value = {"scanned": 10, "parsed": 8}

        response = client.post("/scan")
        assert response.status_code == 200
        data = response.json()
        assert data["status"] == "completed"
        assert "results" in data

    def test_config_endpoint(self, client, mock_config):
        """Test configuration info endpoint."""
        response = client.get("/config")
        assert response.status_code == 200
        data = response.json()
        assert "server" in data
        assert "scan_interval" in data

    def test_root_redirect(self, client):
        """Test root endpoint redirects to health."""
        response = client.get("/", allow_redirects=False)
        assert response.status_code == 307
        assert response.headers["location"] == "/healthz"
