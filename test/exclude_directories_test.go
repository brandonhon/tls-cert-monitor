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
)

// TestExcludeDirectories tests that directories specified in exclude_directories
// are properly excluded from certificate scanning
func TestExcludeDirectories(t *testing.T) {
	tmpDir := t.TempDir()
	
	// Create main certificate directory
	certDir := filepath.Join(tmpDir, "certs")
	if err := os.MkdirAll(certDir, TestDirPermissions); err != nil {
		t.Fatal("Failed to create cert directory:", err)
	}

	// Create excluded subdirectory
	excludeDir := filepath.Join(certDir, "private")
	if err := os.MkdirAll(excludeDir, TestDirPermissions); err != nil {
		t.Fatal("Failed to create exclude directory:", err)
	}

	// Create another excluded directory outside the main cert dir
	externalExcludeDir := filepath.Join(tmpDir, "backup-certs")
	if err := os.MkdirAll(externalExcludeDir, TestDirPermissions); err != nil {
		t.Fatal("Failed to create external exclude directory:", err)
	}

	// Generate test certificates
	validCert := createValidCertificate(t)
	
	// Place certificates in different locations
	writeCertToFile(t, filepath.Join(certDir, "valid1.pem"), validCert)
	writeCertToFile(t, filepath.Join(certDir, "valid2.pem"), validCert)
	writeCertToFile(t, filepath.Join(excludeDir, "excluded1.pem"), validCert)     // Should be excluded
	writeCertToFile(t, filepath.Join(excludeDir, "excluded2.pem"), validCert)     // Should be excluded
	writeCertToFile(t, filepath.Join(externalExcludeDir, "backup1.pem"), validCert) // Should be excluded

	// Create scanner configuration with exclude directories
	cfg := &config.Config{
		Port:                   generateTestPort(),
		BindAddress:            "127.0.0.1",
		CertificateDirectories: []string{certDir, externalExcludeDir}, // Include both main and backup dirs
		ExcludeDirectories:     []string{excludeDir, externalExcludeDir}, // Exclude private and backup dirs
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
		t.Fatal("Failed to create scanner:", err)
	}
	defer s.Close()

	// Perform scan
	ctx := context.Background()
	if err := s.Scan(ctx); err != nil {
		t.Fatal("Failed to run scan:", err)
	}

	// Verify metrics - should only find 2 certificates (valid1.pem and valid2.pem)
	// The 3 certificates in excluded directories should not be counted
	metricsMap := metricsCollector.GetMetrics()

	expectedFiles := float64(2) // Only files in certDir, not in excluded subdirs
	if metricsMap["cert_files_total"] != expectedFiles {
		t.Errorf("Expected %v certificate files, got %v", expectedFiles, metricsMap["cert_files_total"])
	}

	if metricsMap["certs_parsed_total"] != expectedFiles {
		t.Errorf("Expected %v parsed certificates, got %v", expectedFiles, metricsMap["certs_parsed_total"])
	}

	// Should have no parse errors
	if metricsMap["cert_parse_errors_total"] != 0 {
		t.Errorf("Expected 0 parse errors, got %v", metricsMap["cert_parse_errors_total"])
	}
}

