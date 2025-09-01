package test

import (
	"context"
	"encoding/json"
	"fmt"
	"io"
	"net/http"
	"testing"
	"time"

	"github.com/brandonhon/tls-cert-monitor/internal/config"
	"github.com/brandonhon/tls-cert-monitor/internal/health"
	"github.com/brandonhon/tls-cert-monitor/internal/logger"
	"github.com/brandonhon/tls-cert-monitor/internal/metrics"
	"github.com/brandonhon/tls-cert-monitor/internal/server"
	"github.com/prometheus/client_golang/prometheus"
)

func TestServerEndpoints(t *testing.T) {
	// Setup
	port := generateTestPort()
	cfg := &config.Config{
		Port:                   port,
		BindAddress:            "127.0.0.1",
		CertificateDirectories: []string{t.TempDir()},
		Workers:                2,
		LogLevel:               "debug",
		ScanInterval:           1 * time.Minute,
	}

	registry := prometheus.NewRegistry()
	metricsCollector := metrics.NewCollectorWithRegistry(registry)
	healthChecker := health.New(cfg, metricsCollector)
	log := logger.NewNop()

	srv := server.NewWithRegistry(cfg, metricsCollector, healthChecker, log, registry)

	// Start server
	go func() {
		if err := srv.Start(); err != nil && err != http.ErrServerClosed {
			t.Errorf("Server start error: %v", err)
		}
	}()

	// Wait for server to start
	time.Sleep(100 * time.Millisecond)

	// Test endpoints
	baseURL := fmt.Sprintf("http://127.0.0.1:%d", port)

	tests := []struct {
		name       string
		endpoint   string
		wantStatus int
	}{
		{"root", "/", http.StatusOK},
		{"metrics", "/metrics", http.StatusOK},
		{"health", "/healthz", http.StatusOK},
		{"not_found", "/invalid", http.StatusNotFound},
	}

	// Create context for requests (noctx fix)
	ctx := context.Background()

	for _, tt := range tests {
		t.Run(tt.name, func(t *testing.T) {
			req, err := http.NewRequestWithContext(ctx, "GET", baseURL+tt.endpoint, nil)
			if err != nil {
				t.Fatal(err)
			}

			resp, err := http.DefaultClient.Do(req)
			if err != nil {
				t.Fatal(err)
			}
			// Handle close error (errcheck fix)
			defer func() {
				if err := resp.Body.Close(); err != nil {
					t.Logf("Failed to close response body: %v", err)
				}
			}()

			if resp.StatusCode != tt.wantStatus {
				t.Errorf("Status code = %d, want %d", resp.StatusCode, tt.wantStatus)
			}
		})
	}

	// Shutdown server
	shutdownCtx, cancel := context.WithTimeout(context.Background(), 5*time.Second)
	defer cancel()
	if err := srv.Shutdown(shutdownCtx); err != nil {
		t.Errorf("Server shutdown error: %v", err)
	}
}

func TestHealthEndpoint(t *testing.T) {
	// Setup
	port := generateTestPort()
	tmpDir := t.TempDir()

	cfg := &config.Config{
		Port:                   port,
		BindAddress:            "127.0.0.1",
		CertificateDirectories: []string{tmpDir},
		Workers:                2,
		LogLevel:               "info",
		HotReload:              true,
		CacheDir:               tmpDir,
		ScanInterval:           1 * time.Minute,
	}

	registry := prometheus.NewRegistry()
	metricsCollector := metrics.NewCollectorWithRegistry(registry)
	healthChecker := health.New(cfg, metricsCollector)
	log := logger.NewNop()

	srv := server.NewWithRegistry(cfg, metricsCollector, healthChecker, log, registry)

	// Start server
	go func() {
		if err := srv.Start(); err != nil && err != http.ErrServerClosed {
			t.Errorf("Server start error: %v", err)
		}
	}()

	// Wait for server to start
	time.Sleep(100 * time.Millisecond)

	// Test health endpoint with context (noctx fix)
	ctx := context.Background()
	req, err := http.NewRequestWithContext(ctx, "GET", fmt.Sprintf("http://127.0.0.1:%d/healthz", port), nil)
	if err != nil {
		t.Fatal(err)
	}

	resp, err := http.DefaultClient.Do(req)
	if err != nil {
		t.Fatal(err)
	}
	// Handle close error (errcheck fix)
	defer func() {
		if err := resp.Body.Close(); err != nil {
			t.Logf("Failed to close response body: %v", err)
		}
	}()

	if resp.StatusCode != http.StatusOK {
		t.Errorf("Health check status = %d, want %d", resp.StatusCode, http.StatusOK)
	}

	// Parse response
	body, err := io.ReadAll(resp.Body)
	if err != nil {
		t.Fatal(err)
	}

	var healthResp health.Response
	if err := json.Unmarshal(body, &healthResp); err != nil {
		t.Fatal(err)
	}

	// Verify response structure
	if healthResp.Status == "" {
		t.Error("Health response missing status")
	}

	if len(healthResp.Checks) == 0 {
		t.Error("Health response missing checks")
	}

	// Check for expected health checks
	expectedChecks := []string{
		"cert_files_total",
		"cert_parse_errors_total",
		"certs_parsed_total",
		"cert_scan_status",
		"certificate_directories",
		"config_file",
		"hot_reload_enabled",
		"log_file_writable",
		"prometheus_registry",
		"worker_pool_size",
	}

	checkMap := make(map[string]bool)
	for _, check := range healthResp.Checks {
		checkMap[check.Name] = true
	}

	for _, expected := range expectedChecks {
		if !checkMap[expected] {
			t.Errorf("Missing expected health check: %s", expected)
		}
	}

	// Shutdown server
	shutdownCtx, cancel := context.WithTimeout(context.Background(), 5*time.Second)
	defer cancel()
	if err := srv.Shutdown(shutdownCtx); err != nil {
		t.Errorf("Server shutdown error: %v", err)
	}
}

