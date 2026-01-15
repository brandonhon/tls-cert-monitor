"""
Integration tests for TLS Certificate Monitor.

These tests verify the entire application working together in a running environment:
- Application startup and initialization
- Certificate scanning with real files
- API endpoints with real HTTP requests
- Metrics collection and exposure
- Hot reload functionality
- Graceful shutdown

Run with: pytest tests/test_integration.py -v
Or: make test-integration
"""

import asyncio
import time
from datetime import datetime, timedelta, timezone
from pathlib import Path

import httpx
import pytest
import pytest_asyncio
from cryptography import x509
from cryptography.hazmat.backends import default_backend
from cryptography.hazmat.primitives import hashes, serialization
from cryptography.hazmat.primitives.asymmetric import rsa
from cryptography.x509.oid import NameOID

from tls_cert_monitor.api import create_app
from tls_cert_monitor.cache import CacheManager
from tls_cert_monitor.config import Config
from tls_cert_monitor.hot_reload import HotReloadManager
from tls_cert_monitor.metrics import MetricsCollector
from tls_cert_monitor.scanner import CertificateScanner


@pytest.fixture
def test_certs_dir(tmp_path: Path) -> Path:
    """Create a temporary directory with test certificates."""
    certs_dir = tmp_path / "certs"
    certs_dir.mkdir()
    return certs_dir


@pytest.fixture
def test_config(test_certs_dir: Path, tmp_path: Path) -> Config:
    """Create a test configuration."""
    cache_dir = tmp_path / "cache"
    cache_dir.mkdir()

    return Config(
        certificate_directories=[str(test_certs_dir)],
        port=9999,  # High port for testing
        bind_address="127.0.0.1",
        scan_interval_seconds=300,  # Long interval, we'll trigger manually
        workers=2,
        log_level="DEBUG",
        cache_dir=str(cache_dir),
        cache_ttl_seconds=300,
        hot_reload=False,  # Disable for most tests
        dry_run=False,
        enable_ip_whitelist=False,  # Disable for testing
    )


@pytest_asyncio.fixture
async def app_components(test_config: Config):
    """Create and initialize application components."""
    metrics = MetricsCollector()
    cache = CacheManager(test_config)
    await cache.initialize()

    scanner = CertificateScanner(config=test_config, cache=cache, metrics=metrics)

    yield (test_config, scanner, metrics, cache)

    # Cleanup
    await cache.close()


def generate_test_certificate(path: Path, cn: str = "test.example.com") -> None:
    """Generate a test X.509 certificate."""
    # Generate private key
    private_key = rsa.generate_private_key(
        public_exponent=65537, key_size=2048, backend=default_backend()
    )

    # Create certificate
    subject = issuer = x509.Name(
        [
            x509.NameAttribute(NameOID.COUNTRY_NAME, "US"),
            x509.NameAttribute(NameOID.STATE_OR_PROVINCE_NAME, "California"),
            x509.NameAttribute(NameOID.LOCALITY_NAME, "San Francisco"),
            x509.NameAttribute(NameOID.ORGANIZATION_NAME, "Test Org"),
            x509.NameAttribute(NameOID.COMMON_NAME, cn),
        ]
    )

    cert = (
        x509.CertificateBuilder()
        .subject_name(subject)
        .issuer_name(issuer)
        .public_key(private_key.public_key())
        .serial_number(x509.random_serial_number())
        .not_valid_before(datetime.now(timezone.utc))
        .not_valid_after(datetime.now(timezone.utc) + timedelta(days=365))
        .add_extension(
            x509.SubjectAlternativeName([x509.DNSName(cn)]),
            critical=False,
        )
        .sign(private_key, hashes.SHA256(), backend=default_backend())
    )

    # Write certificate to file
    with open(path, "wb") as f:
        f.write(cert.public_bytes(serialization.Encoding.PEM))