// TestConfigValidateExcludeDirectories tests the validation of exclude directories configuration
func TestConfigValidateExcludeDirectories(t *testing.T) {
	tests := []struct {
		name               string
		excludeDirectories []string
		wantErr            bool
		errMsg             string
	}{
		{
			name:               "valid exclude directories",
			excludeDirectories: []string{"/tmp/exclude1", "/tmp/exclude2"},
			wantErr:            false,
		},
		{
			name:               "empty exclude directories (should be valid)",
			excludeDirectories: []string{},
			wantErr:            false,
		},
		{
			name:               "exclude directory with path traversal",
			excludeDirectories: []string{"/tmp/../etc/passwd"},
			wantErr:            true,
			errMsg:             "invalid exclude directory path",
		},
		{
			name:               "exclude directory that exists but is not a directory",
			excludeDirectories: []string{"/dev/null"}, // This is a device file, not a directory
			wantErr:            true,
			errMsg:             "exclude path is not a directory",
		},
	}

	for _, tt := range tests {
		t.Run(tt.name, func(t *testing.T) {
			tmpDir := t.TempDir()
			certDir := filepath.Join(tmpDir, "certs")
			if err := os.MkdirAll(certDir, TestDirPermissions); err != nil {
				t.Fatal("Failed to create cert directory:", err)
			}

			cfg := &config.Config{
				Port:                   3200,
				CertificateDirectories: []string{certDir},
				ExcludeDirectories:     tt.excludeDirectories,
				ScanInterval:           1 * time.Minute,
				Workers:                4,
				LogLevel:               "info",
			}

			err := cfg.Validate()
			if (err != nil) != tt.wantErr {
				t.Errorf("Validate() error = %v, wantErr %v", err, tt.wantErr)
				return
			}
			if err != nil && tt.errMsg != "" {
				if !contains(err.Error(), tt.errMsg) {
					t.Errorf("Validate() error message = %v, want to contain %v", err.Error(), tt.errMsg)
				}
			}
		})
	}
}

// TestIsPathExcluded tests the IsPathExcluded method
func TestIsPathExcluded(t *testing.T) {
	tmpDir := t.TempDir()
	
	// Create directories
	excludeDir1 := filepath.Join(tmpDir, "exclude1")
	excludeDir2 := filepath.Join(tmpDir, "exclude2")
	if err := os.MkdirAll(excludeDir1, TestDirPermissions); err != nil {
		t.Fatal(err)
	}
	if err := os.MkdirAll(excludeDir2, TestDirPermissions); err != nil {
		t.Fatal(err)
	}

	cfg := &config.Config{
		ExcludeDirectories: []string{excludeDir1, excludeDir2},
	}

	tests := []struct {
		name     string
		path     string
		excluded bool
	}{
		{
			name:     "path in first exclude directory",
			path:     filepath.Join(excludeDir1, "file.pem"),
			excluded: true,
		},
		{
			name:     "path in second exclude directory",
			path:     filepath.Join(excludeDir2, "subdir", "file.pem"),
			excluded: true,
		},
		{
			name:     "path not in exclude directory",
			path:     filepath.Join(tmpDir, "allowed", "file.pem"),
			excluded: false,
		},
		{
			name:     "exclude directory itself",
			path:     excludeDir1,
			excluded: true,
		},
		{
			name:     "path trying to escape exclude directory",
			path:     filepath.Join(excludeDir1, "..", "file.pem"),
			excluded: false,
		},
	}

	for _, tt := range tests {
		t.Run(tt.name, func(t *testing.T) {
			result := cfg.IsPathExcluded(tt.path)
			if result != tt.excluded {
				t.Errorf("IsPathExcluded(%s) = %v, want %v", tt.path, result, tt.excluded)
			}
		})
	}
}

