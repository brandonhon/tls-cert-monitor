// test/issuer_classification_test.go

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

func TestNewIssuerClassificationCodes(t *testing.T) {
	// Test the new issuer classification system
	// DigiCert=30, Amazon=31, Other=32, Self-signed=33
	
	tests := []struct {
		name         string
		issuer       string
		expectedCode int
		description  string
	}{
		// DigiCert family (code 30)
		{"digicert_main", "CN=DigiCert Global Root CA,OU=www.digicert.com,O=DigiCert Inc,C=US", 30, "DigiCert"},
		{"digicert_sha2", "CN=DigiCert SHA2 Extended Validation Server CA,O=DigiCert Inc,C=US", 30, "DigiCert"},
		{"rapidssl", "CN=RapidSSL RSA CA 2018,O=DigiCert Inc,C=US", 30, "DigiCert (RapidSSL)"},
		{"geotrust", "CN=GeoTrust RSA CA 2018,O=DigiCert Inc,C=US", 30, "DigiCert (GeoTrust)"},
		{"thawte", "CN=thawte RSA CA 2018,O=thawte, Inc.,C=US", 30, "DigiCert (Thawte)"},
		{"verisign", "CN=VeriSign Class 3 Public Primary Certification Authority - G5", 30, "DigiCert (VeriSign)"},
		{"symantec", "CN=Symantec Class 3 Secure Server CA - G4,O=Symantec Corporation,C=US", 30, "DigiCert (Symantec)"},

		// Amazon family (code 31)
		{"amazon_rsa", "CN=Amazon RSA 2048 M01,O=Amazon,C=US", 31, "Amazon"},
		{"aws_acm", "CN=ACM Private CA,O=AWS,C=US", 31, "Amazon (ACM)"},
		{"amazon_root", "CN=Amazon Root CA 1,O=Amazon,C=US", 31, "Amazon"},

		// Other CAs (code 32)
		{"lets_encrypt", "CN=Let's Encrypt Authority X3,O=Let's Encrypt,C=US", 32, "Other (Let's Encrypt)"},
		{"letsencrypt_r3", "CN=R3,O=Let's Encrypt,C=US", 32, "Other (Let's Encrypt R3)"},
		{"isrg_root", "CN=ISRG Root X1,O=Internet Security Research Group,C=US", 32, "Other (ISRG)"},
		{"comodo", "CN=COMODO RSA Domain Validation Secure Server CA,O=COMODO CA Limited,L=Salford,ST=Greater Manchester,C=GB", 32, "Other (Comodo)"},
		{"sectigo", "CN=Sectigo RSA Domain Validation Secure Server CA,O=Sectigo Limited,L=Salford,ST=Greater Manchester,C=GB", 32, "Other (Sectigo)"},
		{"godaddy", "CN=Go Daddy Secure Certificate Authority - G2,OU=http://certs.godaddy.com/repository/,O=GoDaddy.com\\, Inc.,L=Scottsdale,ST=Arizona,C=US", 32, "Other (GoDaddy)"},
		{"globalsign", "CN=GlobalSign RSA OV SSL CA 2018,O=GlobalSign nv-sa,C=BE", 32, "Other (GlobalSign)"},
		{"entrust", "CN=Entrust Certification Authority - L1K,OU=(c) 2012 Entrust\\, Inc.,O=Entrust\\, Inc.,C=US", 32, "Other (Entrust)"},
		{"zerossl", "CN=ZeroSSL RSA Domain Secure Site CA,O=ZeroSSL,C=AT", 32, "Other (ZeroSSL)"},

		// Self-signed and internal (code 33)
		{"self_signed_explicit", "CN=self-signed.example.com,O=Self-Signed Org,C=US", 33, "Self-signed (explicit)"},
		{"localhost", "CN=localhost", 33, "Self-signed (localhost)"},
		{"test_cert", "CN=test.example.com,O=Test Org,C=US", 33, "Self-signed (test domain)"},
		{"internal_ca", "CN=Internal CA,O=Internal,C=US", 33, "Self-signed (internal)"},
		{"enterprise_ca", "CN=Enterprise Root CA,O=Enterprise Corp,C=US", 33, "Self-signed (enterprise)"},
		{"corporate_ca", "CN=Corporate CA,O=Corporate IT,C=US", 33, "Self-signed (corporate)"},
		{"private_ca", "CN=Private CA,O=Private Org,C=US", 33, "Self-signed (private)"},

		// Unknown/Other (should default to code 32)
		{"unknown_ca", "CN=Unknown Certificate Authority,O=Unknown Org,C=XX", 32, "Other (unknown)"},
		{"custom_ca", "CN=Custom CA,O=Custom Organization,C=US", 32, "Other (custom)"},
	}

	for _, tt := range tests {
		t.Run(tt.name, func(t *testing.T) {
			tmpDir := t.TempDir()
			certDir := filepath.Join(tmpDir, "certs")
			os.MkdirAll(certDir, 0755)

			// Create a certificate with the specific issuer
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
			var actualCode int
			
			for _, family := range families {
				if family.GetName() == "ssl_cert_issuer_code" {
					for _, metric := range family.GetMetric() {
						if metric.Gauge != nil && metric.Gauge.Value != nil {
							actualCode = int(*metric.Gauge.Value)
							if actualCode == tt.expectedCode {
								foundExpectedCode = true
								break
							}
						}
					}
				}
			}

			if !foundExpectedCode {
				t.Errorf("%s: Expected issuer code %d for '%s', but got %d", 
					tt.description, tt.expectedCode, tt.issuer, actualCode)
			} else {
				t.Logf("✓ %s: Correctly classified as code %d", tt.description, tt.expectedCode)
			}
		})
	}
}

