// Package config provides configuration management for the TLS Certificate Monitor.
// It handles loading configuration from files and environment variables, validates
// settings, and supports hot-reloading of configuration changes.
package config

import (
	"fmt"
	"os"
	"path/filepath"
	"strings"
	"time"

	"github.com/spf13/viper"
)

// Config represents the application configuration.
// Field order is optimized to minimize memory padding (fieldalignment fix).
type Config struct {
	// 8-byte aligned fields first
	CacheMaxSize int64         `mapstructure:"cache_max_size" yaml:"cache_max_size"`
	ScanInterval time.Duration `mapstructure:"scan_interval" yaml:"scan_interval"`
	CacheTTL     time.Duration `mapstructure:"cache_ttl" yaml:"cache_ttl"`

	// Slice (24 bytes header)
	CertificateDirectories []string `mapstructure:"certificate_directories" yaml:"certificate_directories"`
	ExcludeDirectories     []string `mapstructure:"exclude_directories" yaml:"exclude_directories"`

	// String fields (16 bytes each)
	BindAddress string `mapstructure:"bind_address" yaml:"bind_address"`
	TLSCert     string `mapstructure:"tls_cert" yaml:"tls_cert"`
	TLSKey      string `mapstructure:"tls_key" yaml:"tls_key"`
	LogFile     string `mapstructure:"log_file" yaml:"log_file"`
	LogLevel    string `mapstructure:"log_level" yaml:"log_level"`
	CacheDir    string `mapstructure:"cache_dir" yaml:"cache_dir"`

	// int fields (platform dependent, but after strings for better alignment)
	Port    int `mapstructure:"port" yaml:"port"`
	Workers int `mapstructure:"workers" yaml:"workers"`

	// Boolean fields last (1 byte each)
	DryRun    bool `mapstructure:"dry_run" yaml:"dry_run"`
	HotReload bool `mapstructure:"hot_reload" yaml:"hot_reload"`
}

// Defaults returns a Config with default values
func Defaults() *Config {
	return &Config{
		Port:                   3200,
		BindAddress:            "0.0.0.0",
		CertificateDirectories: []string{"/etc/ssl/certs"},
		ExcludeDirectories:     []string{}, // Empty by default
		ScanInterval:           5 * time.Minute,
		Workers:                4,
		LogLevel:               "info",
		DryRun:                 false,
		HotReload:              true,
		CacheDir:               "./cache",
		CacheTTL:               1 * time.Hour,
		CacheMaxSize:           100 * 1024 * 1024, // 100MB
	}
}

// Load loads configuration from file or environment
func Load(configFile string) (*Config, error) {
	cfg := Defaults()

	v := viper.New()

	// Set defaults
	v.SetDefault("port", cfg.Port)
	v.SetDefault("bind_address", cfg.BindAddress)
	v.SetDefault("certificate_directories", cfg.CertificateDirectories)
	v.SetDefault("exclude_directories", cfg.ExcludeDirectories)
	v.SetDefault("scan_interval", cfg.ScanInterval)
	v.SetDefault("workers", cfg.Workers)
	v.SetDefault("log_level", cfg.LogLevel)
	v.SetDefault("dry_run", cfg.DryRun)
	v.SetDefault("hot_reload", cfg.HotReload)
	v.SetDefault("cache_dir", cfg.CacheDir)
	v.SetDefault("cache_ttl", cfg.CacheTTL)
	v.SetDefault("cache_max_size", cfg.CacheMaxSize)

	// Enable environment variables
	v.SetEnvPrefix("TLS_MONITOR")
	v.SetEnvKeyReplacer(strings.NewReplacer(".", "_"))
	v.AutomaticEnv()

	// Load from config file if provided
	if configFile != "" {
		v.SetConfigFile(configFile)
		if err := v.ReadInConfig(); err != nil {
			return nil, fmt.Errorf("failed to read config file: %w", err)
		}
	}

	// Unmarshal into struct
	if err := v.Unmarshal(cfg); err != nil {
		return nil, fmt.Errorf("failed to unmarshal config: %w", err)
	}

	// Process paths: expand environment variables and normalize
	cfg.processPaths()

	// Validate configuration
	if err := cfg.Validate(); err != nil {
		return nil, fmt.Errorf("invalid configuration: %w", err)
	}

	return cfg, nil
}

// processPaths handles both environment variable expansion and path normalization
// to avoid code duplication between expandEnvironmentVariables and normalizePaths
func (c *Config) processPaths() {
	// Process certificate directories
	for i, dir := range c.CertificateDirectories {
		c.CertificateDirectories[i] = filepath.Clean(os.ExpandEnv(dir))
	}

	// Process exclude directories
	for i, dir := range c.ExcludeDirectories {
		c.ExcludeDirectories[i] = filepath.Clean(os.ExpandEnv(dir))
	}

	// Process TLS paths
	if c.TLSCert != "" {
		c.TLSCert = filepath.Clean(os.ExpandEnv(c.TLSCert))
	}
	if c.TLSKey != "" {
		c.TLSKey = filepath.Clean(os.ExpandEnv(c.TLSKey))
	}

	// Process log file path
	if c.LogFile != "" {
		c.LogFile = filepath.Clean(os.ExpandEnv(c.LogFile))
	}

	// Process cache directory
	if c.CacheDir != "" {
		c.CacheDir = filepath.Clean(os.ExpandEnv(c.CacheDir))
	}
}

