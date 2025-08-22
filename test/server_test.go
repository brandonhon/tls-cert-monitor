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

	srv := server.New(cfg, metricsCollector, healthChecker, log)

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

	for _, tt := range tests {
		t.Run(tt.name, func(t *testing.T) {
			resp, err := http.Get(baseURL + tt.endpoint)
			if err != nil {
				t.Fatal(err)
			}
			defer resp.Body.Close()

			if resp.StatusCode != tt.wantStatus {
				t.Errorf("Status code = %d, want %d", resp.StatusCode, tt.wantStatus)
			}
		})
	}

	// Shutdown server
	ctx, cancel := context.WithTimeout(context.Background(), 5*time.Second)
	defer cancel()
	if err := srv.Shutdown(ctx); err != nil {
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

	srv := server.New(cfg, metricsCollector, healthChecker, log)

	// Start server
	go func() {
		if err := srv.Start(); err != nil && err != http.ErrServerClosed {
			t.Errorf("Server start error: %v", err)
		}
	}()

	// Wait for server to start
	time.Sleep(100 * time.Millisecond)

	// Test health endpoint
	resp, err := http.Get(fmt.Sprintf("http://127.0.0.1:%d/healthz", port))
	if err != nil {
		t.Fatal(err)
	}
	defer resp.Body.Close()

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
	ctx, cancel := context.WithTimeout(context.Background(), 5*time.Second)
	defer cancel()
	if err := srv.Shutdown(ctx); err != nil {
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

	srv := server.New(cfg, metricsCollector, healthChecker, log)

	// Start server
	go func() {
		if err := srv.Start(); err != nil && err != http.ErrServerClosed {
			t.Errorf("Server start error: %v", err)
		}
	}()

	// Wait for server to start
	time.Sleep(100 * time.Millisecond)

	// Test metrics endpoint
	resp, err := http.Get(fmt.Sprintf("http://127.0.0.1:%d/metrics", port))
	if err != nil {
		t.Fatal(err)
	}
	defer resp.Body.Close()

	if resp.StatusCode != http.StatusOK {
		t.Errorf("Metrics endpoint status = %d, want %d", resp.StatusCode, http.StatusOK)
	}

	// Read response
	body, err := io.ReadAll(resp.Body)
	if err != nil {
		t.Fatal(err)
	}

	bodyStr := string(body)

	// Check for expected metrics
	expectedMetrics := []string{
		"ssl_cert_files_total",
		"ssl_certs_parsed_total",
		"ssl_cert_parse_errors_total",
		"go_memstats",
		"go_threads",
	}

	for _, metric := range expectedMetrics {
		if !contains(bodyStr, metric) {
			t.Errorf("Metrics response missing expected metric: %s", metric)
		}
	}

	// Shutdown server
	ctx, cancel := context.WithTimeout(context.Background(), 5*time.Second)
	defer cancel()
	if err := srv.Shutdown(ctx); err != nil {
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

	srv := server.New(cfg, metricsCollector, healthChecker, log)

	// Start server
	serverErr := make(chan error, 1)
	go func() {
		serverErr <- srv.Start()
	}()

	// Wait for server to start
	time.Sleep(100 * time.Millisecond)

	// Verify server is running
	resp, err := http.Get(fmt.Sprintf("http://127.0.0.1:%d/", port))
	if err != nil {
		t.Fatal(err)
	}
	resp.Body.Close()

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
