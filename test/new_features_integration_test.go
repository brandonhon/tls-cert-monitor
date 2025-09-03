//go:build integration
// +build integration

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

// TestNewFeaturesIntegration tests both exclude directories and hostname metrics
// working together in a complete end-to-end scenario
func TestNewFeaturesIntegration(t *testing.T) {
	tmpDir := t.TempDir()
	
	// Create directory structure
	certDir := filepath.Join(tmpDir, "certs")
	excludeDir1 := filepath.Join(certDir, "private")
	excludeDir2 := filepath.Join(certDir, "backup") 
	allowedSubdir := filepath.Join(certDir, "public")
	
	// Create all directories
	for _, dir := range []string{certDir, excludeDir1, excludeDir2, allowedSubdir} {
		if err := os.MkdirAll(dir, TestDirPermissions); err != nil {
			t.Fatalf("Failed to create directory %s: %v", dir, err)
		}
	}

	// Generate test certificates
	validCert := createValidCertificate(t)
	weakKeyCert := createWeakKeyCertificate(t)
	
	// Place certificates in various locations
	testFiles := map[string][]byte{
		// These should be included in scanning
		filepath.Join(certDir, "root.pem"):              validCert,
		filepath.Join(allowedSubdir, "public1.pem"):     validCert,
		filepath.Join(allowedSubdir, "public2.pem"):     weakKeyCert,
		
		// These should be excluded from scanning
		filepath.Join(excludeDir1, "private1.pem"):      validCert,
		filepath.Join(excludeDir1, "private2.pem"):      validCert,
		filepath.Join(excludeDir2, "backup1.pem"):       validCert,
		filepath.Join(excludeDir2, "backup2.pem"):       weakKeyCert,
	}

	// Write all test files
	for path, content := range testFiles {
		writeCertToFile(t, path, content)
	}

	// Create configuration with exclude directories
	cfg := &config.Config{
		Port:                   generateTestPort(),
		BindAddress:            "127.0.0.1",
		CertificateDirectories: []string{certDir},
		ExcludeDirectories:     []string{excludeDir1, excludeDir2}, // Exclude private and backup dirs
		ScanInterval:           1 * time.Minute,
		Workers:                2,
		LogLevel:               "debug",
		CacheDir:               filepath.Join(tmpDir, "cache"),
		CacheTTL:               30 * time.Minute,
		CacheMaxSize:           10485760,
	}

	// Create components
	registry := prometheus.NewRegistry()
	metricsCollector := metrics.NewCollectorWithRegistry(registry)
	healthChecker := health.New(cfg, metricsCollector)
	log := logger.NewNop()

	// Create and run scanner
	s, err := scanner.New(cfg, metricsCollector, log)
	if err != nil {
		t.Fatal("Failed to create scanner:", err)
	}
	defer s.Close()

	// Perform scan
	ctx := context.Background()
	if err := s.Scan(ctx); err != nil {
		t.Fatal("Failed to run scan:", err)
	}

	// Start HTTP server to test metrics endpoint
	srv := server.NewWithRegistry(cfg, metricsCollector, healthChecker, log, registry)

	go func() {
		if err := srv.Start(); err != nil && err != http.ErrServerClosed {
			t.Errorf("Server start error: %v", err)
		}
	}()

	// Wait for server to start
	time.Sleep(200 * time.Millisecond)

	// Test 1: Verify exclude directories functionality
	t.Run("ExcludeDirectoriesFunctionality", func(t *testing.T) {
		metricsMap := metricsCollector.GetMetrics()

		// Should only find 3 certificates (root.pem, public1.pem, public2.pem)
		// The 4 certificates in excluded directories should not be counted
		expectedFiles := float64(3)
		if metricsMap["cert_files_total"] != expectedFiles {
			t.Errorf("Expected %v certificate files, got %v", expectedFiles, metricsMap["cert_files_total"])
		}

		if metricsMap["certs_parsed_total"] != expectedFiles {
			t.Errorf("Expected %v parsed certificates, got %v", expectedFiles, metricsMap["certs_parsed_total"])
		}

		// Should have 1 weak key (from public2.pem, not from excluded backup2.pem)
		expectedWeakKeys := float64(1)
		if metricsMap["weak_key_total"] != expectedWeakKeys {
			t.Errorf("Expected %v weak keys, got %v", expectedWeakKeys, metricsMap["weak_key_total"])
		}
	})

	// Test 2: Verify hostname metric via HTTP endpoint
	t.Run("HostnameMetricViaHTTP", func(t *testing.T) {
		// Fetch metrics from HTTP endpoint
		resp, err := http.Get(fmt.Sprintf("http://127.0.0.1:%d/metrics", cfg.Port))
		if err != nil {
			t.Fatal("Failed to fetch metrics:", err)
		}
		defer func() {
			if err := resp.Body.Close(); err != nil {
				t.Logf("Failed to close response body: %v", err)
			}
		}()

		if resp.StatusCode != http.StatusOK {
			t.Fatalf("Expected status 200, got %d", resp.StatusCode)
		}

		body, err := io.ReadAll(resp.Body)
		if err != nil {
			t.Fatal("Failed to read response body:", err)
		}

		metricsOutput := string(body)

		// Check for hostname metric
		if !strings.Contains(metricsOutput, "ssl_cert_monitor_hostname_info") {
			t.Error("Hostname metric 'ssl_cert_monitor_hostname_info' not found in metrics output")
		}

		// Check that hostname metric has a value of 1
		if !strings.Contains(metricsOutput, "ssl_cert_monitor_hostname_info{hostname=") {
			t.Error("Hostname metric missing hostname label")
		}

		// Verify the metric has a value (should be 1)
		lines := strings.Split(metricsOutput, "\n")
		hostnameMetricFound := false
		for _, line := range lines {
			if strings.HasPrefix(line, "ssl_cert_monitor_hostname_info{hostname=") && strings.HasSuffix(strings.TrimSpace(line), " 1") {
				hostnameMetricFound = true
				t.Logf("Found hostname metric: %s", strings.TrimSpace(line))
				break
			}
		}

		if !hostnameMetricFound {
			t.Error("Hostname metric with value 1 not found")
			// Debug: show relevant lines
			t.Log("Hostname-related lines in metrics output:")
			for _, line := range lines {
				if strings.Contains(line, "hostname") || strings.Contains(line, "ssl_cert_monitor_hostname_info") {
					t.Logf("  %s", line)
				}
			}
		}
	})

	// Test 3: Verify configuration validation with both features
	t.Run("ConfigurationValidation", func(t *testing.T) {
		// Test valid configuration
		validCfg := &config.Config{
			Port:                   3201,
			CertificateDirectories: []string{certDir},
			ExcludeDirectories:     []string{excludeDir1, excludeDir2},
			ScanInterval:           1 * time.Minute,
			Workers:                4,
			LogLevel:               "info",
		}

		if err := validCfg.Validate(); err != nil {
			t.Errorf("Valid configuration should not have errors: %v", err)
		}

		// Test configuration with invalid exclude directory
		invalidCfg := &config.Config{
			Port:                   3201,
			CertificateDirectories: []string{certDir},
			ExcludeDirectories:     []string{"/tmp/../etc/passwd"}, // Path traversal attempt
			ScanInterval:           1 * time.Minute,
			Workers:                4,
			LogLevel:               "info",
		}

		if err := invalidCfg.Validate(); err == nil {
			t.Error("Invalid configuration should have validation error")
		} else if !strings.Contains(err.Error(), "invalid exclude directory path") {
			t.Errorf("Expected 'invalid exclude directory path' error, got: %v", err)
		}
	})

	// Test 4: Verify IsPathAllowed respects both inclusion and exclusion
	t.Run("PathAllowedLogic", func(t *testing.T) {
		tests := []struct {
			path     string
			allowed  bool
			reason   string
		}{
			{
				path:    filepath.Join(certDir, "test.pem"),
				allowed: true,
				reason:  "file in certificate directory, not excluded",
			},
			{
				path:    filepath.Join(allowedSubdir, "test.pem"),
				allowed: true,
				reason:  "file in allowed subdirectory",
			},
			{
				path:    filepath.Join(excludeDir1, "test.pem"),
				allowed: false,
				reason:  "file in excluded directory",
			},
			{
				path:    filepath.Join(excludeDir2, "subdir", "test.pem"),
				allowed: false,
				reason:  "file in excluded directory subdirectory",
			},
			{
				path:    "/outside/test.pem",
				allowed: false,
				reason:  "file outside certificate directories",
			},
		}

		for _, tt := range tests {
			result := cfg.IsPathAllowed(tt.path)
			if result != tt.allowed {
				t.Errorf("IsPathAllowed(%s) = %v, want %v (%s)", tt.path, result, tt.allowed, tt.reason)
			}
		}
	})

	// Shutdown server
	shutdownCtx, cancel := context.WithTimeout(context.Background(), 5*time.Second)
	defer cancel()
	if err := srv.Shutdown(shutdownCtx); err != nil {
		t.Errorf("Server shutdown error: %v", err)
	}
}

