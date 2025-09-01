// Package health provides health checking functionality for the TLS Certificate Monitor.
// It performs various system and application checks to ensure the service is operating correctly.
package health

import (
	"encoding/json"
	"fmt"
	"os"
	"path/filepath"
	"runtime"
	"strings"
	"sync"
	"syscall"
	"time"

	"github.com/brandonhon/tls-cert-monitor/internal/cache"
	"github.com/brandonhon/tls-cert-monitor/internal/config"
	"github.com/brandonhon/tls-cert-monitor/internal/metrics"
)

// Status represents health check status
type Status string

const (
	// StatusHealthy indicates the component is functioning normally
	StatusHealthy Status = "healthy"
	// StatusDegraded indicates the component is functioning but with issues
	StatusDegraded Status = "degraded"
	// StatusUnhealthy indicates the component is not functioning properly
	StatusUnhealthy Status = "unhealthy"
)

// Check represents a single health check
// Field order optimized for memory alignment (fieldalignment fix)
type Check struct {
	Value       interface{} `json:"value,omitempty"`   // 16 bytes
	LastChecked time.Time   `json:"last_checked"`      // 24 bytes
	Name        string      `json:"name"`              // 16 bytes
	Message     string      `json:"message,omitempty"` // 16 bytes
	Status      Status      `json:"status"`            // 16 bytes
}

// Response represents the health check response
// Field order optimized for memory alignment (fieldalignment fix)
type Response struct {
	Checks    []Check                `json:"checks"`    // 24 bytes
	Metadata  map[string]interface{} `json:"metadata"`  // 8 bytes
	Timestamp time.Time              `json:"timestamp"` // 24 bytes
	Status    Status                 `json:"status"`    // 16 bytes
}

// Checker performs health checks
type Checker struct {
	config  *config.Config
	metrics *metrics.Collector
	cache   *cache.Cache
	mu      sync.RWMutex
}

// New creates a new health checker
func New(cfg *config.Config, metrics *metrics.Collector) *Checker {
	return &Checker{
		config:  cfg,
		metrics: metrics,
	}
}

// SetCache sets the cache for health checks
func (c *Checker) SetCache(cache *cache.Cache) {
	c.mu.Lock()
	defer c.mu.Unlock()
	c.cache = cache
}

// UpdateConfig updates the configuration
func (c *Checker) UpdateConfig(cfg *config.Config) {
	c.mu.Lock()
	defer c.mu.Unlock()
	c.config = cfg
}

// Check performs all health checks
// Refactored to reduce cyclomatic complexity (gocyclo fix)
func (c *Checker) Check() *Response {
	c.mu.RLock()
	defer c.mu.RUnlock()

	checks := []Check{}

	// Collect all checks
	checkGroups := [][]Check{
		c.checkCache(),
		c.checkCertificates(),
		c.checkConfiguration(),
		c.checkDiskSpace(),
		c.checkSystem(),
	}

	// Merge all checks and determine overall status
	overallStatus := StatusHealthy
	for _, group := range checkGroups {
		checks = append(checks, group...)
		overallStatus = c.updateOverallStatus(overallStatus, group)
	}

	return &Response{
		Status:    overallStatus,
		Timestamp: time.Now(),
		Checks:    checks,
		Metadata: map[string]interface{}{
			"version":    "1.0.0",
			"go_version": runtime.Version(),
			"pid":        os.Getpid(),
		},
	}
}

// updateOverallStatus determines the worst status from a group of checks
func (c *Checker) updateOverallStatus(current Status, checks []Check) Status {
	for _, check := range checks {
		if check.Status == StatusUnhealthy {
			return StatusUnhealthy
		}
		if check.Status == StatusDegraded && current == StatusHealthy {
			current = StatusDegraded
		}
	}
	return current
}

