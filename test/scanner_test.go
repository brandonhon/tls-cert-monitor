
// ============================================================================
// test/scanner_test.go
// ============================================================================
//go:build integration
// +build integration

package test

import (
	"context"
	"os"
	"path/filepath"
	"testing"
	"time"

	"github.com/brandonhon/tls-cert-monitor/internal/config"
	"github.com/brandonhon/tls-cert-monitor/internal/logger"
	"github.com/brandonhon/tls-cert-monitor/internal/metrics"
	"github.com/brandonhon/tls-cert-monitor/internal/scanner"
	"github.com/prometheus/client_golang/prometheus"
	dto "github.com/prometheus/client_model/go"
)

func TestCertificateScanning(t *testing.T) {
	tmpDir := t.TempDir()
	certDir := filepath.Join(tmpDir, "certs")
	// Fixed gosec G301 - use secure directory permissions
	if err := os.MkdirAll(certDir, TestDirPermissions); err != nil {
		t.Fatal(err)
	}

	// Generate test certificates
	goodCert := generateTestCertificate(t, 2048, time.Now().Add(365*24*time.Hour))
	weakCert := generateTestCertificate(t, 1024, time.Now().Add(365*24*time.Hour))
	expiredCert := generateTestCertificate(t, 2048, time.Now().Add(-24*time.Hour))

	// Write certificates to files
	writeCertToFile(t, filepath.Join(certDir, "good.pem"), goodCert)
	writeCertToFile(t, filepath.Join(certDir, "weak.pem"), weakCert)
	writeCertToFile(t, filepath.Join(certDir, "expired.pem"), expiredCert)

	// Add some private key files that should be excluded
	writeCertToFile(t, filepath.Join(certDir, "private.key"), []byte("dummy private key"))
	writeCertToFile(t, filepath.Join(certDir, "server_key.pem"), []byte("dummy private key"))

	// Create scanner configuration
	cfg := &config.Config{
		Port:                   generateTestPort(),
		BindAddress:            "127.0.0.1",
		CertificateDirectories: []string{certDir},
		ScanInterval:           1 * time.Minute,
		Workers:                2,
		LogLevel:               "debug",
		CacheDir:               filepath.Join(tmpDir, "cache"),
		CacheTTL:               30 * time.Minute,
		CacheMaxSize:           10485760,
	}

	// Create scanner with test registry
	registry := prometheus.NewRegistry()
	metricsCollector := metrics.NewCollectorWithRegistry(registry)
	log := logger.NewNop()

	s, err := scanner.New(cfg, metricsCollector, log)
	if err != nil {
		t.Fatal(err)
	}
	defer s.Close()

	// Perform scan
	ctx := context.Background()
	if err := s.Scan(ctx); err != nil {
		t.Fatal(err)
	}

	// Verify metrics - should only count certificate files, not private keys
	metricsMap := metricsCollector.GetMetrics()

	// Should only find 3 certificate files (private keys excluded)
	if metricsMap["cert_files_total"] != 3 {
		t.Errorf("Expected 3 certificate files, got %v", metricsMap["cert_files_total"])
	}

	if metricsMap["certs_parsed_total"] != 3 {
		t.Errorf("Expected 3 parsed certificates, got %v", metricsMap["certs_parsed_total"])
	}

	if metricsMap["weak_key_total"] != 1 {
		t.Errorf("Expected 1 weak key, got %v", metricsMap["weak_key_total"])
	}
}