// Validate validates the configuration.
// This function is split into smaller validation functions to reduce cyclomatic complexity.
func (c *Config) Validate() error {
	// Validate network settings
	if err := c.validateNetworkSettings(); err != nil {
		return err
	}

	// Validate certificate directories
	if err := c.validateCertificateDirectories(); err != nil {
		return err
	}

	// Validate exclude directories
	if err := c.validateExcludeDirectories(); err != nil {
		return err
	}

	// Validate TLS settings
	if err := c.validateTLSSettings(); err != nil {
		return err
	}

	// Validate operational settings
	return c.validateOperationalSettings()
}

// validateNetworkSettings validates port and bind address
func (c *Config) validateNetworkSettings() error {
	if c.Port < 1 || c.Port > 65535 {
		return fmt.Errorf("invalid port: %d", c.Port)
	}
	return nil
}

// validateCertificateDirectories validates certificate directory settings
func (c *Config) validateCertificateDirectories() error {
	if len(c.CertificateDirectories) == 0 {
		return fmt.Errorf("at least one certificate directory must be specified")
	}

	for _, dir := range c.CertificateDirectories {
		// Clean the path to prevent traversal
		cleanPath := filepath.Clean(dir)
		if cleanPath != dir {
			return fmt.Errorf("invalid directory path: %s", dir)
		}

		// Check if directory exists
		info, err := os.Stat(dir)
		if err != nil {
			if os.IsNotExist(err) {
				return fmt.Errorf("certificate directory does not exist: %s", dir)
			}
			return fmt.Errorf("failed to access certificate directory %s: %w", dir, err)
		}

		if !info.IsDir() {
			return fmt.Errorf("certificate path is not a directory: %s", dir)
		}
	}

	return nil
}

// validateExcludeDirectories validates exclude directory settings
func (c *Config) validateExcludeDirectories() error {
	for _, dir := range c.ExcludeDirectories {
		// Clean the path to prevent traversal
		cleanPath := filepath.Clean(dir)
		if cleanPath != dir {
			return fmt.Errorf("invalid exclude directory path: %s", dir)
		}

		// Exclude directories don't need to exist, but if they do exist, they should be directories
		if info, err := os.Stat(dir); err == nil {
			if !info.IsDir() {
				return fmt.Errorf("exclude path is not a directory: %s", dir)
			}
		}
		// If directory doesn't exist, that's fine - we just won't exclude anything
	}

	return nil
}

// validateTLSSettings validates TLS certificate and key configuration
func (c *Config) validateTLSSettings() error {
	// Both must be provided or neither
	if (c.TLSCert != "" && c.TLSKey == "") || (c.TLSCert == "" && c.TLSKey != "") {
		return fmt.Errorf("both TLS certificate and key must be provided")
	}

	if c.TLSCert != "" {
		if _, err := os.Stat(c.TLSCert); err != nil {
			return fmt.Errorf("TLS certificate file not accessible: %w", err)
		}
	}

	if c.TLSKey != "" {
		if _, err := os.Stat(c.TLSKey); err != nil {
			return fmt.Errorf("TLS key file not accessible: %w", err)
		}
	}

	return nil
}

// validateOperationalSettings validates workers, scan interval, and log level
func (c *Config) validateOperationalSettings() error {
	// Validate workers
	if c.Workers < 1 {
		return fmt.Errorf("workers must be at least 1")
	}

	// Validate scan interval
	if c.ScanInterval < 10*time.Second {
		return fmt.Errorf("scan interval must be at least 10 seconds")
	}

	// Validate log level
	validLevels := map[string]bool{
		"debug": true,
		"info":  true,
		"warn":  true,
		"error": true,
	}

	if !validLevels[strings.ToLower(c.LogLevel)] {
		return fmt.Errorf("invalid log level: %s", c.LogLevel)
	}

	return nil
}

// IsPathAllowed checks if a path is within the configured certificate directories
// and not within any exclude directories
func (c *Config) IsPathAllowed(path string) bool {
	cleanPath := filepath.Clean(path)

	// First check if path is excluded
	if c.IsPathExcluded(cleanPath) {
		return false
	}

	// Then check if path is within allowed directories
	for _, dir := range c.CertificateDirectories {
		cleanDir := filepath.Clean(dir)

		// Check if path is within the allowed directory
		rel, err := filepath.Rel(cleanDir, cleanPath)
		if err != nil {
			continue
		}

		// Check for path traversal
		if !strings.HasPrefix(rel, "..") && !filepath.IsAbs(rel) {
			return true
		}
	}

	return false
}

// IsPathExcluded checks if a path is within any of the configured exclude directories
func (c *Config) IsPathExcluded(path string) bool {
	cleanPath := filepath.Clean(path)

	for _, excludeDir := range c.ExcludeDirectories {
		cleanExcludeDir := filepath.Clean(excludeDir)

		// Check if path is within the exclude directory
		rel, err := filepath.Rel(cleanExcludeDir, cleanPath)
		if err != nil {
			continue
		}

		// If the path is within the exclude directory (not trying to escape via ..)
		if !strings.HasPrefix(rel, "..") && !filepath.IsAbs(rel) {
			return true
		}
	}

	return false
}