func TestIssuerClassificationSummary(t *testing.T) {
	// Test that verifies we can distinguish between all four categories
	tmpDir := t.TempDir()
	certDir := filepath.Join(tmpDir, "certs")
	os.MkdirAll(certDir, 0755)

	// Create one certificate from each category
	testCerts := []struct {
		filename string
		issuer   string
		expected int
	}{
		{"digicert.pem", "CN=DigiCert Global Root CA,O=DigiCert Inc,C=US", 30},
		{"amazon.pem", "CN=Amazon RSA 2048 M01,O=Amazon,C=US", 31},
		{"letsencrypt.pem", "CN=Let's Encrypt Authority X3,O=Let's Encrypt,C=US", 32},
		{"selfsigned.pem", "CN=localhost", 33},
	}

	for _, tc := range testCerts {
		cert := createCertificateWithIssuer(t, tc.issuer)
		certPath := filepath.Join(certDir, tc.filename)
		writeCertToFile(t, certPath, cert)
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

	time.Sleep(100 * time.Millisecond)

	// Check that we found all four different codes
	families, err := registry.Gather()
	if err != nil {
		t.Fatal("Failed to gather metrics:", err)
	}

	foundCodes := make(map[int]bool)
	for _, family := range families {
		if family.GetName() == "ssl_cert_issuer_code" {
			for _, metric := range family.GetMetric() {
				if metric.Gauge != nil && metric.Gauge.Value != nil {
					code := int(*metric.Gauge.Value)
					foundCodes[code] = true
				}
			}
		}
	}

	expectedCodes := []int{30, 31, 32, 33}
	for _, expectedCode := range expectedCodes {
		if !foundCodes[expectedCode] {
			t.Errorf("Expected to find issuer code %d, but it was not found", expectedCode)
		}
	}

	if len(foundCodes) != 4 {
		t.Errorf("Expected to find exactly 4 different issuer codes, but found %d: %v", len(foundCodes), foundCodes)
	}

	t.Logf("✓ Successfully classified certificates into all 4 categories: %v", foundCodes)
}