func TestCertificateFileDetection(t *testing.T) {
	tmpDir := t.TempDir()

	// Create test files with various extensions
	testFiles := []struct {
		name   string
		isCert bool
	}{
		// Certificate files - should be included
		{"cert.pem", true},
		{"cert.crt", true},
		{"cert.cer", true},
		{"cert.der", true},
		{"certificate.pem", true},
		{"ca-cert.pem", true},
		{"chain.pem", true},
		{"bundle.pem", true},
		{"cacert.pem", true},

		// Private key files - should be excluded
		{"private.key", false},
		{"server.key", false},
		{"cert_key.pem", false},
		{"server-key.pem", false},
		{"private.pem", false},
		{"server.pem.key", false},

		// Non-certificate files - should be excluded
		{"nothing.txt", false},
		{"readme.md", false},
		{"config.yaml", false},
	}

	for _, tf := range testFiles {
		path := filepath.Join(tmpDir, tf.name)
		// Fixed gosec G306 - use secure file permissions
		if err := os.WriteFile(path, []byte("test"), TestFilePermissions); err != nil {
			t.Fatal(err)
		}
	}

	cfg := &config.Config{
		CertificateDirectories: []string{tmpDir},
		Workers:                1,
		CacheDir:               filepath.Join(tmpDir, "cache"),
		CacheTTL:               30 * time.Minute,
		CacheMaxSize:           10485760,
		ScanInterval:           1 * time.Minute,
	}

	registry := prometheus.NewRegistry()
	metricsCollector := metrics.NewCollectorWithRegistry(registry)
	log := logger.NewNop()

	s, err := scanner.New(cfg, metricsCollector, log)
	if err != nil {
		t.Fatal(err)
	}
	defer s.Close()

	// Run a scan to test the file detection
	ctx := context.Background()
	if err := s.Scan(ctx); err != nil {
		t.Fatal(err)
	}

	// Verify that only certificate files were processed
	metricsMap := metricsCollector.GetMetrics()

	// Count expected certificate files
	expectedCertFiles := 0
	for _, tf := range testFiles {
		if tf.isCert {
			expectedCertFiles++
		}
	}

	t.Logf("Expected %d certificate files, got %v", expectedCertFiles, metricsMap["cert_files_total"])

	if metricsMap["cert_files_total"] != float64(expectedCertFiles) {
		t.Errorf("Expected %d certificate files, got %v", expectedCertFiles, metricsMap["cert_files_total"])

		// Debug: show which files are being detected
		t.Log("Certificate files that should be detected:")
		for _, tf := range testFiles {
			if tf.isCert {
				t.Logf("  %s", tf.name)
			}
		}

		// Let's also check what the scanner's isCertificateFile function looks for
		t.Log("Scanner certificate patterns include:")
		t.Log("  Extensions: .pem, .crt, .cer, .cert, .der, .p7b, .p7c, .pfx, .p12")
		t.Log("  Name patterns: cert, certificate, chain, bundle, ca-cert, cacert")
	}
}

func TestPrivateKeyExclusion(t *testing.T) {
	tmpDir := t.TempDir()
	certDir := filepath.Join(tmpDir, "certs")
	// Fixed gosec G301 - use secure directory permissions
	if err := os.MkdirAll(certDir, TestDirPermissions); err != nil {
		t.Fatal(err)
	}

	// Create a valid certificate
	validCert := generateTestCertificate(t, 2048, time.Now().Add(365*24*time.Hour))
	writeCertToFile(t, filepath.Join(certDir, "valid.pem"), validCert)

	// Create various private key files that should be excluded
	privateKeyFiles := []string{
		"server.key",
		"private.key",
		"cert_key.pem",
		"server-key.pem",
		"private.pem",
		"server.pem.key",
		"internal_private.pem",
	}

	for _, keyFile := range privateKeyFiles {
		writeCertToFile(t, filepath.Join(certDir, keyFile), []byte("dummy private key content"))
	}

	cfg := &config.Config{
		CertificateDirectories: []string{certDir},
		Workers:                1,
		LogLevel:               "debug",
		CacheDir:               filepath.Join(tmpDir, "cache"),
		CacheTTL:               30 * time.Minute,
		CacheMaxSize:           10485760,
		ScanInterval:           1 * time.Minute,
	}

	registry := prometheus.NewRegistry()
	metricsCollector := metrics.NewCollectorWithRegistry(registry)
	log := logger.NewNop()

	s, err := scanner.New(cfg, metricsCollector, log)
	if err != nil {
		t.Fatal("Failed to create scanner:", err)
	}
	defer s.Close()

	ctx := context.Background()
	if err := s.Scan(ctx); err != nil {
		t.Fatal("Failed to run scan:", err)
	}

	// Should only process the one valid certificate, not any private keys
	metricsMap := metricsCollector.GetMetrics()

	if metricsMap["cert_files_total"] != 1 {
		t.Errorf("Expected 1 certificate file (private keys excluded), got %v", metricsMap["cert_files_total"])
	}

	if metricsMap["certs_parsed_total"] != 1 {
		t.Errorf("Expected 1 parsed certificate, got %v", metricsMap["certs_parsed_total"])
	}

	// Should have no parse errors since private keys are excluded before parsing
	if metricsMap["cert_parse_errors_total"] != 0 {
		t.Errorf("Expected 0 parse errors, got %v", metricsMap["cert_parse_errors_total"])
	}
}

