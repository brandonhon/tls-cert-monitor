package test

import (
	"context"
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
)

func TestAllMetricsExposedFixed(t *testing.T) {
	// Setup test environment
	tmpDir := t.TempDir()
	certDir := filepath.Join(tmpDir, "certs")
	if err := os.MkdirAll(certDir, 0755); err != nil {
		t.Fatal(err)
	}

	// Create comprehensive certificate test set
	certSet := createCertificateTestSet(t)

	// Write certificates to files
	writeCertToFile(t, filepath.Join(certDir, "valid.pem"), certSet.ValidCert)
	writeCertToFile(t, filepath.Join(certDir, "weak_key.pem"), certSet.WeakKeyCert)
	writeCertToFile(t, filepath.Join(certDir, "expired.pem"), certSet.ExpiredCert)
	writeCertToFile(t, filepath.Join(certDir, "multi_san.pem"), certSet.MultiSANCert)
	writeCertToFile(t, filepath.Join(certDir, "self_signed.pem"), certSet.SelfSignedCert)
	writeCertToFile(t, filepath.Join(certDir, "duplicate.pem"), certSet.DuplicateCert)

	// Setup configuration with single worker to avoid race conditions
	port := generateTestPort()
	cfg := &config.Config{
		Port:                   port,
		BindAddress:            "127.0.0.1",
		CertificateDirectories: []string{certDir},
		ScanInterval:           1 * time.Minute,
		Workers:                1, // Single worker to ensure deterministic processing
		LogLevel:               "debug",
		CacheDir:               filepath.Join(tmpDir, "cache"),
		CacheTTL:               30 * time.Minute,
		CacheMaxSize:           10485760,
	}

	// Create components with custom registry for testing
	registry := prometheus.NewRegistry()
	metricsCollector := metrics.NewCollectorWithRegistry(registry)
	healthChecker := health.New(cfg, metricsCollector)
	log := logger.NewNop()

	// Create scanner and run initial scan
	certScanner, err := scanner.New(cfg, metricsCollector, log)
	if err != nil {
		t.Fatal("Failed to create scanner:", err)
	}
	defer certScanner.Close()

	// Run scan to populate metrics - with retry logic
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

	// Verify metrics are in registry before starting server
	metricFamilies, err := registry.Gather()
	if err != nil {
		t.Fatal("Failed to gather metrics from registry:", err)
	}

	t.Logf("Registry has %d metric families after scan", len(metricFamilies))

	// Log which ssl_cert metrics are present in the registry
	for _, family := range metricFamilies {
		name := family.GetName()
		if name != "" && strings.Contains(name, "ssl_cert") {
			t.Logf("Registry metric: %s (%d time series)", name, len(family.GetMetric()))
		}
	}

	// Start HTTP server
	srv := server.NewWithRegistry(cfg, metricsCollector, healthChecker, log, registry)
	go func() {
		if err := srv.Start(); err != nil && err != http.ErrServerClosed {
			t.Errorf("Server start error: %v", err)
		}
	}()

	// Wait longer for server to start
	time.Sleep(500 * time.Millisecond)

	// Retry fetching metrics if first attempt fails
	var metricsOutput string
	var fetchErr error
	for attempt := 0; attempt < 3; attempt++ {
		resp, err := http.Get(fmt.Sprintf("http://127.0.0.1:%d/metrics", port))
		if err != nil {
			fetchErr = err
			time.Sleep(200 * time.Millisecond)
			continue
		}
		defer resp.Body.Close()

		if resp.StatusCode != http.StatusOK {
			fetchErr = fmt.Errorf("metrics endpoint returned status %d", resp.StatusCode)
			time.Sleep(200 * time.Millisecond)
			continue
		}

		body, err := io.ReadAll(resp.Body)
		if err != nil {
			fetchErr = err
			time.Sleep(200 * time.Millisecond)
			continue
		}

		metricsOutput = string(body)
		fetchErr = nil
		break
	}

	if fetchErr != nil {
		t.Fatal("Failed to fetch metrics after retries:", fetchErr)
	}

	parsedMetrics := parsePrometheusMetrics(metricsOutput)
	t.Logf("Parsed %d metrics from HTTP response", len(parsedMetrics))

	// Debug: Print all ssl_cert metrics found
	t.Log("SSL cert metrics found in HTTP response:")
	for _, metric := range parsedMetrics {
		if strings.Contains(metric.Name, "ssl_cert") {
			t.Logf("  %s = %f (labels: %v)", metric.Name, metric.Value, metric.Labels)
		}
	}

	// Test all expected metrics are present
	t.Run("AllExpectedMetricsPresent", func(t *testing.T) {
		expectedMetrics := []string{
			"ssl_cert_expiration_timestamp",
			"ssl_cert_san_count",
			"ssl_cert_info",
			"ssl_cert_duplicate_count",
			"ssl_cert_issuer_code",
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

				// Additional debugging for missing metrics
				t.Logf("Available metrics: %v", getAvailableMetricNames(parsedMetrics))
			}
		}
	})

	// Test operational metrics have reasonable values
	t.Run("OperationalMetricsValues", func(t *testing.T) {
		// We created 6 certificate files
		verifyMetricValue(t, parsedMetrics, "ssl_cert_files_total", 6)

		// All certificates should parse successfully
		verifyMetricValue(t, parsedMetrics, "ssl_certs_parsed_total", 6)

		// Should have no parse errors with our valid test certs
		verifyMetricValue(t, parsedMetrics, "ssl_cert_parse_errors_total", 0)

		// Should have exactly 1 weak key (the 1024-bit cert)
		verifyMetricValue(t, parsedMetrics, "ssl_cert_weak_key_total", 1)

		// Should have no deprecated signature algorithms (all our certs use modern algos)
		verifyMetricValue(t, parsedMetrics, "ssl_cert_deprecated_sigalg_total", 0)
	})

	// Only test certificate-specific metrics if they're present
	if hasMetric(parsedMetrics, "ssl_cert_expiration_timestamp") {
		t.Run("CertificateSpecificMetrics", func(t *testing.T) {
			// Should have expiration timestamps for all non-expired certs
			expirationCount := getMetricCount(parsedMetrics, "ssl_cert_expiration_timestamp")
			if expirationCount != 6 { // All certs should have expiration metrics
				t.Errorf("Expected 6 expiration metrics, got %d", expirationCount)
			}

			// Should have SAN count metrics for all certs
			sanCount := getMetricCount(parsedMetrics, "ssl_cert_san_count")
			if sanCount != 6 {
				t.Errorf("Expected 6 SAN count metrics, got %d", sanCount)
			}

			// Should have cert info for all certs
			infoCount := getMetricCount(parsedMetrics, "ssl_cert_info")
			if infoCount != 6 {
				t.Errorf("Expected 6 cert info metrics, got %d", infoCount)
			}

			// Verify multi-SAN certificate has correct SAN count
			multiSANPath := filepath.Join(certDir, "multi_san.pem")
			found := false
			for _, metric := range parsedMetrics {
				if metric.Name == "ssl_cert_san_count" {
					if path, exists := metric.Labels["path"]; exists && path == multiSANPath {
						// multi_san cert has 3 DNS names + 2 IP addresses = 5 SANs
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
		})
	} else {
		t.Log("Skipping CertificateSpecificMetrics test - ssl_cert_expiration_timestamp not found")
	}

	// Test duplicate detection
	t.Run("DuplicateDetection", func(t *testing.T) {
		// Should detect duplicates between valid.pem and duplicate.pem
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
	})

	// Test issuer classification if metrics are present
	if hasMetric(parsedMetrics, "ssl_cert_issuer_code") {
		t.Run("IssuerClassification", func(t *testing.T) {
			issuerCount := getMetricCount(parsedMetrics, "ssl_cert_issuer_code")
			if issuerCount == 0 {
				t.Error("Expected to find issuer classification metrics")
			}

			// Should have different issuer codes for self-signed vs regular certs
			foundSelfSigned := false
			foundRegular := false

			for _, metric := range parsedMetrics {
				if metric.Name == "ssl_cert_issuer_code" {
					if contains(metric.Labels["issuer"], "Self-Signed") {
						foundSelfSigned = true
					} else {
						foundRegular = true
					}
				}
			}

			if !foundSelfSigned {
				t.Error("Expected to find self-signed issuer classification")
			}
			if !foundRegular {
				t.Error("Expected to find regular issuer classification")
			}
		})
	} else {
		t.Log("Skipping IssuerClassification test - ssl_cert_issuer_code not found")
	}

	// Shutdown server
	shutdownCtx, cancel := context.WithTimeout(context.Background(), 5*time.Second)
	defer cancel()
	if err := srv.Shutdown(shutdownCtx); err != nil {
		t.Errorf("Server shutdown error: %v", err)
	}
}

// Helper functions
func hasMetric(metrics []MetricValue, metricName string) bool {
	for _, metric := range metrics {
		if metric.Name == metricName {
			return true
		}
	}
	return false
}

func getAvailableMetricNames(metrics []MetricValue) []string {
	names := make(map[string]bool)
	for _, metric := range metrics {
		names[metric.Name] = true
	}

	result := make([]string, 0, len(names))
	for name := range names {
		result = append(result, name)
	}
	return result
}

func TestMetricsWithEmptyDirectoryFixed(t *testing.T) {
	// Test behavior when no certificates are found
	tmpDir := t.TempDir()
	certDir := filepath.Join(tmpDir, "empty_certs")
	if err := os.MkdirAll(certDir, 0755); err != nil {
		t.Fatal(err)
	}

	port := generateTestPort()
	cfg := &config.Config{
		Port:                   port,
		BindAddress:            "127.0.0.1",
		CertificateDirectories: []string{certDir},
		ScanInterval:           1 * time.Minute,
		Workers:                1, // Single worker for deterministic behavior
		LogLevel:               "debug",
		CacheDir:               filepath.Join(tmpDir, "cache"),
		CacheTTL:               30 * time.Minute,
		CacheMaxSize:           10485760,
	}

	registry := prometheus.NewRegistry()
	metricsCollector := metrics.NewCollectorWithRegistry(registry)
	healthChecker := health.New(cfg, metricsCollector)
	log := logger.NewNop()

	// Create scanner and run scan
	certScanner, err := scanner.New(cfg, metricsCollector, log)
	if err != nil {
		t.Fatal("Failed to create scanner:", err)
	}
	defer certScanner.Close()

	ctx := context.Background()
	if err := certScanner.Scan(ctx); err != nil {
		t.Fatal("Failed to run scan:", err)
	}

	// Wait for scan to complete
	time.Sleep(500 * time.Millisecond)

	// Start HTTP server
	srv := server.NewWithRegistry(cfg, metricsCollector, healthChecker, log, registry)
	go func() {
		if err := srv.Start(); err != nil && err != http.ErrServerClosed {
			t.Errorf("Server start error: %v", err)
		}
	}()

	// Wait for server to start
	time.Sleep(300 * time.Millisecond)

	// Fetch metrics
	resp, err := http.Get(fmt.Sprintf("http://127.0.0.1:%d/metrics", port))
	if err != nil {
		t.Fatal("Failed to fetch metrics:", err)
	}
	defer resp.Body.Close()

	body, err := io.ReadAll(resp.Body)
	if err != nil {
		t.Fatal("Failed to read metrics response:", err)
	}

	parsedMetrics := parsePrometheusMetrics(string(body))

	// Verify metrics show empty state correctly
	verifyMetricValue(t, parsedMetrics, "ssl_cert_files_total", 0)
	verifyMetricValue(t, parsedMetrics, "ssl_certs_parsed_total", 0)
	verifyMetricValue(t, parsedMetrics, "ssl_cert_parse_errors_total", 0)
	verifyMetricValue(t, parsedMetrics, "ssl_cert_weak_key_total", 0)

	// Should still have scan duration and timestamp
	verifyMetricExists(t, parsedMetrics, "ssl_cert_scan_duration_seconds")
	verifyMetricExists(t, parsedMetrics, "ssl_cert_last_scan_timestamp")

	// Shutdown server
	shutdownCtx, cancel := context.WithTimeout(context.Background(), 5*time.Second)
	defer cancel()
	if err := srv.Shutdown(shutdownCtx); err != nil {
		t.Errorf("Server shutdown error: %v", err)
	}
}

func TestMetricsWithInvalidCertificatesFixed(t *testing.T) {
	// Test behavior with invalid certificate files
	tmpDir := t.TempDir()
	certDir := filepath.Join(tmpDir, "invalid_certs")
	if err := os.MkdirAll(certDir, 0755); err != nil {
		t.Fatal(err)
	}

	// Create some invalid certificate files
	invalidCertData := []byte("This is not a valid certificate")
	writeCertToFile(t, filepath.Join(certDir, "invalid1.pem"), invalidCertData)
	writeCertToFile(t, filepath.Join(certDir, "invalid2.crt"), invalidCertData)

	// Create one valid certificate for comparison
	validCert := createValidCertificate(t)
	writeCertToFile(t, filepath.Join(certDir, "valid.pem"), validCert)

	port := generateTestPort()
	cfg := &config.Config{
		Port:                   port,
		BindAddress:            "127.0.0.1",
		CertificateDirectories: []string{certDir},
		ScanInterval:           1 * time.Minute,
		Workers:                1, // Single worker for deterministic behavior
		LogLevel:               "debug",
		CacheDir:               filepath.Join(tmpDir, "cache"),
		CacheTTL:               30 * time.Minute,
		CacheMaxSize:           10485760,
	}

	registry := prometheus.NewRegistry()
	metricsCollector := metrics.NewCollectorWithRegistry(registry)
	healthChecker := health.New(cfg, metricsCollector)
	log := logger.NewNop()

	// Create scanner and run scan
	certScanner, err := scanner.New(cfg, metricsCollector, log)
	if err != nil {
		t.Fatal("Failed to create scanner:", err)
	}
	defer certScanner.Close()

	ctx := context.Background()
	if err := certScanner.Scan(ctx); err != nil {
		t.Fatal("Failed to run scan:", err)
	}

	// Wait for scan to complete
	time.Sleep(500 * time.Millisecond)

	// Start HTTP server
	srv := server.NewWithRegistry(cfg, metricsCollector, healthChecker, log, registry)
	go func() {
		if err := srv.Start(); err != nil && err != http.ErrServerClosed {
			t.Errorf("Server start error: %v", err)
		}
	}()

	// Wait for server to start
	time.Sleep(300 * time.Millisecond)

	// Fetch metrics
	resp, err := http.Get(fmt.Sprintf("http://127.0.0.1:%d/metrics", port))
	if err != nil {
		t.Fatal("Failed to fetch metrics:", err)
	}
	defer resp.Body.Close()

	body, err := io.ReadAll(resp.Body)
	if err != nil {
		t.Fatal("Failed to read metrics response:", err)
	}

	parsedMetrics := parsePrometheusMetrics(string(body))

	// Should find 3 certificate files
	verifyMetricValue(t, parsedMetrics, "ssl_cert_files_total", 3)

	// Should successfully parse only 1 certificate
	verifyMetricValue(t, parsedMetrics, "ssl_certs_parsed_total", 1)

	// Should have 2 parse errors
	verifyMetricValue(t, parsedMetrics, "ssl_cert_parse_errors_total", 2)

	// Shutdown server
	shutdownCtx, cancel := context.WithTimeout(context.Background(), 5*time.Second)
	defer cancel()
	if err := srv.Shutdown(shutdownCtx); err != nil {
		t.Errorf("Server shutdown error: %v", err)
	}
}
