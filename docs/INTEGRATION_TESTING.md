# Integration Testing Guide

## Overview

The TLS Certificate Monitor includes comprehensive integration tests that verify the entire application working together in a running environment. These tests go beyond unit tests by testing:

- Complete application lifecycle (startup → operation → shutdown)
- Real certificate file scanning
- Live API endpoints with HTTP requests
- Metrics collection and exposure
- Hot reload functionality
- Cache persistence
- Concurrent operations
- Error handling with real scenarios

## Quick Start

```bash
# Run all tests (unit + integration)
make test-all

# Run only integration tests
make test-integration

# Run only unit tests
make test-unit

# Run with verbose output
pytest tests/test_integration.py -v -m integration
```

## Test Structure

### Integration Test File

**Location**: `tests/test_integration.py`

**Test Classes**:
1. `TestFullApplicationIntegration` - Core functionality tests
2. `TestPerformanceAndStability` - Performance and stress tests

### What Gets Tested

#### 1. Application Lifecycle
- ✅ Clean startup and initialization
- ✅ Component initialization (scanner, metrics, cache)
- ✅ Graceful shutdown
- ✅ Resource cleanup

#### 2. Certificate Scanning
- ✅ Scanning real PEM certificate files
- ✅ Processing multiple certificates
- ✅ Handling invalid certificates gracefully
- ✅ Accurate scan result reporting

#### 3. API Endpoints
- ✅ `/healthz` - Health check endpoint
- ✅ `/metrics` - Prometheus metrics endpoint
- ✅ `/config` - Configuration endpoint
- ✅ `/scan` - Manual scan trigger
- ✅ `/cache/stats` - Cache statistics
- ✅ `/cache/clear` - Cache clearing

#### 4. Metrics Collection
- ✅ Certificate expiration metrics
- ✅ Certificate information metrics
- ✅ Scan performance metrics
- ✅ System resource metrics
- ✅ Metric accuracy and consistency

#### 5. Caching System
- ✅ Cache storage and retrieval
- ✅ Cache hit/miss tracking
- ✅ Cache persistence
- ✅ Cache clearing
- ✅ Performance improvement verification

#### 6. Hot Reload
- ✅ Certificate file addition detection
- ✅ Certificate file modification detection
- ✅ Certificate file deletion detection
- ✅ Automatic re-scan on changes

#### 7. Concurrency Control
- ✅ Concurrent scan prevention (via locks)
- ✅ Multiple simultaneous requests handling
- ✅ Race condition prevention

#### 8. Error Handling
- ✅ Invalid certificate files
- ✅ Missing files
- ✅ Permission errors
- ✅ Malformed data

#### 9. Performance
- ✅ Rapid successive scans
- ✅ Large certificate sets (50+ certs)
- ✅ Cache performance impact
- ✅ Memory cleanup verification

## Running Integration Tests

### Standard Execution

```bash
# Recommended: Use Makefile targets
make test-integration

# Or use pytest directly
pytest tests/test_integration.py -v -m integration

# Run specific test
pytest tests/test_integration.py::TestFullApplicationIntegration::test_api_endpoints_with_running_server -v
```

### With Coverage

```bash
# Run integration tests with coverage
pytest tests/test_integration.py --cov=tls_cert_monitor --cov-report=html -m integration

# View coverage report
open htmlcov/index.html  # macOS
xdg-open htmlcov/index.html  # Linux
```

### Debugging Integration Tests

```bash
# Run with detailed output
pytest tests/test_integration.py -vv -s -m integration

# Run specific test with debugging
pytest tests/test_integration.py::TestFullApplicationIntegration::test_complete_application_lifecycle -vv -s --log-cli-level=DEBUG
```

### Performance Testing

```bash
# Run only performance tests
pytest tests/test_integration.py::TestPerformanceAndStability -v -m integration

# With timing information
pytest tests/test_integration.py -v -m integration --durations=10
```

## Test Fixtures

### Temporary Test Environment

All integration tests use temporary directories that are automatically cleaned up:

```python
@pytest.fixture
async def test_certs_dir(tmp_path: Path) -> Path:
    """Temporary directory for test certificates."""
    certs_dir = tmp_path / "certs"
    certs_dir.mkdir()
    return certs_dir
```

### Test Configuration

```python
@pytest.fixture
async def test_config(test_certs_dir: Path, tmp_path: Path) -> Config:
    """Test configuration with temporary paths."""
    return Config(
        certificate_directories=[str(test_certs_dir)],
        port=0,  # Random port
        bind_address="127.0.0.1",
        scan_interval_seconds=300,
        workers=2,
        log_level="DEBUG",
        enable_ip_whitelist=False,
    )
```

### Application Components

```python
@pytest.fixture
async def app_components(test_config: Config):
    """Fully initialized application components."""
    metrics = MetricsCollector()
    cache = CacheManager(test_config)
    await cache.initialize()
    scanner = CertificateScanner(config=test_config, cache=cache, metrics=metrics)

    yield (test_config, scanner, metrics, cache)

    # Automatic cleanup
    await cache.close()
```

## Test Certificate Generation

Integration tests generate real X.509 certificates on-the-fly:

```python
def generate_test_certificate(path: Path, cn: str = "test.example.com") -> None:
    """Generate a test X.509 certificate with:
    - RSA 2048-bit key
    - SHA256 signature
    - 1 year validity
    - Subject Alternative Name
    - Self-signed
    """
```

## CI/CD Integration

### GitHub Actions

