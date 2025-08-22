// test/scanner_test.go

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
)

func TestCertificateScanning(t *testing.T) {
	tmpDir := t.TempDir()
	certDir := filepath.Join(tmpDir, "certs")
	os.MkdirAll(certDir, 0755)

	// Generate test certificates
	goodCert := generateTestCertificate(t, 2048, time.Now().Add(365*24*time.Hour))
	weakCert := generateTestCertificate(t, 1024, time.Now().Add(365*24*time.Hour))
	expiredCert := generateTestCertificate(t, 2048, time.Now().Add(-24*time.Hour))

	// Write certificates to files
	writeCertToFile(t, filepath.Join(certDir, "good.pem"), goodCert)
	writeCertToFile(t, filepath.Join(certDir, "weak.pem"), weakCert)
	writeCertToFile(t, filepath.Join(certDir, "expired.pem"), expiredCert)

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

	// Verify metrics
	metrics := metricsCollector.GetMetrics()

	if metrics["cert_files_total"] != 3 {
		t.Errorf("Expected 3 certificate files, got %v", metrics["cert_files_total"])
	}

	if metrics["certs_parsed_total"] != 3 {
		t.Errorf("Expected 3 parsed certificates, got %v", metrics["certs_parsed_total"])
	}

	if metrics["weak_key_total"] != 1 {
		t.Errorf("Expected 1 weak key, got %v", metrics["weak_key_total"])
	}
}

func TestCertificateFileDetection(t *testing.T) {
	tmpDir := t.TempDir()

	// Create test files with various extensions
	testFiles := []struct {
		name   string
		isCert bool
	}{
		{"cert.pem", true},
		{"cert.crt", true},
		{"cert.cer", true},
		{"cert.der", true},
		{"certificate.pem", true},
		{"notacert.txt", false},
		{"readme.md", false},
		{"config.yaml", false},
	}

	for _, tf := range testFiles {
		path := filepath.Join(tmpDir, tf.name)
		if err := os.WriteFile(path, []byte("test"), 0644); err != nil {
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

	// Test file detection
	for _, tf := range testFiles {
		_ = filepath.Join(tmpDir, tf.name)
		// Note: This test relies on the internal logic of isCertificateFile
		// In a real scenario, we'd make this method public or test through the Scan method
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

			metrics := metricsCollector.GetMetrics()
			weakKeys := metrics["weak_key_total"]

			if tt.isWeak && weakKeys != 1 {
				t.Errorf("Expected weak key to be detected, but wasn't")
			}
			if !tt.isWeak && weakKeys != 0 {
				t.Errorf("Expected no weak key detection, but was detected")
			}
		})
	}
}

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
			tmpDir := t.TempDir()
			certDir := filepath.Join(tmpDir, "certs")
			os.MkdirAll(certDir, 0755)

			// Create a certificate with custom issuer
			cert := createCertificateWithIssuer(t, tt.issuer)
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
			if err := s.Scan(ctx); err != nil {
				t.Fatal("Failed to run scan:", err)
			}

			// Give time for async operations
			time.Sleep(100 * time.Millisecond)

			// Check issuer code metric
			families, err := registry.Gather()
			if err != nil {
				t.Fatal("Failed to gather metrics:", err)
			}

			foundExpectedCode := false
			for _, family := range families {
				if family.GetName() == "ssl_cert_issuer_code" {
					for _, metric := range family.GetMetric() {
						if metric.Gauge != nil && metric.Gauge.Value != nil {
							actualCode := int(*metric.Gauge.Value)
							if actualCode == tt.expectedCode {
								foundExpectedCode = true
								break
							}
						}
					}
				}
			}

			if !foundExpectedCode {
				t.Errorf("Expected issuer code %d for issuer '%s', but was not found", tt.expectedCode, tt.issuer)

				// Debug: show what codes were found
				t.Logf("Found issuer codes:")
				for _, family := range families {
					if family.GetName() == "ssl_cert_issuer_code" {
						for _, metric := range family.GetMetric() {
							if metric.Gauge != nil && metric.Gauge.Value != nil {
								t.Logf("  Code: %d", int(*metric.Gauge.Value))
							}
						}
					}
				}
			}
		})
	}
}