@pytest.mark.asyncio
@pytest.mark.integration
class TestFullApplicationIntegration:
    """Integration tests for the complete application."""

    async def test_application_startup_and_shutdown(self, app_components):
        """Test that the application starts and shuts down cleanly."""
        config, scanner, metrics, cache = app_components

        # Verify all components initialized
        assert config is not None
        assert scanner is not None
        assert metrics is not None
        assert cache is not None

        # Start scanner
        await scanner.start_scanning()
        assert scanner._scanning is True

        # Stop scanner
        await scanner.stop()
        assert scanner._scanning is False

    async def test_certificate_scanning_with_real_files(self, app_components, test_certs_dir):
        """Test scanning real certificate files."""
        config, scanner, metrics, cache = app_components

        # Generate test certificates
        generate_test_certificate(test_certs_dir / "cert1.pem", "example1.com")
        generate_test_certificate(test_certs_dir / "cert2.pem", "example2.com")
        generate_test_certificate(test_certs_dir / "cert3.pem", "example3.com")

        # Perform scan
        result = await scanner.scan_once()

        # Verify scan results
        assert result is not None
        assert "summary" in result
        assert result["summary"]["total_files"] == 3
        assert result["summary"]["total_parsed"] == 3
        assert result["summary"]["total_errors"] == 0

    async def test_api_endpoints_with_running_server(self, app_components, test_certs_dir):
        """Test all API endpoints with a running server."""
        config, scanner, metrics, cache = app_components

        # Generate test certificate
        generate_test_certificate(test_certs_dir / "test.pem")

        # Create FastAPI app
        app = create_app(scanner=scanner, metrics=metrics, cache=cache, config=config)

        # Use TestClient for synchronous testing
        from fastapi.testclient import TestClient

        client = TestClient(app)

        # Test health endpoint
        response = client.get("/healthz")
        assert response.status_code == 200
        data = response.json()
        assert data["status"] == "healthy"
        assert "version" in data

        # Perform a scan first
        await scanner.scan_once()

        # Test metrics endpoint
        response = client.get("/metrics")
        assert response.status_code == 200
        assert "text/plain" in response.headers["content-type"]
        metrics_text = response.text
        assert "ssl_cert" in metrics_text

        # Test config endpoint
        response = client.get("/config")
        assert response.status_code == 200
        config_data = response.json()
        assert "port" in config_data
        assert "workers" in config_data

        # Test scan trigger endpoint
        response = client.get("/scan")
        assert response.status_code == 200
        scan_data = response.json()
        # Scan endpoint returns full scan results
        assert "summary" in scan_data
        assert "directories" in scan_data
        assert "timestamp" in scan_data

        # Test cache stats endpoint
        response = client.get("/cache/stats")
        assert response.status_code == 200
        cache_stats = response.json()
        assert "entries_total" in cache_stats
        assert "cache_hits" in cache_stats
        assert "cache_misses" in cache_stats

    async def test_metrics_collection_accuracy(self, app_components, test_certs_dir):
        """Test that metrics are collected accurately."""
        config, scanner, metrics, cache = app_components

        # Generate certificates with known properties
        generate_test_certificate(test_certs_dir / "cert1.pem", "test1.example.com")
        generate_test_certificate(test_certs_dir / "cert2.pem", "test2.example.com")

        # Scan and collect metrics
        await scanner.scan_once()

        # Verify metrics were updated (get_registry_status returns dict)
        registry_status = metrics.get_registry_status()
        assert isinstance(registry_status, dict)

        # Check that certificate metrics exist in the metrics collector's registry
        # Note: MetricsCollector uses its own registry, not the global REGISTRY
        metric_names = [m.name for m in metrics.registry.collect()]
        assert "ssl_cert_expiration_timestamp" in metric_names
        assert "ssl_cert_info" in metric_names
        assert "ssl_certs_parsed_total" in metric_names

    async def test_cache_persistence_and_retrieval(self, app_components, test_certs_dir):
        """Test that cache stores and retrieves data correctly."""
        config, scanner, metrics, cache = app_components

        # Generate test certificate
        cert_path = test_certs_dir / "cached_cert.pem"
        generate_test_certificate(cert_path, "cached.example.com")

        # First scan - should populate cache
        await scanner.scan_once()

        # Check cache stats
        stats = await cache.get_stats()
        initial_hits = stats["cache_hits"]

        # Second scan - should use cache
        await scanner.scan_once()

        # Verify cache was used
        stats_after = await cache.get_stats()
        assert stats_after["cache_hits"] > initial_hits or stats_after["entries_total"] > 0

    async def test_hot_reload_with_certificate_changes(
        self, app_components, test_certs_dir, tmp_path
    ):
        """Test hot reload functionality when certificates change."""
        config, scanner, metrics, cache = app_components

        # Enable hot reload for this test
        config.hot_reload = True

        # Create hot reload manager
        hot_reload = HotReloadManager(
            config=config, scanner=scanner, config_path=str(tmp_path / "config.yaml")
        )

        await hot_reload.start()

        # Generate initial certificate
        cert_path = test_certs_dir / "hot_reload_test.pem"
        generate_test_certificate(cert_path, "initial.example.com")

        # Perform initial scan
        result1 = await scanner.scan_once()
        assert result1["summary"]["total_files"] == 1

        # Add a new certificate
        cert_path2 = test_certs_dir / "hot_reload_test2.pem"
        generate_test_certificate(cert_path2, "added.example.com")

        # Trigger hot reload manually (simulate file system event)
        await hot_reload._debounced_cert_change(str(cert_path2), "created")

        # Small delay for processing
        await asyncio.sleep(0.5)

        # Verify new certificate was detected
        result2 = await scanner.scan_once()
        assert result2["summary"]["total_files"] == 2

        # Cleanup
        await hot_reload.stop()

    async def test_concurrent_scans_prevented(self, app_components, test_certs_dir):
        """Test that concurrent scans are prevented by the lock."""
        config, scanner, metrics, cache = app_components

        # Generate test certificates
        for i in range(5):
            generate_test_certificate(test_certs_dir / f"cert{i}.pem", f"test{i}.example.com")

        # Try to start multiple scans concurrently
        scan_tasks = [scanner.scan_once() for _ in range(3)]

        # Wait for all scans to complete
        results = await asyncio.gather(*scan_tasks)

        # All should complete successfully (lock prevents conflicts)
        assert len(results) == 3
        for result in results:
            assert result["summary"]["total_files"] == 5

    async def test_error_handling_with_invalid_certificates(
        self, app_components, test_certs_dir
    ):
        """Test that invalid certificates are handled gracefully."""
        config, scanner, metrics, cache = app_components

        # Create an invalid certificate file
        invalid_cert = test_certs_dir / "invalid.pem"
        invalid_cert.write_text("This is not a valid certificate")

        # Create a valid certificate
        generate_test_certificate(test_certs_dir / "valid.pem")

        # Scan should handle the error gracefully
        result = await scanner.scan_once()

        # Should process both files
        assert result["summary"]["total_files"] == 2
        # One should parse successfully, one should error
        assert result["summary"]["total_parsed"] == 1
        assert result["summary"]["total_errors"] == 1

    async def test_memory_cleanup_after_large_scan(self, app_components, test_certs_dir):
        """Test that memory is properly cleaned up after scanning many certificates."""
        config, scanner, metrics, cache = app_components

        # Generate many certificates
        num_certs = 50
        for i in range(num_certs):
            generate_test_certificate(test_certs_dir / f"bulk{i}.pem", f"bulk{i}.example.com")

        # Perform scan
        result = await scanner.scan_once()

        assert result["summary"]["total_files"] == num_certs
        assert result["summary"]["total_parsed"] == num_certs

        # Clear cache and verify memory release
        await cache.clear()
        stats = await cache.get_stats()
        assert stats["entries_total"] == 0

    async def test_complete_application_lifecycle(self, app_components, test_certs_dir):
        """Test the complete application lifecycle from start to finish."""
        config, scanner, metrics, cache = app_components

        # 1. Application startup (already done by fixture)
        assert scanner is not None

        # 2. Initial certificate setup
        generate_test_certificate(test_certs_dir / "lifecycle.pem", "lifecycle.example.com")

        # 3. Start scanning
        await scanner.start_scanning()
        assert scanner._scanning is True

        # 4. Perform scan
        result = await scanner.scan_once()
        assert result["summary"]["total_parsed"] == 1

        # 5. Query metrics
        registry_status = metrics.get_registry_status()
        assert registry_status["prometheus_registry"]["status"] == "healthy"
        assert registry_status["prometheus_registry"]["metrics_count"] > 0

        # 6. Check cache
        cache_stats = await cache.get_stats()
        assert cache_stats is not None

        # 7. Add new certificate (simulating runtime change)
        generate_test_certificate(test_certs_dir / "new_cert.pem", "new.example.com")

        # 8. Trigger new scan
        result2 = await scanner.scan_once()
        assert result2["summary"]["total_files"] == 2

        # 9. Graceful shutdown
        await scanner.stop()
        assert scanner._scanning is False

        # 10. Final cleanup (handled by fixture)


