// ============================================================================
// test/metrics_test.go
// ============================================================================
//go:build integration
// +build integration

package test

import (
	"context"
	"errors"
	"fmt"
	"io"
	"net/http"
	"os"
	"path/filepath"
	"strings"
	"testing"
	"time"

	"github.com/brandonhon/tls-cert-monitor/internal/config"
	"github.com/brandonhon/tls-cert-monitor/internal/health"
	"github.com/brandonhon/tls-cert-monitor/internal/logger"
	"github.com/brandonhon/tls-cert-monitor/internal/metrics"
	"github.com/brandonhon/tls-cert-monitor/internal/scanner"
	"github.com/brandonhon/tls-cert-monitor/internal/server"
	"github.com/prometheus/client_golang/prometheus"
	"go.uber.org/zap"
)

// TestAllMetricsExposedFixed tests that all expected metrics are exposed
// Refactored to reduce cyclomatic complexity (gocyclo fix)
func TestAllMetricsExposedFixed(t *testing.T) {
	// Setup test environment
	tmpDir, certDir := setupTestEnvironment(t)

	// Create and write test certificates
	writeCertificates(t, certDir)

	// Setup configuration
	cfg := createTestConfig(tmpDir, certDir)

	// Create components
	registry, metricsCollector, healthChecker, log := createTestComponents(cfg)

	// Run certificate scan
	runCertificateScan(t, cfg, metricsCollector, log)

	// Start HTTP server and fetch metrics
	metricsOutput := startServerAndFetchMetrics(t, cfg, registry, metricsCollector, healthChecker, log)

	// Parse metrics
	parsedMetrics := parsePrometheusMetrics(metricsOutput)
	t.Logf("Parsed %d metrics from HTTP response", len(parsedMetrics))

	// Debug: Print all ssl_cert metrics found
	debugSSLCertMetrics(t, parsedMetrics)

	// Run test suites
	t.Run("AllExpectedMetricsPresent", func(t *testing.T) {
		testAllExpectedMetricsPresent(t, parsedMetrics)
	})

	t.Run("OperationalMetricsValues", func(t *testing.T) {
		testOperationalMetricsValues(t, parsedMetrics)
	})

	if hasMetric(parsedMetrics, "ssl_cert_expiration_timestamp") {
		t.Run("CertificateSpecificMetrics", func(t *testing.T) {
			testCertificateSpecificMetrics(t, parsedMetrics, certDir)
		})
	}

	t.Run("DuplicateDetection", func(t *testing.T) {
		testDuplicateDetection(t, parsedMetrics)
	})

	if hasMetric(parsedMetrics, MetricSSLCertIssuerCode) {
		t.Run("IssuerClassification", func(t *testing.T) {
			testIssuerClassification(t, parsedMetrics)
		})
	}
}

// setupTestEnvironment creates the test directories
func setupTestEnvironment(t *testing.T) (string, string) {
	tmpDir := t.TempDir()
	certDir := filepath.Join(tmpDir, "certs")
	// Fixed gosec G301 - use secure directory permissions
	if err := os.MkdirAll(certDir, TestDirPermissions); err != nil {
		t.Fatal(err)
	}
	return tmpDir, certDir
}

// writeCertificates writes test certificates to the directory
func writeCertificates(t *testing.T, certDir string) {
	certSet := createCertificateTestSet(t)

	writeCertToFile(t, filepath.Join(certDir, "valid.pem"), certSet.ValidCert)
	writeCertToFile(t, filepath.Join(certDir, "weak_key.pem"), certSet.WeakKeyCert)
	writeCertToFile(t, filepath.Join(certDir, "expired.pem"), certSet.ExpiredCert)
	writeCertToFile(t, filepath.Join(certDir, "multi_san.pem"), certSet.MultiSANCert)
	writeCertToFile(t, filepath.Join(certDir, "self_signed.pem"), certSet.SelfSignedCert)
	writeCertToFile(t, filepath.Join(certDir, "duplicate.pem"), certSet.DuplicateCert)

	// Add some private key files that should be excluded
	writeCertToFile(t, filepath.Join(certDir, "server.key"), []byte("dummy private key"))
	writeCertToFile(t, filepath.Join(certDir, "private_key.pem"), []byte("dummy private key"))
}

// createTestConfig creates the test configuration
func createTestConfig(tmpDir, certDir string) *config.Config {
	return &config.Config{
		Port:                   generateTestPort(),
		BindAddress:            "127.0.0.1",
		CertificateDirectories: []string{certDir},
		ScanInterval:           1 * time.Minute,
		Workers:                1, // Single worker to ensure deterministic processing
		LogLevel:               "debug",
		CacheDir:               filepath.Join(tmpDir, "cache"),
		CacheTTL:               30 * time.Minute,
		CacheMaxSize:           10485760,
	}
}

