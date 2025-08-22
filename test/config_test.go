package test

import (
	"fmt"
	"math/rand"
	"os"
	"path/filepath"
	"testing"
	"time"

	"github.com/brandonhon/tls-cert-monitor/internal/config"
	"gopkg.in/yaml.v3"
)

func TestConfigLoad(t *testing.T) {
	// Create temporary config file
	tmpDir := t.TempDir()
	configFile := filepath.Join(tmpDir, "config.yaml")

	// Create test certificate directory
	certDir := filepath.Join(tmpDir, "certs")
	if err := os.MkdirAll(certDir, 0755); err != nil {
		t.Fatal(err)
	}

	cfg := &config.Config{
		Port:                   generateTestPort(),
		BindAddress:           "127.0.0.1",
		CertificateDirectories: []string{certDir},
		ScanInterval:          1 * time.Minute,
		Workers:               2,
		LogLevel:              "debug",
		DryRun:                false,
		HotReload:             true,
		CacheDir:              filepath.Join(tmpDir, "cache"),
		CacheTTL:              30 * time.Minute,
		CacheMaxSize:          10485760,
	}

	// Write config to file
	data, err := yaml.Marshal(cfg)
	if err != nil {
		t.Fatal(err)
	}

	if err := os.WriteFile(configFile, data, 0644); err != nil {
		t.Fatal(err)
	}

	// Load config
	loaded, err := config.Load(configFile)
	if err != nil {
		t.Fatal(err)
	}

	// Verify loaded config
	if loaded.Port != cfg.Port {
		t.Errorf("Port mismatch: got %d, want %d", loaded.Port, cfg.Port)
	}

	if loaded.BindAddress != cfg.BindAddress {
		t.Errorf("BindAddress mismatch: got %s, want %s", loaded.BindAddress, cfg.BindAddress)
	}

	if len(loaded.CertificateDirectories) != len(cfg.CertificateDirectories) {
		t.Errorf("CertificateDirectories length mismatch: got %d, want %d", 
			len(loaded.CertificateDirectories), len(cfg.CertificateDirectories))
	}
}

func TestConfigValidation(t *testing.T) {
	tests := []struct {
		name    string
		config  *config.Config
		wantErr bool
		errMsg  string
	}{
		{
			name: "valid config",
			config: &config.Config{
				Port:                   3200,
				BindAddress:           "0.0.0.0",
				CertificateDirectories: []string{t.TempDir()},
				ScanInterval:          1 * time.Minute,
				Workers:               4,
				LogLevel:              "info",
			},
			wantErr: false,
		},
		{
			name: "invalid port",
			config: &config.Config{
				Port:                   -1,
				CertificateDirectories: []string{t.TempDir()},
				ScanInterval:          1 * time.Minute,
				Workers:               4,
				LogLevel:              "info",
			},
			wantErr: true,
			errMsg:  "invalid port",
		},
		{
			name: "no certificate directories",
			config: &config.Config{
				Port:                   3200,
				CertificateDirectories: []string{},
				ScanInterval:          1 * time.Minute,
				Workers:               4,
				LogLevel:              "info",
			},
			wantErr: true,
			errMsg:  "at least one certificate directory",
		},
		{
			name: "invalid workers",
			config: &config.Config{
				Port:                   3200,
				CertificateDirectories: []string{t.TempDir()},
				ScanInterval:          1 * time.Minute,
				Workers:               0,
				LogLevel:              "info",
			},
			wantErr: true,
			errMsg:  "workers must be at least 1",
		},
		{
			name: "invalid scan interval",
			config: &config.Config{
				Port:                   3200,
				CertificateDirectories: []string{t.TempDir()},
				ScanInterval:          5 * time.Second,
				Workers:               4,
				LogLevel:              "info",
			},
			wantErr: true,
			errMsg:  "scan interval must be at least 10 seconds",
		},
		{
			name: "invalid log level",
			config: &config.Config{
				Port:                   3200,
				CertificateDirectories: []string{t.TempDir()},
				ScanInterval:          1 * time.Minute,
				Workers:               4,
				LogLevel:              "invalid",
			},
			wantErr: true,
			errMsg:  "invalid log level",
		},
	}

	for _, tt := range tests {
		t.Run(tt.name, func(t *testing.T) {
			err := tt.config.Validate()
			if (err != nil) != tt.wantErr {
				t.Errorf("Validate() error = %v, wantErr %v", err, tt.wantErr)
			}
			if err != nil && tt.errMsg != "" {
				if !contains(err.Error(), tt.errMsg) {
					t.Errorf("Validate() error message = %v, want to contain %v", err.Error(), tt.errMsg)
				}
			}
		})
	}
}

func TestConfigDefaults(t *testing.T) {
	defaults := config.Defaults()

	if defaults.Port != 3200 {
		t.Errorf("Default port = %d, want 3200", defaults.Port)
	}

	if defaults.Workers != 4 {
		t.Errorf("Default workers = %d, want 4", defaults.Workers)
	}

	if defaults.LogLevel != "info" {
		t.Errorf("Default log level = %s, want info", defaults.LogLevel)
	}

	if !defaults.HotReload {
		t.Error("Default hot reload should be true")
	}
}

func TestConfigPathTraversal(t *testing.T) {
	tmpDir := t.TempDir()
	allowedDir := filepath.Join(tmpDir, "allowed")
	os.MkdirAll(allowedDir, 0755)

	cfg := &config.Config{
		CertificateDirectories: []string{allowedDir},
	}

	tests := []struct {
		name    string
		path    string
		allowed bool
	}{
		{
			name:    "allowed path",
			path:    filepath.Join(allowedDir, "cert.pem"),
			allowed: true,
		},
		{
			name:    "allowed subdirectory",
			path:    filepath.Join(allowedDir, "subdir", "cert.pem"),
			allowed: true,
		},
		{
			name:    "path traversal attempt",
			path:    filepath.Join(allowedDir, "..", "outside.pem"),
			allowed: false,
		},
		{
			name:    "absolute path outside",
			path:    "/etc/passwd",
			allowed: false,
		},
	}

	for _, tt := range tests {
		t.Run(tt.name, func(t *testing.T) {
			result := cfg.IsPathAllowed(tt.path)
			if result != tt.allowed {
				t.Errorf("IsPathAllowed(%s) = %v, want %v", tt.path, result, tt.allowed)
			}
		})
	}
}

// Helper functions

func generateTestPort() int {
	rand.Seed(time.Now().UnixNano())
	return 18000 + rand.Intn(400)
}

func contains(s, substr string) bool {
	return len(s) >= len(substr) && (s == substr || contains(s[1:], substr))
}