func TestWeakKeyDetection(t *testing.T) {
	tests := []struct {
		name    string
		keySize int
		isWeak  bool
	}{
		{"strong_2048", 2048, false},
		{"strong_4096", 4096, false},
		{"weak_1024", 1024, true},
		{"weak_512", 512, true},
	}

	for _, tt := range tests {
		t.Run(tt.name, func(t *testing.T) {
			tmpDir := t.TempDir()
			certPath := filepath.Join(tmpDir, "cert.pem")

			cert := generateTestCertificate(t, tt.keySize, time.Now().Add(365*24*time.Hour))
			writeCertToFile(t, certPath, cert)

			cfg := &config.Config{
				CertificateDirectories: []string{tmpDir},
				Workers:                1,
				CacheDir:               filepath.Join(tmpDir, "cache"),
				CacheTTL:               30 * time.Minute,
				CacheMaxSize:           10485760,
				ScanInterval:           1 * time.Minute,
			}

			registry := prometheus.NewRegistry()
			metricsCollector := metrics.NewCollectorWithRegistry(registry)
			log := logger.NewNop()

			s, err := scanner.New(cfg, metricsCollector, log)
			if err != nil {
				t.Fatal(err)
			}
			defer s.Close()

			ctx := context.Background()
			if err := s.Scan(ctx); err != nil {
				t.Fatal(err)
			}

			metricsMap := metricsCollector.GetMetrics()
			weakKeys := metricsMap["weak_key_total"]

			if tt.isWeak && weakKeys != 1 {
				t.Errorf("Expected weak key to be detected, but wasn't")
			}
			if !tt.isWeak && weakKeys != 0 {
				t.Errorf("Expected no weak key detection, but was detected")
			}
		})
	}
}

// TestIssuerClassification tests certificate issuer classification
// Refactored to reduce cyclomatic complexity (gocyclo fix)
func TestIssuerClassification(t *testing.T) {
	tests := []struct {
		name         string
		issuer       string
		expectedCode int
	}{
		{"digicert", "CN=DigiCert TLS RSA SHA256 2020 CA1,O=DigiCert Inc,C=US", 30},
		{"verisign", "CN=VeriSign Class 3 Public Primary Certification Authority - G5,OU=(c) 2006 VeriSign", 30},
		{"amazon", "CN=Amazon RSA 2048 M01,O=Amazon,C=US", 31},
		{"aws_acm", "CN=ACM Private CA,O=AWS,C=US", 31},
		{"lets_encrypt", "CN=Let's Encrypt Authority X3,O=Let's Encrypt,C=US", 32},
		{"comodo", "CN=COMODO RSA Domain Validation Secure Server CA,O=COMODO CA Limited", 32},
		{"self_signed", "CN=self-signed.example.com,O=Self-Signed Org,C=US", 33},
		{"localhost", "CN=localhost", 33},
		{"internal", "CN=Internal CA,O=Internal,C=US", 33},
		{"unknown", "CN=Unknown CA,O=Unknown Org,C=US", 32},
	}

	for _, tt := range tests {
		t.Run(tt.name, func(t *testing.T) {
			testSingleIssuerClassification(t, tt.issuer, tt.expectedCode)
		})
	}
}