// createTestComponents creates test components
func createTestComponents(cfg *config.Config) (*prometheus.Registry, *metrics.Collector, *health.Checker, *zap.Logger) {
	registry := prometheus.NewRegistry()
	metricsCollector := metrics.NewCollectorWithRegistry(registry)
	healthChecker := health.New(cfg, metricsCollector)
	log := logger.NewNop()
	return registry, metricsCollector, healthChecker, log
}

// runCertificateScan runs the certificate scan
func runCertificateScan(t *testing.T, cfg *config.Config, metricsCollector *metrics.Collector, log *zap.Logger) {
	certScanner, err := scanner.New(cfg, metricsCollector, log)
	if err != nil {
		t.Fatal("Failed to create scanner:", err)
	}
	defer certScanner.Close()

	// Run scan with retry logic
	ctx := context.Background()
	var scanErr error
	for attempt := 0; attempt < 3; attempt++ {
		scanErr = certScanner.Scan(ctx)
		if scanErr == nil {
			break
		}
		t.Logf("Scan attempt %d failed: %v", attempt+1, scanErr)
		time.Sleep(100 * time.Millisecond)
	}
	if scanErr != nil {
		t.Fatal("Failed to run scan after retries:", scanErr)
	}

	// Add significant delay to ensure all goroutines complete
	time.Sleep(1 * time.Second)
}

// startServerAndFetchMetrics starts the server and fetches metrics
func startServerAndFetchMetrics(t *testing.T, cfg *config.Config, registry *prometheus.Registry,
	metricsCollector *metrics.Collector, healthChecker *health.Checker, log *zap.Logger) string {

	srv := server.NewWithRegistry(cfg, metricsCollector, healthChecker, log, registry)

	// Start HTTP server
	go func() {
		// Fixed errorlint issue - use errors.Is for wrapped error comparison
		if err := srv.Start(); err != nil && !errors.Is(err, http.ErrServerClosed) {
			t.Errorf("Server start error: %v", err)
		}
	}()

	// Wait for server to start
	time.Sleep(500 * time.Millisecond)

	// Fetch metrics with retry
	metricsOutput := fetchMetricsWithRetry(t, cfg.Port)

	// Shutdown server
	shutdownCtx, cancel := context.WithTimeout(context.Background(), 5*time.Second)
	defer cancel()
	if err := srv.Shutdown(shutdownCtx); err != nil {
		t.Errorf("Server shutdown error: %v", err)
	}

	return metricsOutput
}

// fetchMetricsWithRetry fetches metrics with retry logic
func fetchMetricsWithRetry(t *testing.T, port int) string {
	var metricsOutput string
	var fetchErr error
	ctx := context.Background()

	for attempt := 0; attempt < 3; attempt++ {
		req, err := http.NewRequestWithContext(ctx, "GET", fmt.Sprintf("http://127.0.0.1:%d/metrics", port), nil)
		if err != nil {
			fetchErr = err
			time.Sleep(200 * time.Millisecond)
			continue
		}

		resp, err := http.DefaultClient.Do(req)
		if err != nil {
			fetchErr = err
			time.Sleep(200 * time.Millisecond)
			continue
		}
		// Handle close error in loop (deferInLoop fix)
		func() {
			defer func() {
				if err := resp.Body.Close(); err != nil {
					t.Logf("Failed to close response body: %v", err)
				}
			}()

			if resp.StatusCode != http.StatusOK {
				fetchErr = fmt.Errorf("metrics endpoint returned status %d", resp.StatusCode)
				return
			}

			body, err := io.ReadAll(resp.Body)
			if err != nil {
				fetchErr = err
				return
			}

			metricsOutput = string(body)
			fetchErr = nil
		}()

		if fetchErr == nil {
			break
		}
		time.Sleep(200 * time.Millisecond)
	}

	if fetchErr != nil {
		t.Fatal("Failed to fetch metrics after retries:", fetchErr)
	}

	return metricsOutput
}

// debugSSLCertMetrics prints SSL cert metrics for debugging
func debugSSLCertMetrics(t *testing.T, parsedMetrics []MetricValue) {
	t.Log("SSL cert metrics found in HTTP response:")
	for _, metric := range parsedMetrics {
		if strings.Contains(metric.Name, "ssl_cert") {
			t.Logf("  %s = %f (labels: %v)", metric.Name, metric.Value, metric.Labels)
		}
	}
}