func TestMetricsEndpoint(t *testing.T) {
	// Setup
	port := generateTestPort()
	cfg := &config.Config{
		Port:                   port,
		BindAddress:            "127.0.0.1",
		CertificateDirectories: []string{t.TempDir()},
		Workers:                2,
		LogLevel:               "info",
		ScanInterval:           1 * time.Minute,
	}

	registry := prometheus.NewRegistry()
	metricsCollector := metrics.NewCollectorWithRegistry(registry)
	healthChecker := health.New(cfg, metricsCollector)
	log := logger.NewNop()

	// Set some test metrics
	metricsCollector.SetCertFilesTotal(10)
	metricsCollector.SetCertsParsedTotal(8)
	metricsCollector.SetCertParseErrorsTotal(2)

	srv := server.NewWithRegistry(cfg, metricsCollector, healthChecker, log, registry)

	// Start server
	go func() {
		if err := srv.Start(); err != nil && err != http.ErrServerClosed {
			t.Errorf("Server start error: %v", err)
		}
	}()

	// Wait for server to start
	time.Sleep(100 * time.Millisecond)

	// Test metrics endpoint with context (noctx fix)
	ctx := context.Background()
	req, err := http.NewRequestWithContext(ctx, "GET", fmt.Sprintf("http://127.0.0.1:%d/metrics", port), nil)
	if err != nil {
		t.Fatal(err)
	}

	resp, err := http.DefaultClient.Do(req)
	if err != nil {
		t.Fatal(err)
	}
	// Handle close error (errcheck fix)
	defer func() {
		if err := resp.Body.Close(); err != nil {
			t.Logf("Failed to close response body: %v", err)
		}
	}()

	if resp.StatusCode != http.StatusOK {
		t.Errorf("Metrics endpoint status = %d, want %d", resp.StatusCode, http.StatusOK)
	}

	// Read response
	body, err := io.ReadAll(resp.Body)
	if err != nil {
		t.Fatal(err)
	}

	bodyStr := string(body)

	// Check for expected application metrics only
	expectedMetrics := []string{
		"ssl_cert_files_total",
		"ssl_certs_parsed_total",
		"ssl_cert_parse_errors_total",
	}

	for _, metric := range expectedMetrics {
		if !contains(bodyStr, metric) {
			t.Errorf("Metrics response missing expected metric: %s", metric)
		}
	}

	// Verify the test metrics we set are present with correct values
	if !contains(bodyStr, "ssl_cert_files_total 10") {
		t.Error("Expected ssl_cert_files_total to be 10")
	}
	if !contains(bodyStr, "ssl_certs_parsed_total 8") {
		t.Error("Expected ssl_certs_parsed_total to be 8")
	}
	if !contains(bodyStr, "ssl_cert_parse_errors_total 2") {
		t.Error("Expected ssl_cert_parse_errors_total to be 2")
	}

	// Shutdown server
	shutdownCtx, cancel := context.WithTimeout(context.Background(), 5*time.Second)
	defer cancel()
	if err := srv.Shutdown(shutdownCtx); err != nil {
		t.Errorf("Server shutdown error: %v", err)
	}
}

func TestGracefulShutdown(t *testing.T) {
	// Setup
	port := generateTestPort()
	cfg := &config.Config{
		Port:                   port,
		BindAddress:            "127.0.0.1",
		CertificateDirectories: []string{t.TempDir()},
		Workers:                2,
		LogLevel:               "info",
		ScanInterval:           1 * time.Minute,
	}

	registry := prometheus.NewRegistry()
	metricsCollector := metrics.NewCollectorWithRegistry(registry)
	healthChecker := health.New(cfg, metricsCollector)
	log := logger.NewNop()

	srv := server.NewWithRegistry(cfg, metricsCollector, healthChecker, log, registry)

	// Start server
	serverErr := make(chan error, 1)
	go func() {
		serverErr <- srv.Start()
	}()

	// Wait for server to start
	time.Sleep(100 * time.Millisecond)

	// Verify server is running with context (noctx fix)
	ctx := context.Background()
	req, err := http.NewRequestWithContext(ctx, "GET", fmt.Sprintf("http://127.0.0.1:%d/", port), nil)
	if err != nil {
		t.Fatal(err)
	}

	resp, err := http.DefaultClient.Do(req)
	if err != nil {
		t.Fatal(err)
	}
	// Handle close error (errcheck fix)
	if err := resp.Body.Close(); err != nil {
		t.Logf("Failed to close response body: %v", err)
	}

	// Shutdown server with timeout
	shutdownCtx, cancel := context.WithTimeout(context.Background(), 5*time.Second)
	defer cancel()

	shutdownStart := time.Now()
	if err := srv.Shutdown(shutdownCtx); err != nil {
		t.Errorf("Server shutdown error: %v", err)
	}
	shutdownDuration := time.Since(shutdownStart)

	// Verify shutdown completed within timeout
	if shutdownDuration > 5*time.Second {
		t.Errorf("Shutdown took too long: %v", shutdownDuration)
	}

	// Verify server stopped
	select {
	case err := <-serverErr:
		if err != http.ErrServerClosed {
			t.Errorf("Unexpected server error: %v", err)
		}
	case <-time.After(1 * time.Second):
		t.Error("Server did not stop after shutdown")
	}
}
