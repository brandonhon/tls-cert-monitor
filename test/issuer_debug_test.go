// test/issuer_debug_test.go

package test

import (
	"context"
	"fmt"
	"os"
	"path/filepath"
	"strings"
	"testing"
	"time"

	"github.com/brandonhon/tls-cert-monitor/internal/config"
	"github.com/brandonhon/tls-cert-monitor/internal/logger"
	"github.com/brandonhon/tls-cert-monitor/internal/metrics"
	"github.com/brandonhon/tls-cert-monitor/internal/scanner"
	"github.com/prometheus/client_golang/prometheus"
)

func TestIssuerClassificationDebug(t *testing.T) {
	// Test what the actual issuer strings look like
	testCases := []struct {
		name         string
		issuer       string
		expectedCode int
	}{
		{"digicert", "CN=DigiCert TLS RSA SHA256 2020 CA1,O=DigiCert Inc,C=US", 30},
		{"amazon", "CN=Amazon RSA 2048 M01,O=Amazon,C=US", 31},
		{"self_signed", "CN=self-signed.example.com,O=Self-Signed Org,C=US", 33},
	}

	for _, tc := range testCases {
		t.Run(tc.name, func(t *testing.T) {
			tmpDir := t.TempDir()
			certDir := filepath.Join(tmpDir, "certs")
			os.MkdirAll(certDir, 0755)

			// Create certificate with specific issuer
			cert := createCertificateWithIssuer(t, tc.issuer)
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

			time.Sleep(100 * time.Millisecond)

			// Get the actual issuer string from metrics
			families, err := registry.Gather()
			if err != nil {
				t.Fatal("Failed to gather metrics:", err)
			}

			var actualIssuer string
			var actualCode int
			
			for _, family := range families {
				if family.GetName() == "ssl_cert_issuer_code" {
					for _, metric := range family.GetMetric() {
						if metric.Gauge != nil && metric.Gauge.Value != nil {
							actualCode = int(*metric.Gauge.Value)
							// Get issuer from labels
							for _, label := range metric.GetLabel() {
								if label.GetName() == "issuer" {
									actualIssuer = label.GetValue()
									break
								}
							}
							break
						}
					}
				}
			}

			fmt.Printf("=== %s ===\n", tc.name)
			fmt.Printf("Expected issuer: %s\n", tc.issuer)
			fmt.Printf("Actual issuer:   %s\n", actualIssuer)
			fmt.Printf("Expected code:   %d\n", tc.expectedCode)
			fmt.Printf("Actual code:     %d\n", actualCode)
			fmt.Printf("Issuer lowercase: %s\n", strings.ToLower(actualIssuer))
			
			// Test the classification logic manually
			lowerIssuer := strings.ToLower(actualIssuer)
			
			fmt.Printf("Contains 'digicert': %t\n", strings.Contains(lowerIssuer, "digicert"))
			fmt.Printf("Contains 'amazon': %t\n", strings.Contains(lowerIssuer, "amazon"))
			fmt.Printf("Contains 'self-signed': %t\n", strings.Contains(lowerIssuer, "self-signed"))
			fmt.Printf("Contains 'self signed': %t\n", strings.Contains(lowerIssuer, "self signed"))
			fmt.Printf("Contains 'localhost': %t\n", strings.Contains(lowerIssuer, "localhost"))
			fmt.Printf("Contains 'example.com': %t\n", strings.Contains(lowerIssuer, "example.com"))
			fmt.Printf("Contains 'test': %t\n", strings.Contains(lowerIssuer, "test"))
			fmt.Println()

			if actualCode != tc.expectedCode {
				t.Errorf("Expected code %d but got %d for issuer: %s", tc.expectedCode, actualCode, actualIssuer)
			}
		})
	}
}

func TestManualClassification(t *testing.T) {
	// Test the classification logic directly on known strings
	testCases := []struct {
		issuer       string
		expectedCode int
		description  string
	}{
		{"CN=DigiCert TLS RSA SHA256 2020 CA1,O=DigiCert Inc,C=US", 30, "DigiCert"},
		{"CN=Amazon RSA 2048 M01,O=Amazon,C=US", 31, "Amazon"},
		{"CN=self-signed.example.com,O=Self-Signed Org,C=US", 33, "Self-signed"},
		{"CN=localhost", 33, "Localhost"},
		{"CN=Let's Encrypt Authority X3,O=Let's Encrypt,C=US", 32, "Let's Encrypt"},
	}

	for _, tc := range testCases {
		t.Run(tc.description, func(t *testing.T) {
			// Manually implement the classification logic to test it
			actualCode := classifyIssuerManual(tc.issuer)
			
			fmt.Printf("Issuer: %s\n", tc.issuer)
			fmt.Printf("Expected: %d, Actual: %d\n", tc.expectedCode, actualCode)
			
			if actualCode != tc.expectedCode {
				t.Errorf("Manual classification failed: expected %d, got %d for %s", tc.expectedCode, actualCode, tc.issuer)
			}
		})
	}
}

// Manual implementation of classifyIssuer for testing
func classifyIssuerManual(issuer string) int {
	lowerIssuer := strings.ToLower(issuer)

	// Self-signed certificates - check this first
	if strings.Contains(lowerIssuer, "self-signed") || 
	   strings.Contains(lowerIssuer, "self signed") ||
	   (strings.Contains(lowerIssuer, "cn=") && 
	    (strings.Contains(lowerIssuer, "localhost") || 
	     strings.Contains(lowerIssuer, "example.com") ||
	     strings.Contains(lowerIssuer, "test"))) {
		return 33 // Self-signed
	}

	// DigiCert family
	if strings.Contains(lowerIssuer, "digicert") ||
	   strings.Contains(lowerIssuer, "rapidssl") ||
	   strings.Contains(lowerIssuer, "geotrust") ||
	   strings.Contains(lowerIssuer, "thawte") ||
	   strings.Contains(lowerIssuer, "verisign") ||
	   strings.Contains(lowerIssuer, "symantec") {
		return 30 // DigiCert
	}

	// Amazon certificates
	if strings.Contains(lowerIssuer, "amazon") ||
	   strings.Contains(lowerIssuer, "aws") ||
	   strings.Contains(lowerIssuer, "acm") {
		return 31 // Amazon
	}

	// Let's Encrypt
	if strings.Contains(lowerIssuer, "let's encrypt") || 
	   strings.Contains(lowerIssuer, "letsencrypt") ||
	   strings.Contains(lowerIssuer, "isrg") {
		return 32 // Other (Let's Encrypt goes in Other category)
	}

	// Other commercial CAs
	if strings.Contains(lowerIssuer, "comodo") ||
	   strings.Contains(lowerIssuer, "sectigo") ||
	   strings.Contains(lowerIssuer, "godaddy") ||
	   strings.Contains(lowerIssuer, "globalsign") ||
	   strings.Contains(lowerIssuer, "entrust") ||
	   strings.Contains(lowerIssuer, "trustwave") ||
	   strings.Contains(lowerIssuer, "ssl.com") ||
	   strings.Contains(lowerIssuer, "certigna") ||
	   strings.Contains(lowerIssuer, "buypass") ||
	   strings.Contains(lowerIssuer, "zerossl") {
		return 32 // Other
	}

	// Internal/Enterprise CAs
	if strings.Contains(lowerIssuer, "internal") ||
	   strings.Contains(lowerIssuer, "enterprise") ||
	   strings.Contains(lowerIssuer, "corporate") ||
	   strings.Contains(lowerIssuer, "private") {
		return 33 // Self-signed (internal CAs treated as self-signed)
	}

	// Default for unknown issuers
	return 32 // Other
}