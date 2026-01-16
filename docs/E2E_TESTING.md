# End-to-End (E2E) Docker Testing Guide

## Overview

The E2E Docker tests verify the entire TLS Certificate Monitor application running in a real Docker container, simulating a production deployment environment. Unlike unit tests (testing individual functions) and integration tests (testing components together), E2E tests validate the complete system from an external perspective.

## What Gets Tested

### Application Lifecycle
- ✅ Docker image builds successfully
- ✅ Container starts and initializes
- ✅ Application becomes healthy and responsive
- ✅ Graceful shutdown handling
- ✅ Container cleanup

### HTTP API Endpoints
- ✅ Health check endpoint (`/healthz`)
- ✅ Prometheus metrics endpoint (`/metrics`)
- ✅ Configuration endpoint (`/config`)
- ✅ Manual scan trigger (`/scan`)
- ✅ Cache statistics (`/cache/stats`)
- ✅ Cache clearing (`/cache/clear`)

### Certificate Scanning
- ✅ Volume mounting (certificate directory)
- ✅ Certificate discovery and parsing
- ✅ Multiple certificate formats (PEM, DER, PKCS#12/PFX)
- ✅ Password-protected P12 files (with password attempts)
- ✅ Accurate scan results
- ✅ Metrics reflect certificate data

### Security Analysis
- ✅ Weak key detection (< 2048 bits)
- ✅ Security metrics tracking
- ✅ Invalid/corrupted certificate handling
- ✅ Duplicate certificate detection

### Hot Reload Functionality
- ✅ Certificate file updates are detected reliably
- ✅ Multiple simultaneous certificate swaps (4 at once)
- ✅ New certificate additions (3 new files)
- ✅ Certificate file removals (2 files deleted)
- ✅ Metrics automatically update for ALL changes
- ✅ New certificate data replaces old data in metrics
- ✅ Comprehensive test with 9 operations total

### Production Readiness
- ✅ Response time performance
- ✅ Concurrent request handling
- ✅ Log output verification
- ✅ No critical errors during operation

## Prerequisites

### Required
- **Docker Engine**: Docker daemon must be running
  ```bash
  docker --version  # Should show Docker version
  docker ps         # Should connect successfully
  ```

- **Python Dependencies**:
  ```bash
  pip install requests  # Already in requirements.txt
  ```

### Optional
- **Docker Compose**: For advanced multi-container scenarios (future)
- **jq**: For parsing JSON output during manual testing

## Running E2E Tests

### Quick Start

```bash
# Run all E2E tests
make test-e2e

# Or use pytest directly
pytest tests/test_e2e_docker.py -v -m e2e

# Run specific test
pytest tests/test_e2e_docker.py::TestDockerE2E::test_health_endpoint -v

# Run with detailed output
pytest tests/test_e2e_docker.py -v -s -m e2e
```

### All Test Combinations

```bash
# Unit tests only
make test-unit

# Integration tests only
make test-integration

# E2E Docker tests only
make test-e2e

# Unit + Integration
make test-all

# Unit + Integration + E2E (comprehensive)
make test-full
```

### Test Execution Time

- **Unit Tests**: ~20 seconds (92 tests)
- **Integration Tests**: ~7 seconds (12 tests)
- **E2E Tests**: ~60-90 seconds (23 tests)
  - Docker image build: ~30-45 seconds
  - Container startup: ~5-10 seconds
  - Test execution: ~20-40 seconds
  - Cleanup: ~5 seconds

## Test Architecture

### Fixture: `docker_environment`

The main fixture that sets up the entire Docker environment:

```python
@pytest.fixture(scope="module")
def docker_environment(tmp_path_factory):
    """
    1. Creates temporary test directories
    2. Generates test certificates
    3. Creates test config file
    4. Builds Docker image
    5. Starts container with volumes mounted
    6. Waits for health check
    7. Yields environment info to tests
    8. Cleans up on teardown
    """
```

**Scope**: `module` - Setup once for all tests in the module, shared across test classes.

### Test Certificates

Three test certificates are generated automatically:

| File | Common Name | Validity | Purpose |
|------|-------------|----------|---------|
| `test1.pem` | app.example.com | 365 days | Standard valid cert |
| `test2.pem` | api.example.com | 365 days | Standard valid cert |
| `expiring.pem` | old.example.com | 30 days | Near-expiry testing |

### Container Configuration

- **Container Name**: `tls-cert-monitor-e2e-test`
- **Image Name**: `tls-cert-monitor:e2e-test`
- **Host Port**: `19999` (high port to avoid conflicts)
- **Container Port**: `3000` (internal)
- **Volumes**:
  - Test certificates: `/certs` (read-only)
  - Config file: `/app/config.yaml` (read-only)

## Test Classes

### `TestDockerE2E`

Comprehensive functional tests covering all features:

```bash
# Run all functional tests
pytest tests/test_e2e_docker.py::TestDockerE2E -v
```

**Tests Include** (15 tests):
- Container running verification
- All API endpoints
- Certificate scanning accuracy
- Metrics reflection
- Cache operations
- Volume mounting
- Hot reload certificate updates
- Graceful shutdown
- Production readiness checklist

### `TestDockerAdvancedFeatures`

Advanced certificate format and security feature tests:

```bash
# Run advanced feature tests
pytest tests/test_e2e_docker.py::TestDockerAdvancedFeatures -v
```

**Tests Include** (5 tests):
- PKCS#12/PFX certificate parsing with passwords
- DER format certificate parsing
- Weak key detection (1024-bit keys)
- Invalid/corrupted certificate handling
- Duplicate certificate detection

### `TestDockerPerformance`

Performance and load tests:

```bash
# Run performance tests
pytest tests/test_e2e_docker.py::TestDockerPerformance -v -m slow
```

**Tests Include** (3 tests):
- Response time benchmarks
- Concurrent request handling
- Load testing (20 simultaneous requests)

## Manual Testing

### Build and Run Container Manually

```bash
# Build image
docker build -t tls-cert-monitor:manual-test -f Dockerfile .

# Create test certificates directory
mkdir -p /tmp/e2e-test/certs
cd /tmp/e2e-test/certs

# Generate test certificate (requires openssl)
openssl req -x509 -newkey rsa:2048 -keyout key.pem -out cert.pem -days 365 -nodes \
  -subj "/CN=manual.example.com"

# Create config file
cat > /tmp/e2e-test/config.yaml <<EOF
port: 3000
bind_address: "0.0.0.0"
log_level: "INFO"
scan_interval_seconds: 60
workers: 2
certificate_directories:
  - "/certs"
cache_dir: "/tmp/cache"
hot_reload: true
dry_run: false
enable_ip_whitelist: false
EOF

# Run container
docker run -d \
  --name tls-cert-monitor-manual \
  -p 19999:3000 \
  -v /tmp/e2e-test/certs:/certs:ro \
  -v /tmp/e2e-test/config.yaml:/app/config.yaml:ro \
  tls-cert-monitor:manual-test \
  --config /app/config.yaml

# Wait for startup
sleep 5

# Test endpoints
curl http://localhost:19999/healthz | jq
curl http://localhost:19999/metrics
curl http://localhost:19999/scan | jq
curl http://localhost:19999/cache/stats | jq

# View logs
docker logs tls-cert-monitor-manual

# Cleanup
docker stop tls-cert-monitor-manual
docker rm tls-cert-monitor-manual
```

## Debugging Failed Tests

### Check Container Logs

```bash
# If tests fail, check container logs
docker logs tls-cert-monitor-e2e-test

# Follow logs in real-time
docker logs -f tls-cert-monitor-e2e-test
```

### Inspect Running Container

```bash
# Get container details
docker inspect tls-cert-monitor-e2e-test

# Execute commands inside container
docker exec tls-cert-monitor-e2e-test ls -la /certs
docker exec tls-cert-monitor-e2e-test cat /app/config.yaml
docker exec tls-cert-monitor-e2e-test ps aux
```

### Test with Pytest Verbosity

```bash
# Maximum verbosity + show print statements
pytest tests/test_e2e_docker.py -vv -s -m e2e

# Show fixtures
pytest tests/test_e2e_docker.py --fixtures

# Detailed error tracebacks
pytest tests/test_e2e_docker.py -v --tb=long -m e2e
```

### Common Issues

#### Issue: "Docker daemon not running"

**Symptoms**:
```
Cannot connect to the Docker daemon at unix:///var/run/docker.sock
```

**Solution**:
```bash
# Start Docker service (Linux)
sudo systemctl start docker

# Or Docker Desktop (macOS/Windows)
# Start Docker Desktop application
```

#### Issue: "Port already in use"

**Symptoms**:
```
Error starting userland proxy: listen tcp4 0.0.0.0:19999: bind: address already in use
```

**Solution**:
```bash
# Find process using port 19999
lsof -i :19999
sudo netstat -tulpn | grep 19999

# Stop conflicting container
docker stop $(docker ps -q --filter "publish=19999")

# Or change HOST_PORT in test file
```

#### Issue: "Container not becoming healthy"

**Symptoms**:
```
Container did not become healthy in time
```

**Solution**:
```bash
# Check container logs for errors
docker logs tls-cert-monitor-e2e-test

# Try building image fresh
docker rmi tls-cert-monitor:e2e-test
docker build --no-cache -t tls-cert-monitor:e2e-test -f Dockerfile .

# Increase timeout in test (edit TIMEOUT in fixture)
```

#### Issue: "Permission denied mounting volumes"

**Symptoms**:
```
docker: Error response from daemon: error while creating mount source path
```

**Solution**:
```bash
# Ensure temp directories have proper permissions
chmod 755 /tmp/pytest-*

# Check SELinux context (if applicable)
ls -Z /tmp/pytest-*
```

## CI/CD Integration

### GitHub Actions

The E2E tests can be added to CI/CD pipelines:

```yaml
# .github/workflows/ci.yml
jobs:
  e2e-tests:
    name: E2E Docker Tests
    runs-on: ubuntu-latest

    steps:
    - name: Checkout code
      uses: actions/checkout@v4

    - name: Set up Python
      uses: actions/setup-python@v5
      with:
        python-version: "3.11"

    - name: Install dependencies
      run: |
        pip install -r requirements.txt
        pip install -r requirements-dev.txt

    - name: Run E2E tests
      run: make test-e2e

    - name: Upload container logs on failure
      if: failure()
      uses: actions/upload-artifact@v4
      with:
        name: e2e-logs
        path: |
          /tmp/e2e-*.log
```

### Local Pre-Commit Hook

```bash
# .git/hooks/pre-push
#!/bin/bash
echo "Running E2E tests before push..."
make test-e2e || exit 1
```

## Best Practices

### Writing New E2E Tests

1. **Use the docker_environment fixture** - Don't create your own containers
2. **Test from external perspective** - Use HTTP requests, don't import app code
3. **Verify production behavior** - Test what users/monitoring systems see
4. **Clean up resources** - Fixture handles cleanup, but avoid leaving dangling resources
5. **Make tests independent** - Each test should work in isolation
6. **Use meaningful assertions** - Check specific values, not just status codes

### Example Test Structure

```python
@pytest.mark.e2e
@pytest.mark.docker
def test_new_feature(self, docker_environment):
    """Test description of what this validates."""
    # Given: Setup conditions
    base_url = docker_environment["base_url"]

    # When: Perform action
    response = requests.get(f"{base_url}/endpoint", timeout=5)

    # Then: Verify results
    assert response.status_code == 200
    assert "expected_field" in response.json()
```

## Performance Benchmarks

### Expected Response Times

| Endpoint | Expected | Acceptable | Poor |
|----------|----------|------------|------|
| `/healthz` | < 100ms | < 1s | > 1s |
| `/metrics` | < 500ms | < 2s | > 2s |
| `/config` | < 100ms | < 1s | > 1s |
| `/scan` | < 2s | < 10s | > 10s |
| `/cache/stats` | < 100ms | < 1s | > 1s |

### Concurrent Load

The application should handle:
- **20 simultaneous requests** without errors
- **Response time degradation** < 2x under load
- **No crashes** or container restarts

## Future Enhancements

### Planned Features

- [ ] Multi-container testing with docker-compose
- [ ] TLS/SSL endpoint testing
- [ ] Hot reload testing with file watches
- [ ] Resource limit testing (CPU/memory)
- [ ] Network isolation testing
- [ ] Health check retry logic testing
- [ ] Crash recovery testing
- [ ] Volume backup/restore testing

### Adding New Tests

When adding new features to the application:

1. **Add E2E test** for the feature in `test_e2e_docker.py`
2. **Test from user perspective** - external HTTP calls only
3. **Verify in production scenario** - test in Docker container
4. **Document expected behavior** in test docstring
5. **Update this guide** if new setup is required

## Resources

- [Docker Documentation](https://docs.docker.com/)
- [pytest Documentation](https://docs.pytest.org/)
- [requests Library](https://requests.readthedocs.io/)
- [Docker Python SDK](https://docker-py.readthedocs.io/) (for advanced scenarios)

## Support

For issues with E2E tests:

1. Check container logs: `docker logs tls-cert-monitor-e2e-test`
2. Verify Docker is running: `docker ps`
3. Run with verbose output: `pytest tests/test_e2e_docker.py -vv -s`
4. Check this documentation for troubleshooting steps
5. Create an issue with logs and error output