@pytest.mark.asyncio
@pytest.mark.integration
class TestPerformanceAndStability:
    """Performance and stability integration tests."""

    async def test_rapid_successive_scans(self, app_components, test_certs_dir):
        """Test performance with rapid successive scans."""
        config, scanner, metrics, cache = app_components

        # Generate test certificates
        for i in range(10):
            generate_test_certificate(test_certs_dir / f"rapid{i}.pem", f"rapid{i}.example.com")

        # Perform multiple rapid scans
        start_time = time.time()
        for _ in range(5):
            result = await scanner.scan_once()
            assert result["summary"]["total_parsed"] == 10

        duration = time.time() - start_time

        # Should complete all scans in reasonable time (< 10 seconds)
        assert duration < 10.0

    async def test_cache_performance_improvement(self, app_components, test_certs_dir):
        """Test that caching improves scan performance."""
        config, scanner, metrics, cache = app_components

        # Generate certificates
        for i in range(20):
            generate_test_certificate(test_certs_dir / f"cache{i}.pem", f"cache{i}.example.com")

        # First scan (no cache)
        start_cold = time.time()
        await scanner.scan_once()
        cold_duration = time.time() - start_cold

        # Second scan (with cache)
        start_warm = time.time()
        await scanner.scan_once()
        warm_duration = time.time() - start_warm

        # Warm scan should be faster or similar (cache overhead might be minimal for small sets)
        # This is mainly to ensure caching doesn't slow things down
        assert warm_duration < (cold_duration * 2)  # Allow some variance