// testSingleIssuerClassification tests a single issuer classification
// Extracted to reduce cyclomatic complexity
func testSingleIssuerClassification(t *testing.T, issuer string, expectedCode int) {
	tmpDir := t.TempDir()
	certDir := filepath.Join(tmpDir, "certs")
	// Fixed gosec G301 - use secure directory permissions
	if err := os.MkdirAll(certDir, TestDirPermissions); err != nil {
		t.Fatal("Failed to create cert directory:", err)
	}

	// Create a certificate with custom issuer
	cert := createCertificateWithIssuer(t, issuer)
	certPath := filepath.Join(certDir, "test.pem")
	writeCertToFile(t, certPath, cert)

	cfg := &config.Config{
		CertificateDirectories: []string{certDir},
		Workers:                1,
		LogLevel:               "debug",
		CacheDir:               filepath.Join(tmpDir, "cache"),
		CacheTTL:               30 * time.Minute,
		CacheMaxSize:           10485760,
		ScanInterval:           1 * time.Minute,
	}

	registry := prometheus.NewRegistry()
	metricsCollector := metrics.NewCollectorWithRegistry(registry)
	log := logger.NewNop()

	s, err := scanner.New(cfg, metricsCollector, log)
	if err != nil {
		t.Fatal("Failed to create scanner:", err)
	}
	defer s.Close()

	ctx := context.Background()
	scanErr := s.Scan(ctx) // Avoid shadowing err (govet fix)
	if scanErr != nil {
		t.Fatal("Failed to run scan:", scanErr)
	}

	// Give time for async operations
	time.Sleep(100 * time.Millisecond)

	// Check issuer code metric
	families, err := registry.Gather()
	if err != nil {
		t.Fatal("Failed to gather metrics:", err)
	}

	if !verifyIssuerCode(t, families, expectedCode) {
		t.Errorf("Expected issuer code %d for issuer '%s', but was not found", expectedCode, issuer)
		debugIssuerCodes(t, families)
	}
}

// verifyIssuerCode checks if the expected issuer code is present
// Fixed revive unused parameter issue by removing unused parameter
func verifyIssuerCode(t *testing.T, families []*dto.MetricFamily, expectedCode int) bool {
	for _, family := range families {
		if family.GetName() == MetricSSLCertIssuerCode {
			for _, metric := range family.GetMetric() {
				if metric.Gauge != nil && metric.Gauge.Value != nil {
					actualCode := int(*metric.Gauge.Value)
					if actualCode == expectedCode {
						// Also check that we have the new labels
						verifyIssuerLabels(t, metric)
						return true
					}
				}
			}
		}
	}
	return false
}

// verifyIssuerLabels checks that the metric has the required labels
func verifyIssuerLabels(t *testing.T, metric *dto.Metric) {
	hasCommonName := false
	hasFileName := false

	for _, label := range metric.GetLabel() {
		switch label.GetName() {
		case "common_name":
			if label.GetValue() != "" {
				hasCommonName = true
				t.Logf("Found common_name: %s", label.GetValue())
			}
		case "file_name":
			if label.GetValue() != "" {
				hasFileName = true
				t.Logf("Found file_name: %s", label.GetValue())
			}
		}
	}

	if !hasCommonName {
		t.Error("Expected common_name label to be present")
	}
	if !hasFileName {
		t.Error("Expected file_name label to be present")
	}
}

// debugIssuerCodes logs found issuer codes for debugging
func debugIssuerCodes(t *testing.T, families []*dto.MetricFamily) {
	t.Logf("Found issuer codes:")
	for _, family := range families {
		if family.GetName() == MetricSSLCertIssuerCode {
			for _, metric := range family.GetMetric() {
				if metric.Gauge != nil && metric.Gauge.Value != nil {
					t.Logf("  Code: %d", int(*metric.Gauge.Value))
				}
			}
		}
	}
}