Integration tests are run as part of the CI pipeline:

```yaml
# .github/workflows/ci.yml
- name: Run quality checks
  run: make check-system

- name: Run tests
  run: make test-system  # Includes integration tests
```

### Local Pre-Commit

Run integration tests before pushing:

```bash
# Add to .git/hooks/pre-push
#!/bin/bash
make test-integration
```

## Best Practices

### When to Add Integration Tests

Add integration tests when:
- ✅ Adding new API endpoints
- ✅ Changing application startup/shutdown logic
- ✅ Modifying certificate scanning logic
- ✅ Adding new metrics
- ✅ Changing hot reload behavior
- ✅ Adding new configuration options

### Writing New Integration Tests

```python
@pytest.mark.asyncio
@pytest.mark.integration
async def test_new_feature(app_components, test_certs_dir):
    """Test description."""
    config, scanner, metrics, cache = app_components

    # 1. Setup test data
    generate_test_certificate(test_certs_dir / "test.pem")

    # 2. Perform operation
    result = await scanner.scan_once()

    # 3. Verify results
    assert result["summary"]["total_parsed"] == 1
```

### Test Isolation

Each test should be independent:
- ✅ Use fresh temporary directories
- ✅ Don't rely on other tests' state
- ✅ Clean up resources in fixtures
- ✅ Use unique certificate names

### Performance Considerations

- Keep test certificate counts reasonable (< 100 per test)
- Use `await asyncio.sleep()` sparingly
- Verify tests complete in reasonable time (< 30s each)
- Use `--durations` to identify slow tests

## Troubleshooting

### Test Failures

#### "Address already in use"
```bash
# Port conflict - tests use port 0 (random) but may conflict
# Solution: Run tests sequentially or increase delays
pytest tests/test_integration.py -v --dist=no
```

#### "Certificate generation failed"
```bash
# Missing cryptography dependencies
pip install cryptography
```

#### "Timeout waiting for scan"
```bash
# Increase timeout in test
await asyncio.wait_for(scanner.scan_once(), timeout=30)
```

### Debugging Tips

```python
# Add logging to tests
import logging
logging.basicConfig(level=logging.DEBUG)

# Print intermediate values
print(f"Scan result: {result}")

# Use pytest breakpoints
import pytest; pytest.set_trace()

# Check temp directory contents
print(f"Test files: {list(test_certs_dir.glob('*'))}")
```

## Example Test Run

```bash
$ make test-integration

🚀 Running integration tests...
⚠️  Integration tests start the full application

tests/test_integration.py::TestFullApplicationIntegration::test_application_startup_and_shutdown PASSED [  8%]
tests/test_integration.py::TestFullApplicationIntegration::test_certificate_scanning_with_real_files PASSED [ 16%]
tests/test_integration.py::TestFullApplicationIntegration::test_api_endpoints_with_running_server PASSED [ 25%]
tests/test_integration.py::TestFullApplicationIntegration::test_metrics_collection_accuracy PASSED [ 33%]
tests/test_integration.py::TestFullApplicationIntegration::test_cache_persistence_and_retrieval PASSED [ 41%]
tests/test_integration.py::TestFullApplicationIntegration::test_hot_reload_with_certificate_changes PASSED [ 50%]
tests/test_integration.py::TestFullApplicationIntegration::test_concurrent_scans_prevented PASSED [ 58%]
tests/test_integration.py::TestFullApplicationIntegration::test_error_handling_with_invalid_certificates PASSED [ 66%]
tests/test_integration.py::TestFullApplicationIntegration::test_memory_cleanup_after_large_scan PASSED [ 75%]
tests/test_integration.py::TestFullApplicationIntegration::test_complete_application_lifecycle PASSED [ 83%]
tests/test_integration.py::TestPerformanceAndStability::test_rapid_successive_scans PASSED [ 91%]
tests/test_integration.py::TestPerformanceAndStability::test_cache_performance_improvement PASSED [100%]

✅ Integration tests completed

12 passed in 15.43s
```

## Continuous Improvement

### Test Metrics

Track test health over time:
- Test execution time
- Test failure rate
- Code coverage from integration tests
- Number of real bugs caught

### Adding Coverage

Priority areas for new integration tests:
1. Windows service functionality
2. macOS LaunchDaemon functionality
3. TLS/SSL endpoint testing
4. Multi-directory scanning
5. P12/PFX password trying
6. Network-based certificate fetching (if added)

## End-to-End (E2E) Docker Testing

For production-like testing in real Docker containers, see the [E2E Testing Guide](E2E_TESTING.md).

**Key Differences**:
- **Integration Tests**: Run in-process, test components working together
- **E2E Tests**: Run in Docker containers, test from external perspective (HTTP only)

**When to Use**:
- Integration tests for rapid development feedback
- E2E tests for production deployment validation and Docker-specific issues

**Running E2E Tests**:
```bash
make test-e2e  # Requires Docker daemon running
```

## Resources

- [pytest Documentation](https://docs.pytest.org/)
- [pytest-asyncio](https://pytest-asyncio.readthedocs.io/)
- [FastAPI Testing](https://fastapi.tiangolo.com/tutorial/testing/)
- [Python cryptography](https://cryptography.io/)
- [E2E Testing Guide](E2E_TESTING.md) - Docker-based end-to-end tests

## Support

For questions or issues with integration tests:
1. Check this documentation
2. Review test output carefully
3. Enable DEBUG logging
4. Create an issue with:
   - Test command used
   - Full output
   - Python version
   - OS version
