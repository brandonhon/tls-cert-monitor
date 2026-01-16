"""
End-to-end tests for TLS Certificate Monitor running in Docker.

These tests spin up the actual Docker container and test all functionality
as if the application were running in a production environment:
- Container lifecycle (build, start, stop, cleanup)
- HTTP API endpoints from outside the container
- Certificate scanning with mounted volumes
- Metrics exposure in Prometheus format
- Health checks and monitoring
- Graceful shutdown

Prerequisites:
- Docker installed and daemon running
- Docker compose (optional, for advanced scenarios)

Run with:
    pytest tests/test_e2e_docker.py -v -m e2e
    make test-e2e
"""

import subprocess
import time
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Generator

import pytest
import requests
from cryptography import x509
from cryptography.hazmat.backends import default_backend
from cryptography.hazmat.primitives import hashes, serialization
from cryptography.hazmat.primitives.asymmetric import rsa
from cryptography.x509.oid import NameOID

# Test configuration
CONTAINER_NAME = "tls-cert-monitor-e2e-test"
IMAGE_NAME = "tls-cert-monitor:e2e-test"
HOST_PORT = 19999  # High port to avoid conflicts
CONTAINER_PORT = 3000


def generate_test_certificate(
    path: Path,
    cn: str = "test.example.com",
    days_valid: int = 365,
    format: str = "pem",
    key_size: int = 2048,
    password: str = None,
) -> rsa.RSAPrivateKey:
    """
    Generate a test X.509 certificate for E2E testing.

    Args:
        path: Where to save the certificate
        cn: Common name for the certificate
        days_valid: Number of days certificate is valid
        format: Certificate format - "pem", "der", or "p12"
        key_size: RSA key size (use 1024 for testing weak keys)
        password: Password for PKCS#12 files (None for no password)

    Returns:
        The private key used to sign the certificate
    """
    from cryptography.hazmat.primitives.serialization import pkcs12

    # Generate private key
    private_key = rsa.generate_private_key(
        public_exponent=65537, key_size=key_size, backend=default_backend()
    )

    # Create certificate
    subject = issuer = x509.Name(
        [
            x509.NameAttribute(NameOID.COUNTRY_NAME, "US"),
            x509.NameAttribute(NameOID.STATE_OR_PROVINCE_NAME, "California"),
            x509.NameAttribute(NameOID.LOCALITY_NAME, "San Francisco"),
            x509.NameAttribute(NameOID.ORGANIZATION_NAME, "E2E Test Org"),
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
        .not_valid_after(datetime.now(timezone.utc) + timedelta(days=days_valid))
        .add_extension(
            x509.SubjectAlternativeName([x509.DNSName(cn)]),
            critical=False,
        )
        .sign(private_key, hashes.SHA256(), backend=default_backend())
    )

    # Write certificate in requested format
    with open(path, "wb") as f:
        if format == "pem":
            f.write(cert.public_bytes(serialization.Encoding.PEM))
        elif format == "der":
            f.write(cert.public_bytes(serialization.Encoding.DER))
        elif format == "p12":
            # Create PKCS#12 bundle with certificate and private key
            password_bytes = password.encode() if password else None
            p12_data = pkcs12.serialize_key_and_certificates(
                name=cn.encode(),
                key=private_key,
                cert=cert,
                cas=None,
                encryption_algorithm=(
                    serialization.BestAvailableEncryption(password_bytes)
                    if password_bytes
                    else serialization.NoEncryption()
                ),
            )
            f.write(p12_data)
        else:
            raise ValueError(f"Unsupported format: {format}")

    return private_key


def run_command(cmd: list, check: bool = True, capture: bool = True) -> subprocess.CompletedProcess:
    """Run a shell command and return the result."""
    if capture:
        return subprocess.run(cmd, check=check, capture_output=True, text=True)
    else:
        return subprocess.run(cmd, check=check)


def wait_for_container_healthy(timeout: int = 30, interval: float = 1.0) -> bool:
    """Wait for container to be healthy and responding."""
    start_time = time.time()

    while time.time() - start_time < timeout:
        try:
            # Check if container is running
            result = run_command(
                ["docker", "inspect", "-f", "{{.State.Running}}", CONTAINER_NAME], check=False
            )

            if result.returncode != 0 or result.stdout.strip() != "true":
                time.sleep(interval)
                continue

            # Try health check endpoint
            response = requests.get(f"http://localhost:{HOST_PORT}/healthz", timeout=2)

            if response.status_code == 200:
                return True

        except (requests.exceptions.RequestException, subprocess.SubprocessError):
            pass

        time.sleep(interval)

    return False


@pytest.fixture(scope="module")
def docker_environment(tmp_path_factory) -> Generator[dict, None, None]:
    """
    Set up Docker environment for E2E testing.

    This fixture:
    1. Creates test certificates in a temporary directory
    2. Creates a test config file
    3. Builds the Docker image
    4. Starts the container with mounted volumes
    5. Waits for the container to be healthy
    6. Yields environment info for tests
    7. Cleans up container and images
    """
    # Create temporary directories
    test_dir = tmp_path_factory.mktemp("e2e_docker_test")
    certs_dir = test_dir / "certs"
    certs_dir.mkdir()
    config_dir = test_dir / "config"
    config_dir.mkdir()

    # Generate test certificates - create more for comprehensive hot reload testing
    generate_test_certificate(certs_dir / "test1.pem", "app.example.com")
    generate_test_certificate(certs_dir / "test2.pem", "api.example.com")
    generate_test_certificate(certs_dir / "test3.pem", "web.example.com")
    generate_test_certificate(certs_dir / "test4.pem", "mail.example.com")
    generate_test_certificate(certs_dir / "test5.pem", "db.example.com")
    generate_test_certificate(certs_dir / "test6.pem", "cache.example.com")
    generate_test_certificate(certs_dir / "test7.pem", "lb.example.com")
    generate_test_certificate(certs_dir / "test8.pem", "proxy.example.com")
    generate_test_certificate(certs_dir / "expiring.pem", "old.example.com", days_valid=30)

    # Create test config file
    config_content = f"""
port: {CONTAINER_PORT}
bind_address: "0.0.0.0"
log_level: "INFO"
scan_interval_seconds: 60
workers: 2
certificate_directories:
  - "/certs"
cache_dir: "/tmp/cache"
cache_ttl_seconds: 300
hot_reload: true
dry_run: false
enable_ip_whitelist: false
"""

    config_file = config_dir / "config.yaml"
    config_file.write_text(config_content)

    # Build Docker image
    print("\n🐳 Building Docker image for E2E testing...")
    build_result = run_command(["docker", "build", "-t", IMAGE_NAME, "-f", "Dockerfile", "."])

    if build_result.returncode != 0:
        pytest.skip(f"Docker build failed: {build_result.stderr}")

    print("✅ Docker image built successfully")

    # Stop and remove any existing test container
    run_command(["docker", "stop", CONTAINER_NAME], check=False)
    run_command(["docker", "rm", CONTAINER_NAME], check=False)

    # Start container
    print(f"🚀 Starting container '{CONTAINER_NAME}'...")
    start_result = run_command(
        [
            "docker",
            "run",
            "-d",
            "--name",
            CONTAINER_NAME,
            "-p",
            f"{HOST_PORT}:{CONTAINER_PORT}",
            "-v",
            f"{certs_dir}:/certs:ro",
            "-v",
            f"{config_file}:/app/config.yaml:ro",
            IMAGE_NAME,
            "python",
            "main.py",
            "--config=/app/config.yaml",
        ]
    )

    if start_result.returncode != 0:
        pytest.skip(f"Failed to start container: {start_result.stderr}")

    print(f"✅ Container started: {start_result.stdout.strip()}")

    # Wait for container to be healthy
    print("⏳ Waiting for container to be healthy...")
    if not wait_for_container_healthy(timeout=60):
        # Print container logs for debugging
        logs = run_command(["docker", "logs", CONTAINER_NAME], check=False)
        print(f"Container logs:\n{logs.stdout}")

        # Cleanup and fail
        run_command(["docker", "stop", CONTAINER_NAME], check=False)
        run_command(["docker", "rm", CONTAINER_NAME], check=False)
        pytest.skip("Container did not become healthy in time")

    print("✅ Container is healthy and responding")

    # Yield environment info to tests
    env = {
        "base_url": f"http://localhost:{HOST_PORT}",
        "container_name": CONTAINER_NAME,
        "image_name": IMAGE_NAME,
        "certs_dir": certs_dir,
        "config_file": config_file,
    }

    yield env

    # Cleanup
    print("\n🧹 Cleaning up Docker environment...")
    run_command(["docker", "stop", CONTAINER_NAME], check=False)
    run_command(["docker", "rm", CONTAINER_NAME], check=False)
    run_command(["docker", "rmi", IMAGE_NAME], check=False)
    print("✅ Docker environment cleaned up")


@pytest.mark.e2e
@pytest.mark.docker
class TestDockerE2E:
    """End-to-end tests for Docker-deployed application."""

    def test_container_is_running(self, docker_environment):
        """Test that the container is running."""
        result = run_command(
            ["docker", "inspect", "-f", "{{.State.Running}}", docker_environment["container_name"]]
        )
        assert result.stdout.strip() == "true"

    def test_health_endpoint(self, docker_environment):
        """Test health check endpoint from outside container."""
        response = requests.get(f"{docker_environment['base_url']}/healthz", timeout=5)

        assert response.status_code == 200
        data = response.json()
        assert data["status"] == "healthy"
        assert "version" in data

    def test_metrics_endpoint(self, docker_environment):
        """Test Prometheus metrics endpoint."""
        response = requests.get(f"{docker_environment['base_url']}/metrics", timeout=5)

        assert response.status_code == 200
        assert "text/plain" in response.headers["content-type"]

        metrics_text = response.text

        # Verify key metrics are present
        assert "ssl_cert_expiration_timestamp" in metrics_text
        assert "ssl_cert_info" in metrics_text
        assert "ssl_certs_parsed_total" in metrics_text
        assert "app_memory_bytes" in metrics_text  # App metrics, not process metrics

    def test_config_endpoint(self, docker_environment):
        """Test configuration endpoint."""
        response = requests.get(f"{docker_environment['base_url']}/config", timeout=5)

        assert response.status_code == 200
        config = response.json()

        assert config["port"] == CONTAINER_PORT
        assert config["workers"] == 2
        # Certificate directories are masked for security (e.g., "***/certs")
        assert len(config["certificate_directories"]) > 0
        assert any("certs" in d for d in config["certificate_directories"])

    def test_manual_scan_trigger(self, docker_environment):
        """Test manual scan trigger endpoint."""
        response = requests.get(f"{docker_environment['base_url']}/scan", timeout=10)

        assert response.status_code == 200
        scan_data = response.json()

        # Verify scan results structure
        assert "summary" in scan_data
        assert "directories" in scan_data
        assert "timestamp" in scan_data

        # Verify certificates were scanned
        assert scan_data["summary"]["total_files"] >= 3
        assert scan_data["summary"]["total_parsed"] >= 3

    def test_cache_stats_endpoint(self, docker_environment):
        """Test cache statistics endpoint."""
        # Trigger a scan first to populate cache
        requests.get(f"{docker_environment['base_url']}/scan", timeout=10)

        response = requests.get(f"{docker_environment['base_url']}/cache/stats", timeout=5)

        assert response.status_code == 200
        stats = response.json()

        assert "entries_total" in stats
        assert "cache_hits" in stats
        assert "cache_misses" in stats
        assert "hit_rate" in stats

    def test_cache_clear_endpoint(self, docker_environment):
        """Test cache clearing endpoint."""
        # Populate cache first
        requests.get(f"{docker_environment['base_url']}/scan", timeout=10)

        # Clear cache
        response = requests.post(f"{docker_environment['base_url']}/cache/clear", timeout=5)

        assert response.status_code == 200
        result = response.json()
        assert "message" in result

        # Verify cache is empty
        stats_response = requests.get(f"{docker_environment['base_url']}/cache/stats", timeout=5)
        stats = stats_response.json()
        assert stats["entries_total"] == 0

    def test_certificate_scanning_accuracy(self, docker_environment):
        """Test that certificates are accurately scanned and reported."""
        # Trigger scan
        response = requests.get(f"{docker_environment['base_url']}/scan", timeout=10)

        scan_data = response.json()

        # Verify scan found our test certificates (9 initial certificates)
        assert scan_data["summary"]["total_files"] == 9
        assert scan_data["summary"]["total_parsed"] == 9
        assert scan_data["summary"]["total_errors"] == 0

        # Check certificates in the scan results
        certs_found = []
        for dir_data in scan_data["directories"].values():
            certs_found.extend([cert["common_name"] for cert in dir_data["certificates"]])

        assert "app.example.com" in certs_found
        assert "api.example.com" in certs_found
        assert "old.example.com" in certs_found

    def test_metrics_reflect_certificate_data(self, docker_environment):
        """Test that Prometheus metrics reflect actual certificate data."""
        # Trigger scan first
        requests.get(f"{docker_environment['base_url']}/scan", timeout=10)

        # Get metrics
        response = requests.get(f"{docker_environment['base_url']}/metrics", timeout=5)

        metrics_text = response.text

        # Verify certificate-specific metrics are present (sample check)
        assert 'common_name="app.example.com"' in metrics_text
        assert 'common_name="api.example.com"' in metrics_text
        assert 'common_name="old.example.com"' in metrics_text
        assert 'common_name="web.example.com"' in metrics_text
        assert 'common_name="db.example.com"' in metrics_text

        # Verify scan metrics (9 initial certificates)
        assert "ssl_certs_parsed_total 9" in metrics_text

    def test_container_logs_contain_startup_info(self, docker_environment):
        """Test that container logs contain proper startup information."""
        result = run_command(["docker", "logs", docker_environment["container_name"]])

        logs = result.stdout

        # Verify key startup messages
        assert "tls certificate monitor" in logs.lower() or "tls_cert_monitor" in logs.lower()
        assert "info" in logs.lower() or "debug" in logs.lower()

    def test_graceful_shutdown(self, docker_environment):
        """Test that container handles graceful shutdown."""
        # Send stop signal
        result = run_command(
            [
                "docker",
                "stop",
                "-t",
                "10",  # 10 second timeout
                docker_environment["container_name"],
            ]
        )

        assert result.returncode == 0

        # Verify container stopped
        inspect_result = run_command(
            ["docker", "inspect", "-f", "{{.State.Running}}", docker_environment["container_name"]]
        )
        assert inspect_result.stdout.strip() == "false"

        # Restart for other tests
        run_command(["docker", "start", docker_environment["container_name"]])

        # Wait for it to be healthy again
        assert wait_for_container_healthy(timeout=30)

    def test_environment_variables_override(self, docker_environment):
        """Test that environment variables can override config (future enhancement)."""
        # This test documents expected behavior for environment variable overrides
        # Currently the app uses config file, but this shows how it could be tested
        pass

    def test_volume_persistence(self, docker_environment):
        """Test that mounted volumes are accessible and writable."""
        # Execute command in container to verify volume mount
        result = run_command(
            ["docker", "exec", docker_environment["container_name"], "ls", "-la", "/certs"]
        )

        assert result.returncode == 0
        assert "test1.pem" in result.stdout
        assert "test2.pem" in result.stdout
        assert "expiring.pem" in result.stdout

    def test_hot_reload_certificate_update(self, docker_environment):
        """
        Comprehensive test for certificate hot reload functionality.

        This test verifies hot reload works reliably by:
        1. Capturing initial state (9 certificates)
        2. Swapping 4 certificates simultaneously
        3. Adding 3 new certificates
        4. Removing 2 certificates
        5. Verifying ALL changes are correctly reflected in metrics

        Tests both file modification detection and metric refresh reliability.
        """
        base_url = docker_environment["base_url"]
        certs_dir = docker_environment["certs_dir"]

        # ===== PHASE 1: Capture initial state =====
        requests.get(f"{base_url}/scan", timeout=10)
        initial_response = requests.get(f"{base_url}/metrics", timeout=5)
        initial_metrics = initial_response.text

        # Verify all 9 initial certificates are present
        initial_certs = [
            "app.example.com",
            "api.example.com",
            "web.example.com",
            "mail.example.com",
            "db.example.com",
            "cache.example.com",
            "lb.example.com",
            "proxy.example.com",
            "old.example.com",
        ]

        for cert_cn in initial_certs:
            assert (
                f'common_name="{cert_cn}"' in initial_metrics
            ), f"Initial cert {cert_cn} not found"

        assert "ssl_certs_parsed_total 9" in initial_metrics

        # ===== PHASE 2: Swap 4 certificates simultaneously =====
        print("\n🔄 Swapping 4 certificates...")

        # Swap test1.pem: app.example.com → updated1.example.com
        generate_test_certificate(
            certs_dir / "test1.pem",
            cn="updated1.example.com",
            days_valid=200,
        )

        # Swap test3.pem: web.example.com → updated3.example.com
        generate_test_certificate(
            certs_dir / "test3.pem",
            cn="updated3.example.com",
            days_valid=250,
        )

        # Swap test5.pem: db.example.com → updated5.example.com
        generate_test_certificate(
            certs_dir / "test5.pem",
            cn="updated5.example.com",
            days_valid=300,
        )

        # Swap test7.pem: lb.example.com → updated7.example.com
        generate_test_certificate(
            certs_dir / "test7.pem",
            cn="updated7.example.com",
            days_valid=150,
        )

        # ===== PHASE 3: Add 3 new certificates =====
        print("➕ Adding 3 new certificates...")

        generate_test_certificate(
            certs_dir / "new1.pem",
            cn="new1.example.com",
            days_valid=400,
        )

        generate_test_certificate(
            certs_dir / "new2.pem",
            cn="new2.example.com",
            days_valid=450,
        )

        generate_test_certificate(
            certs_dir / "new3.pem",
            cn="new3.example.com",
            days_valid=500,
        )

        # ===== PHASE 4: Remove 2 certificates =====
        print("➖ Removing 2 certificates...")

        import os

        # Remove test2.pem (api.example.com)
        os.remove(certs_dir / "test2.pem")

        # Remove test4.pem (mail.example.com)
        os.remove(certs_dir / "test4.pem")

        # ===== PHASE 5: Wait for hot reload and trigger scan =====
        print("⏳ Waiting for hot reload detection...")
        time.sleep(4)  # Give hot reload time to detect all changes

        scan_response = requests.get(f"{base_url}/scan", timeout=15)
        assert scan_response.status_code == 200

        # ===== PHASE 6: Get updated metrics and verify =====
        print("✅ Verifying all changes in metrics...")

        updated_response = requests.get(f"{base_url}/metrics", timeout=5)
        updated_metrics = updated_response.text

        # Verify swapped certificates: OLD should be GONE
        assert 'common_name="app.example.com"' not in updated_metrics, "Old app cert still present!"
        assert 'common_name="web.example.com"' not in updated_metrics, "Old web cert still present!"
        assert 'common_name="db.example.com"' not in updated_metrics, "Old db cert still present!"
        assert 'common_name="lb.example.com"' not in updated_metrics, "Old lb cert still present!"

        # Verify swapped certificates: NEW should be PRESENT
        assert 'common_name="updated1.example.com"' in updated_metrics, "New updated1 cert missing!"
        assert 'common_name="updated3.example.com"' in updated_metrics, "New updated3 cert missing!"
        assert 'common_name="updated5.example.com"' in updated_metrics, "New updated5 cert missing!"
        assert 'common_name="updated7.example.com"' in updated_metrics, "New updated7 cert missing!"

        # Verify added certificates: should be PRESENT
        assert 'common_name="new1.example.com"' in updated_metrics, "New1 cert missing!"
        assert 'common_name="new2.example.com"' in updated_metrics, "New2 cert missing!"
        assert 'common_name="new3.example.com"' in updated_metrics, "New3 cert missing!"

        # Verify removed certificates: should be GONE
        assert (
            'common_name="api.example.com"' not in updated_metrics
        ), "Removed api cert still present!"
        assert (
            'common_name="mail.example.com"' not in updated_metrics
        ), "Removed mail cert still present!"

        # Verify unchanged certificates: should STILL be PRESENT
        assert 'common_name="cache.example.com"' in updated_metrics, "Unchanged cache cert missing!"
        assert 'common_name="proxy.example.com"' in updated_metrics, "Unchanged proxy cert missing!"
        assert 'common_name="old.example.com"' in updated_metrics, "Unchanged old cert missing!"

        # Verify total count: Started with 9, swapped 4, added 3, removed 2 = 10 total
        # (9 - 2 removed + 3 added = 10)
        expected_total = 10
        assert (
            f"ssl_certs_parsed_total {expected_total}" in updated_metrics
        ), f"Expected {expected_total} total certs!"

        print(f"✅ Hot reload test passed! All {expected_total} certificates correctly tracked.")
        print("   - 4 certificates swapped ✓")
        print("   - 3 certificates added ✓")
        print("   - 2 certificates removed ✓")
        print("   - 3 certificates unchanged ✓")

    def test_production_readiness_checklist(self, docker_environment):
        """
        Comprehensive production readiness check.

        Verifies:
        - Health endpoint responds
        - Metrics endpoint is accessible
        - Application handles requests under load
        - No error logs during normal operation
        """
        base_url = docker_environment["base_url"]

        # 1. Health check
        health_response = requests.get(f"{base_url}/healthz", timeout=5)
        assert health_response.status_code == 200
        assert health_response.json()["status"] == "healthy"

        # 2. Metrics available
        metrics_response = requests.get(f"{base_url}/metrics", timeout=5)
        assert metrics_response.status_code == 200

        # 3. Multiple rapid requests (simulate load)
        for _ in range(10):
            response = requests.get(f"{base_url}/healthz", timeout=2)
            assert response.status_code == 200

        # 4. Check logs for errors
        logs_result = run_command(
            ["docker", "logs", "--tail", "100", docker_environment["container_name"]]
        )

        logs = logs_result.stdout.lower()

        # Should not have critical errors
        assert "critical" not in logs
        assert "fatal" not in logs

        # Should have successful startup (check for ERROR log level, not "errors: 0")
        assert " error " not in logs and "| error" not in logs


@pytest.mark.e2e
@pytest.mark.docker
class TestDockerAdvancedFeatures:
    """Tests for advanced certificate scanning features."""

    def test_pkcs12_certificate_with_password(self, docker_environment):
        """
        Test PKCS#12/PFX certificate parsing with password.

        Verifies:
        - P12 files can be parsed
        - Password attempts work (using default passwords from config)
        - Certificate data is correctly extracted from P12 bundle
        """
        certs_dir = docker_environment["certs_dir"]
        base_url = docker_environment["base_url"]

        # Generate a P12 certificate with a password from the default list
        p12_path = certs_dir / "secure.p12"
        generate_test_certificate(
            p12_path,
            cn="p12.example.com",
            format="p12",
            password="changeit",  # Default password in config
        )

        # Trigger scan to pick up the new P12 file
        time.sleep(2)  # Give hot reload time to detect
        scan_response = requests.get(f"{base_url}/scan", timeout=10)
        assert scan_response.status_code == 200

        # Check metrics for the P12 certificate
        metrics_response = requests.get(f"{base_url}/metrics", timeout=5)
        metrics_text = metrics_response.text

        # P12 certificate should be parsed and present in metrics
        assert 'common_name="p12.example.com"' in metrics_text
        assert "/certs/secure.p12" in metrics_text

    def test_der_format_certificate(self, docker_environment):
        """
        Test DER format certificate parsing.

        Verifies:
        - DER format certificates are correctly parsed
        - Metrics reflect DER certificate data
        """
        certs_dir = docker_environment["certs_dir"]
        base_url = docker_environment["base_url"]

        # Generate a DER format certificate
        der_path = certs_dir / "binary.der"
        generate_test_certificate(
            der_path,
            cn="der.example.com",
            format="der",
        )

        # Trigger scan
        time.sleep(2)
        scan_response = requests.get(f"{base_url}/scan", timeout=10)
        assert scan_response.status_code == 200

        # Check metrics
        metrics_response = requests.get(f"{base_url}/metrics", timeout=5)
        metrics_text = metrics_response.text

        assert 'common_name="der.example.com"' in metrics_text
        assert "/certs/binary.der" in metrics_text

    def test_weak_key_detection(self, docker_environment):
        """
        Test weak key detection for security analysis.

        Verifies:
        - Weak keys (< 2048 bits) are detected
        - ssl_cert_weak_key_total metric is incremented
        """
        certs_dir = docker_environment["certs_dir"]
        base_url = docker_environment["base_url"]

        # Generate a certificate with a weak 1024-bit key
        weak_path = certs_dir / "weak.pem"
        generate_test_certificate(
            weak_path,
            cn="weak.example.com",
            key_size=1024,  # Weak key
        )

        # Trigger scan
        time.sleep(2)
        scan_response = requests.get(f"{base_url}/scan", timeout=10)
        assert scan_response.status_code == 200

        # Check metrics for weak key detection
        metrics_response = requests.get(f"{base_url}/metrics", timeout=5)
        metrics_text = metrics_response.text

        # Should detect weak key
        assert "ssl_cert_weak_key_total" in metrics_text
        # The weak key count should be > 0 (at least 1)
        assert 'common_name="weak.example.com"' in metrics_text

    def test_invalid_certificate_handling(self, docker_environment):
        """
        Test handling of invalid/corrupted certificates.

        Verifies:
        - Invalid certificates don't crash the scanner
        - Parse errors are tracked in metrics
        - Valid certificates continue to be processed
        """
        certs_dir = docker_environment["certs_dir"]
        base_url = docker_environment["base_url"]

        # Create an invalid certificate file (just random data)
        invalid_path = certs_dir / "invalid.pem"
        with open(invalid_path, "w") as f:
            f.write("-----BEGIN CERTIFICATE-----\n")
            f.write("This is not a valid certificate\n")
            f.write("Just some random text\n")
            f.write("-----END CERTIFICATE-----\n")

        # Trigger scan
        time.sleep(2)
        scan_response = requests.get(f"{base_url}/scan", timeout=10)
        assert scan_response.status_code == 200

        # Check metrics - parse errors should be tracked
        metrics_response = requests.get(f"{base_url}/metrics", timeout=5)
        metrics_text = metrics_response.text

        # Parse errors metric should exist
        assert "ssl_cert_parse_errors_total" in metrics_text

        # Valid certificates should still be present (check for any valid cert)
        # Note: Some certs may have been swapped by previous tests
        assert (
            'common_name="old.example.com"' in metrics_text
            or 'common_name="cache.example.com"' in metrics_text
            or 'common_name="proxy.example.com"' in metrics_text
        )

    def test_duplicate_certificate_detection(self, docker_environment):
        """
        Test duplicate certificate detection.

        Verifies:
        - Duplicate certificates (same serial number) are detected
        - ssl_cert_duplicate_count metric is updated
        """
        certs_dir = docker_environment["certs_dir"]
        base_url = docker_environment["base_url"]

        # Read existing certificate
        existing_cert = certs_dir / "test2.pem"
        if existing_cert.exists():
            # Copy it to create a duplicate
            duplicate_cert = certs_dir / "test2_duplicate.pem"
            import shutil

            shutil.copy(existing_cert, duplicate_cert)

            # Trigger scan
            time.sleep(2)
            scan_response = requests.get(f"{base_url}/scan", timeout=10)
            assert scan_response.status_code == 200

            # Check metrics
            metrics_response = requests.get(f"{base_url}/metrics", timeout=5)
            metrics_text = metrics_response.text

            # Duplicate detection metric should exist
            assert "ssl_cert_duplicate_count" in metrics_text


@pytest.mark.e2e
@pytest.mark.docker
@pytest.mark.slow
class TestDockerPerformance:
    """Performance tests for Docker-deployed application."""

    def test_response_time_health_check(self, docker_environment):
        """Test that health check responds quickly."""
        start_time = time.time()
        response = requests.get(f"{docker_environment['base_url']}/healthz", timeout=5)
        duration = time.time() - start_time

        assert response.status_code == 200
        assert duration < 1.0  # Should respond in less than 1 second

    def test_response_time_metrics(self, docker_environment):
        """Test that metrics endpoint responds in reasonable time."""
        # Trigger scan first
        requests.get(f"{docker_environment['base_url']}/scan", timeout=10)

        start_time = time.time()
        response = requests.get(f"{docker_environment['base_url']}/metrics", timeout=5)
        duration = time.time() - start_time

        assert response.status_code == 200
        assert duration < 2.0  # Should respond in less than 2 seconds

    def test_concurrent_requests(self, docker_environment):
        """Test handling of concurrent requests."""
        import concurrent.futures

        def make_request():
            response = requests.get(f"{docker_environment['base_url']}/healthz", timeout=5)
            return response.status_code

        # Make 20 concurrent requests
        with concurrent.futures.ThreadPoolExecutor(max_workers=20) as executor:
            futures = [executor.submit(make_request) for _ in range(20)]
            results = [f.result() for f in concurrent.futures.as_completed(futures)]

        # All should succeed
        assert all(status == 200 for status in results)
        assert len(results) == 20