// testAllExpectedMetricsPresent tests that all expected metrics are present
func testAllExpectedMetricsPresent(t *testing.T, parsedMetrics []MetricValue) {
	expectedMetrics := []string{
		"ssl_cert_expiration_timestamp",
		"ssl_cert_san_count",
		"ssl_cert_info",
		"ssl_cert_duplicate_count",
		MetricSSLCertIssuerCode,
		"ssl_cert_weak_key_total",
		"ssl_cert_deprecated_sigalg_total",
		"ssl_cert_files_total",
		"ssl_certs_parsed_total",
		"ssl_cert_parse_errors_total",
		"ssl_cert_scan_duration_seconds",
		"ssl_cert_last_scan_timestamp",
	}

	for _, metricName := range expectedMetrics {
		found := false
		for _, metric := range parsedMetrics {
			if metric.Name == metricName {
				found = true
				break
			}
		}
		if !found {
			t.Errorf("Metric %s not found in metrics output", metricName)
			t.Logf("Available metrics: %v", getAvailableMetricNames(parsedMetrics))
		}
	}
}

// testOperationalMetricsValues tests operational metrics values
func testOperationalMetricsValues(t *testing.T, parsedMetrics []MetricValue) {
	var filesTotal, parsedTotal, weakKeyTotal float64

	for _, metric := range parsedMetrics {
		switch metric.Name {
		case "ssl_cert_files_total":
			filesTotal = metric.Value
		case "ssl_certs_parsed_total":
			parsedTotal = metric.Value
		case "ssl_cert_weak_key_total":
			weakKeyTotal = metric.Value
		}
	}

	t.Logf("Found: files=%v, parsed=%v, weak_keys=%v", filesTotal, parsedTotal, weakKeyTotal)

	// We expect 5 certificate files (6 certs - 1 duplicate detection)
	verifyMetricValue(t, parsedMetrics, "ssl_cert_files_total", 5)
	verifyMetricValue(t, parsedMetrics, "ssl_certs_parsed_total", 5)
	verifyMetricValue(t, parsedMetrics, "ssl_cert_parse_errors_total", 0)

	// Accept either 0 or 1 weak key
	if weakKeyTotal != 0 && weakKeyTotal != 1 {
		t.Errorf("Expected 0 or 1 weak key, got %v", weakKeyTotal)
	}

	verifyMetricValue(t, parsedMetrics, "ssl_cert_deprecated_sigalg_total", 0)
}

// testCertificateSpecificMetrics tests certificate-specific metrics
func testCertificateSpecificMetrics(t *testing.T, parsedMetrics []MetricValue, certDir string) {
	expirationCount := getMetricCount(parsedMetrics, "ssl_cert_expiration_timestamp")
	sanCount := getMetricCount(parsedMetrics, "ssl_cert_san_count")
	infoCount := getMetricCount(parsedMetrics, "ssl_cert_info")

	t.Logf("Actual metrics: expiration=%d, san=%d, info=%d", expirationCount, sanCount, infoCount)

	if expirationCount != 5 {
		t.Errorf("Expected 5 expiration metrics, got %d", expirationCount)
	}

	if sanCount != 5 {
		t.Errorf("Expected 5 SAN count metrics, got %d", sanCount)
	}

	if infoCount != 5 {
		t.Errorf("Expected 5 cert info metrics, got %d", infoCount)
	}

	// Verify multi-SAN certificate
	multiSANPath := filepath.Join(certDir, "multi_san.pem")
	found := false
	for _, metric := range parsedMetrics {
		if metric.Name == "ssl_cert_san_count" {
			if path, exists := metric.Labels["path"]; exists && path == multiSANPath {
				if metric.Value != 5 {
					t.Errorf("Multi-SAN cert should have 5 SANs, got %f", metric.Value)
				}
				found = true
				break
			}
		}
	}
	if !found {
		t.Error("Could not find SAN count metric for multi-SAN certificate")
	}
}

// testDuplicateDetection tests duplicate certificate detection
func testDuplicateDetection(t *testing.T, parsedMetrics []MetricValue) {
	duplicateCount := getMetricCount(parsedMetrics, "ssl_cert_duplicate_count")
	if duplicateCount == 0 {
		t.Error("Expected to find duplicate certificate metrics")
	}

	// Verify the duplicate count is 2 for the duplicated certificate
	found := false
	for _, metric := range parsedMetrics {
		if metric.Name == "ssl_cert_duplicate_count" && metric.Value == 2 {
			found = true
			break
		}
	}
	if !found {
		t.Error("Expected to find duplicate count of 2")
	}
}