// TestEnvironmentVariableSupport tests that exclude directories can be set via environment variables
func TestEnvironmentVariableSupport(t *testing.T) {
	tmpDir := t.TempDir()
	certDir := filepath.Join(tmpDir, "certs")
	excludeDir := filepath.Join(certDir, "private")
	
	// Create directories
	if err := os.MkdirAll(certDir, TestDirPermissions); err != nil {
		t.Fatal(err)
	}
	if err := os.MkdirAll(excludeDir, TestDirPermissions); err != nil {
		t.Fatal(err)
	}

	// Set environment variables
	oldCertDirs := os.Getenv("TLS_MONITOR_CERTIFICATE_DIRECTORIES")
	oldExcludeDirs := os.Getenv("TLS_MONITOR_EXCLUDE_DIRECTORIES")
	
	defer func() {
		// Restore original environment
		if oldCertDirs != "" {
			os.Setenv("TLS_MONITOR_CERTIFICATE_DIRECTORIES", oldCertDirs)
		} else {
			os.Unsetenv("TLS_MONITOR_CERTIFICATE_DIRECTORIES")
		}
		if oldExcludeDirs != "" {
			os.Setenv("TLS_MONITOR_EXCLUDE_DIRECTORIES", oldExcludeDirs)
		} else {
			os.Unsetenv("TLS_MONITOR_EXCLUDE_DIRECTORIES")
		}
	}()

	// Set test environment variables
	if err := os.Setenv("TLS_MONITOR_CERTIFICATE_DIRECTORIES", certDir); err != nil {
		t.Fatal(err)
	}
	if err := os.Setenv("TLS_MONITOR_EXCLUDE_DIRECTORIES", excludeDir); err != nil {
		t.Fatal(err)
	}

	// Load configuration (empty config file to test env vars)
	cfg, err := config.Load("")
	if err != nil {
		t.Fatal("Failed to load config:", err)
	}

	// Verify environment variables were applied
	if len(cfg.CertificateDirectories) != 1 || cfg.CertificateDirectories[0] != certDir {
		t.Errorf("Expected certificate_directories [%s], got %v", certDir, cfg.CertificateDirectories)
	}

	if len(cfg.ExcludeDirectories) != 1 || cfg.ExcludeDirectories[0] != excludeDir {
		t.Errorf("Expected exclude_directories [%s], got %v", excludeDir, cfg.ExcludeDirectories)
	}

	// Test that exclusion logic works
	testPath := filepath.Join(excludeDir, "test.pem")
	if !cfg.IsPathExcluded(testPath) {
		t.Errorf("Expected path %s to be excluded", testPath)
	}
}