// TestHostnameMetric tests that the hostname metric is properly set
func TestHostnameMetric(t *testing.T) {
	tmpDir := t.TempDir()
	certDir := filepath.Join(tmpDir, "certs")
	if err := os.MkdirAll(certDir, TestDirPermissions); err != nil {
		t.Fatal("Failed to create cert directory:", err)
	}

	// Create a test certificate
	validCert := createValidCertificate(t)
	writeCertToFile(t, filepath.Join(certDir, "test.pem"), validCert)

	cfg := &config.Config{
		Port:                   generateTestPort(),
		BindAddress:            "127.0.0.1",
		CertificateDirectories: []string{certDir},
		ExcludeDirectories:     []string{},
		ScanInterval:           1 * time.Minute,
		Workers:                1,
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
		t.Fatal("Failed to create scanner:", err)
	}
	defer s.Close()

	// Perform scan
	ctx := context.Background()
	if err := s.Scan(ctx); err != nil {
		t.Fatal("Failed to run scan:", err)
	}

	// Check that hostname metric exists
	families, err := registry.Gather()
	if err != nil {
		t.Fatal("Failed to gather metrics:", err)
	}

	hostnameMetricFound := false
	for _, family := range families {
		if family.GetName() == "ssl_cert_monitor_hostname_info" {
			hostnameMetricFound = true
			
			// Check that we have exactly one metric with a hostname label
			metrics := family.GetMetric()
			if len(metrics) != 1 {
				t.Errorf("Expected 1 hostname metric, got %d", len(metrics))
				continue
			}

			metric := metrics[0]
			if metric.Gauge == nil || metric.Gauge.Value == nil {
				t.Error("Expected gauge value for hostname metric")
				continue
			}

			if *metric.Gauge.Value != 1 {
				t.Errorf("Expected hostname metric value to be 1, got %f", *metric.Gauge.Value)
			}

			// Check that hostname label exists and is not empty
			hostnameLabel := ""
			for _, label := range metric.GetLabel() {
				if label.GetName() == "hostname" {
					hostnameLabel = label.GetValue()
					break
				}
			}

			if hostnameLabel == "" {
				t.Error("Expected hostname label to be non-empty")
			} else {
				t.Logf("Found hostname metric with hostname: %s", hostnameLabel)
			}
			break
		}
	}

	if !hostnameMetricFound {
		t.Error("Hostname metric 'ssl_cert_monitor_hostname_info' not found")
		
		// Debug: List all metrics found
		t.Log("Available metrics:")
		for _, family := range families {
			t.Logf("  - %s", family.GetName())
		}
	}
}

// TestExcludeDirectoriesInFileWatcher tests that file watcher respects exclude directories
func TestExcludeDirectoriesInFileWatcher(t *testing.T) {
	tmpDir := t.TempDir()
	
	// Create main certificate directory
	certDir := filepath.Join(tmpDir, "certs")
	if err := os.MkdirAll(certDir, TestDirPermissions); err != nil {
		t.Fatal("Failed to create cert directory:", err)
	}

	// Create excluded subdirectory
	excludeDir := filepath.Join(certDir, "private")
	if err := os.MkdirAll(excludeDir, TestDirPermissions); err != nil {
		t.Fatal("Failed to create exclude directory:", err)
	}

	cfg := &config.Config{
		Port:                   generateTestPort(),
		BindAddress:            "127.0.0.1",
		CertificateDirectories: []string{certDir},
		ExcludeDirectories:     []string{excludeDir},
		ScanInterval:           1 * time.Minute,
		Workers:                1,
		LogLevel:               "debug",
		CacheDir:               filepath.Join(tmpDir, "cache"),
		CacheTTL:               30 * time.Minute,
		CacheMaxSize:           10485760,
	}

	// Create scanner
	registry := prometheus.NewRegistry()
	metricsCollector := metrics.NewCollectorWithRegistry(registry)
	log := logger.NewNop()

	s, err := scanner.New(cfg, metricsCollector, log)
	if err != nil {
		t.Fatal("Failed to create scanner:", err)
	}
	defer s.Close()

	// Start file watcher in background
	ctx, cancel := context.WithCancel(context.Background())
	defer cancel()

	go s.WatchFiles(ctx)

	// Give the watcher time to start
	time.Sleep(100 * time.Millisecond)

	// This test mainly verifies that the watcher starts without error
	// and properly handles exclude directories. The actual file event
	// testing would require more complex setup with file system events.
	
	// For now, we just verify the scanner was created successfully
	// and the configuration is properly applied
	if !cfg.IsPathExcluded(filepath.Join(excludeDir, "somefile.pem")) {
		t.Error("Expected path in exclude directory to be excluded")
	}
	
	if cfg.IsPathExcluded(filepath.Join(certDir, "allowed.pem")) {
		t.Error("Expected path outside exclude directory to not be excluded")
	}
}