// testIssuerClassification tests issuer classification
func testIssuerClassification(t *testing.T, parsedMetrics []MetricValue) {
	issuerCount := getMetricCount(parsedMetrics, MetricSSLCertIssuerCode)
	if issuerCount == 0 {
		t.Error("Expected to find issuer classification metrics")
	}

	foundSelfSigned := false
	foundRegular := false

	for _, metric := range parsedMetrics {
		if metric.Name == MetricSSLCertIssuerCode {
			if issuer, exists := metric.Labels["issuer"]; exists {
				if strings.Contains(issuer, "Self-Signed") {
					foundSelfSigned = true
				} else {
					foundRegular = true
				}
			}
		}
	}

	if !foundSelfSigned {
		t.Error("Expected to find self-signed issuer classification")
	}
	if !foundRegular {
		t.Error("Expected to find regular issuer classification")
	}
}

// TestMetricsWithEmptyDirectoryFixed tests metrics with empty directory
func TestMetricsWithEmptyDirectoryFixed(t *testing.T) {
	// Test behavior when no certificates are found
	tmpDir := t.TempDir()
	certDir := filepath.Join(tmpDir, "empty_certs")
	// Fixed gosec G301 - use secure directory permissions
	if err := os.MkdirAll(certDir, TestDirPermissions); err != nil {
		t.Fatal(err)
	}

	// Add some private key files that should be excluded
	writeCertToFile(t, filepath.Join(certDir, "private.key"), []byte("dummy private key"))
	writeCertToFile(t, filepath.Join(certDir, "server_key.pem"), []byte("dummy private key"))

	cfg := createTestConfig(tmpDir, certDir)
	registry, metricsCollector, healthChecker, log := createTestComponents(cfg)

	// Run scan
	runCertificateScan(t, cfg, metricsCollector, log)

	// Start server and fetch metrics
	metricsOutput := startServerAndFetchMetrics(t, cfg, registry, metricsCollector, healthChecker, log)
	parsedMetrics := parsePrometheusMetrics(metricsOutput)

	// Verify metrics show empty state correctly
	verifyMetricValue(t, parsedMetrics, "ssl_cert_files_total", 0)
	verifyMetricValue(t, parsedMetrics, "ssl_certs_parsed_total", 0)
	verifyMetricValue(t, parsedMetrics, "ssl_cert_parse_errors_total", 0)
	verifyMetricValue(t, parsedMetrics, "ssl_cert_weak_key_total", 0)

	// Should still have scan duration and timestamp
	verifyMetricExists(t, parsedMetrics, "ssl_cert_scan_duration_seconds")
	verifyMetricExists(t, parsedMetrics, "ssl_cert_last_scan_timestamp")
}

// TestMetricsWithInvalidCertificatesFixed tests metrics with invalid certificates
func TestMetricsWithInvalidCertificatesFixed(t *testing.T) {
	// Test behavior with invalid certificate files
	tmpDir := t.TempDir()
	certDir := filepath.Join(tmpDir, "invalid_certs")
	// Fixed gosec G301 - use secure directory permissions
	if err := os.MkdirAll(certDir, testDirPermissions); err != nil {
		t.Fatal(err)
	}

	// Create some invalid certificate files
	invalidCertData := []byte("This is not a valid certificate")
	writeCertToFile(t, filepath.Join(certDir, "invalid1.pem"), invalidCertData)
	writeCertToFile(t, filepath.Join(certDir, "invalid2.crt"), invalidCertData)

	// Create one valid certificate for comparison
	validCert := createValidCertificate(t)
	writeCertToFile(t, filepath.Join(certDir, "valid.pem"), validCert)

	// Add some private key files that should be excluded
	writeCertToFile(t, filepath.Join(certDir, "server.key"), []byte("dummy private key"))
	writeCertToFile(t, filepath.Join(certDir, "private_key.pem"), []byte("dummy private key"))

	cfg := createTestConfig(tmpDir, certDir)
	registry, metricsCollector, healthChecker, log := createTestComponents(cfg)

	// Run scan
	runCertificateScan(t, cfg, metricsCollector, log)

	// Start server and fetch metrics
	metricsOutput := startServerAndFetchMetrics(t, cfg, registry, metricsCollector, healthChecker, log)
	parsedMetrics := parsePrometheusMetrics(metricsOutput)

	// Should find 3 certificate files (2 invalid + 1 valid, private keys excluded)
	verifyMetricValue(t, parsedMetrics, "ssl_cert_files_total", 3)

	// Should successfully parse only 1 certificate
	verifyMetricValue(t, parsedMetrics, "ssl_certs_parsed_total", 1)

	// Should have 2 parse errors
	verifyMetricValue(t, parsedMetrics, "ssl_cert_parse_errors_total", 2)
}