// checkCache performs cache-related health checks
func (c *Checker) checkCache() []Check {
	if c.cache == nil {
		return []Check{}
	}

	stats := c.cache.Stats()

	// Build checks using appendCombine fix
	checks := []Check{
		{
			Name:        "cache_entries_total",
			Status:      StatusHealthy,
			Value:       stats["entries"],
			LastChecked: time.Now(),
		},
		{
			Name:        "cache_file_path",
			Status:      StatusHealthy,
			Value:       filepath.Join(c.config.CacheDir, "cache.gob"),
			LastChecked: time.Now(),
		},
	}

	// Cache file writable check
	writable := c.isPathWritable(c.config.CacheDir)
	writableStatus := StatusHealthy
	if !writable {
		writableStatus = StatusDegraded
	}
	checks = append(checks, Check{
		Name:        "cache_file_writable",
		Status:      writableStatus,
		Value:       writable,
		LastChecked: time.Now(),
	})

	// Cache hit rate check with safe type assertions (forcetypeassert fix)
	hitRateStatus := StatusHealthy
	if hitRateVal, ok := stats["hit_rate"].(float64); ok {
		if totalVal, ok := stats["total_accesses"].(uint64); ok && totalVal > 100 && hitRateVal < 0.5 {
			hitRateStatus = StatusDegraded
		}
		checks = append(checks, Check{
			Name:        "cache_hit_rate",
			Status:      hitRateStatus,
			Value:       hitRateVal,
			LastChecked: time.Now(),
		})
	}

	// Total accesses
	checks = append(checks, Check{
		Name:        "cache_total_accesses",
		Status:      StatusHealthy,
		Value:       stats["total_accesses"],
		LastChecked: time.Now(),
	})

	return checks
}

// checkCertificates performs certificate-related health checks
func (c *Checker) checkCertificates() []Check {
	metricValues := c.metrics.GetMetrics()

	// Certificate files total
	certFiles := metricValues["cert_files_total"]
	certFilesStatus := StatusHealthy
	if certFiles == 0 {
		certFilesStatus = StatusDegraded
	}

	// Parse errors check
	parseErrors := metricValues["cert_parse_errors_total"]
	parsedTotal := metricValues["certs_parsed_total"]
	parseErrorStatus := StatusHealthy
	if parsedTotal > 0 && parseErrors/parsedTotal > 0.1 {
		parseErrorStatus = StatusDegraded
	}

	// Certificate scan status
	lastScan := metricValues["last_scan_timestamp"]
	scanAge := time.Since(time.Unix(int64(lastScan), 0))
	scanStatus := StatusHealthy
	scanMessage := "Last scan completed successfully"
	if scanAge > c.config.ScanInterval*2 {
		scanStatus = StatusDegraded
		scanMessage = "Scan is overdue"
	}

	// Build all certificate checks at once (appendCombine fix)
	return []Check{
		{
			Name:        "cert_files_total",
			Status:      certFilesStatus,
			Value:       certFiles,
			LastChecked: time.Now(),
		},
		{
			Name:        "cert_parse_errors_total",
			Status:      parseErrorStatus,
			Value:       parseErrors,
			LastChecked: time.Now(),
		},
		{
			Name:        "certs_parsed_total",
			Status:      StatusHealthy,
			Value:       parsedTotal,
			LastChecked: time.Now(),
		},
		{
			Name:        "cert_scan_status",
			Status:      scanStatus,
			Value:       scanAge.String(),
			Message:     scanMessage,
			LastChecked: time.Now(),
		},
		{
			Name:        "certificate_directories",
			Status:      StatusHealthy,
			Value:       c.config.CertificateDirectories,
			LastChecked: time.Now(),
		},
	}
}

// checkConfiguration performs configuration-related health checks
func (c *Checker) checkConfiguration() []Check {
	// Config file status
	configFile := "none"
	if c.config != nil {
		configFile = "loaded"
	}

	// Log file writable check
	logWritableStatus := StatusHealthy
	if c.config.LogFile != "" && !c.isPathWritable(filepath.Dir(c.config.LogFile)) {
		logWritableStatus = StatusDegraded
	}

	// Build all configuration checks at once (appendCombine fix)
	return []Check{
		{
			Name:        "config_file",
			Status:      StatusHealthy,
			Value:       configFile,
			LastChecked: time.Now(),
		},
		{
			Name:        "hot_reload_enabled",
			Status:      StatusHealthy,
			Value:       c.config.HotReload,
			LastChecked: time.Now(),
		},
		{
			Name:        "log_file_writable",
			Status:      logWritableStatus,
			Value:       c.config.LogFile != "",
			LastChecked: time.Now(),
		},
		{
			Name:        "prometheus_registry",
			Status:      StatusHealthy,
			Value:       "active",
			LastChecked: time.Now(),
		},
		{
			Name:        "worker_pool_size",
			Status:      StatusHealthy,
			Value:       c.config.Workers,
			LastChecked: time.Now(),
		},
	}
}

// checkDiskSpace performs disk space checks
func (c *Checker) checkDiskSpace() []Check {
	checks := []Check{}

	for _, dir := range c.config.CertificateDirectories {
		usage := c.getDiskUsage(dir)
		status := StatusHealthy
		if usage.UsedPercent > 90 {
			status = StatusUnhealthy
		} else if usage.UsedPercent > 80 {
			status = StatusDegraded
		}

		checkName := "disk_space_" + filepath.Base(dir)
		checks = append(checks, Check{
			Name:   checkName,
			Status: status,
			Value: map[string]interface{}{
				"path":         dir,
				"used_percent": usage.UsedPercent,
				"free_bytes":   usage.Free,
			},
			LastChecked: time.Now(),
		})
	}

	return checks
}

// checkSystem performs system-level health checks
func (c *Checker) checkSystem() []Check {
	// Memory usage
	var m runtime.MemStats
	runtime.ReadMemStats(&m)

	// Build system check (appendCombine fix)
	return []Check{
		{
			Name:   "memory_usage",
			Status: StatusHealthy,
			Value: map[string]interface{}{
				"alloc_mb":   m.Alloc / 1024 / 1024,
				"sys_mb":     m.Sys / 1024 / 1024,
				"num_gc":     m.NumGC,
				"goroutines": runtime.NumGoroutine(),
			},
			LastChecked: time.Now(),
		},
	}
}

// isPathWritable checks if a path is writable using a secure method
// Fixed gosec G304 issue by validating the path and using secure file creation
func (c *Checker) isPathWritable(path string) bool {
	// Validate the path to prevent directory traversal
	cleanPath := filepath.Clean(path)

	// Check if the path is within allowed directories
	if !c.isPathAllowed(cleanPath) {
		return false
	}

	// Create a secure test file name with timestamp to avoid conflicts
	testFileName := fmt.Sprintf(".healthcheck_%d", time.Now().UnixNano())
	testFile := filepath.Join(cleanPath, testFileName)

	// Use secure file creation with restricted permissions (gosec G304 fix)
	// gosec G304: This is intentional file creation with validated path and restricted permissions
	file, err := os.OpenFile(testFile, os.O_CREATE|os.O_WRONLY|os.O_EXCL, 0600) // #nosec G304
	if err != nil {
		return false
	}

	// Properly handle file close and remove (errcheck fix)
	if err := file.Close(); err != nil {
		// Log but continue - file was created successfully
		return true
	}
	if err := os.Remove(testFile); err != nil {
		// Log but don't fail - file was writable
		return true
	}
	return true
}

// isPathAllowed validates that the path is within configured directories
// to prevent directory traversal attacks
func (c *Checker) isPathAllowed(path string) bool {
	cleanPath := filepath.Clean(path)

	// Check against certificate directories
	for _, dir := range c.config.CertificateDirectories {
		cleanDir := filepath.Clean(dir)
		if isWithinDirectory(cleanPath, cleanDir) {
			return true
		}
	}

	// Check against cache directory
	if c.config.CacheDir != "" {
		cleanCacheDir := filepath.Clean(c.config.CacheDir)
		if isWithinDirectory(cleanPath, cleanCacheDir) {
			return true
		}
	}

	// Check against log directory
	if c.config.LogFile != "" {
		logDir := filepath.Dir(c.config.LogFile)
		cleanLogDir := filepath.Clean(logDir)
		if isWithinDirectory(cleanPath, cleanLogDir) {
			return true
		}
	}

	return false
}

// isWithinDirectory checks if a path is within a base directory
func isWithinDirectory(path, baseDir string) bool {
	rel, err := filepath.Rel(baseDir, path)
	if err != nil {
		return false
	}

	// Check for path traversal attempts
	return !filepath.IsAbs(rel) && !strings.HasPrefix(rel, "..")
}

// DiskUsage represents disk usage statistics
type DiskUsage struct {
	Total       uint64
	Free        uint64
	Used        uint64
	UsedPercent float64
}

// getDiskUsage gets disk usage for a path
func (c *Checker) getDiskUsage(path string) DiskUsage {
	var stat syscall.Statfs_t
	if err := syscall.Statfs(path, &stat); err != nil {
		return DiskUsage{}
	}

	total := stat.Blocks * uint64(stat.Bsize)
	free := stat.Bavail * uint64(stat.Bsize)
	used := total - free
	usedPercent := float64(used) / float64(total) * 100

	return DiskUsage{
		Total:       total,
		Free:        free,
		Used:        used,
		UsedPercent: usedPercent,
	}
}

// ToJSON converts the response to JSON
func (r *Response) ToJSON() ([]byte, error) {
	return json.MarshalIndent(r, "", "  ")
}
