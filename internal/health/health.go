package health

import (
	"encoding/json"
	"os"
	"path/filepath"
	"runtime"
	"sync"
	"syscall"
	"time"

	"github.com/yourusername/tls-cert-monitor/internal/cache"
	"github.com/yourusername/tls-cert-monitor/internal/config"
	"github.com/yourusername/tls-cert-monitor/internal/metrics"
)

// Status represents health check status
type Status string

const (
	StatusHealthy   Status = "healthy"
	StatusDegraded  Status = "degraded"
	StatusUnhealthy Status = "unhealthy"
)

// Check represents a single health check
type Check struct {
	Name        string      `json:"name"`
	Status      Status      `json:"status"`
	Value       interface{} `json:"value,omitempty"`
	Message     string      `json:"message,omitempty"`
	LastChecked time.Time   `json:"last_checked"`
}

// Response represents the health check response
type Response struct {
	Status      Status           `json:"status"`
	Timestamp   time.Time        `json:"timestamp"`
	Checks      []Check          `json:"checks"`
	Metadata    map[string]interface{} `json:"metadata"`
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
func (c *Checker) Check() *Response {
	c.mu.RLock()
	defer c.mu.RUnlock()

	checks := []Check{}
	overallStatus := StatusHealthy

	// Cache checks
	if c.cache != nil {
		cacheChecks := c.checkCache()
		checks = append(checks, cacheChecks...)
		for _, check := range cacheChecks {
			if check.Status == StatusUnhealthy {
				overallStatus = StatusUnhealthy
			} else if check.Status == StatusDegraded && overallStatus == StatusHealthy {
				overallStatus = StatusDegraded
			}
		}
	}

	// Certificate scan checks
	certChecks := c.checkCertificates()
	checks = append(checks, certChecks...)
	for _, check := range certChecks {
		if check.Status == StatusUnhealthy {
			overallStatus = StatusUnhealthy
		} else if check.Status == StatusDegraded && overallStatus == StatusHealthy {
			overallStatus = StatusDegraded
		}
	}

	// Configuration checks
	configChecks := c.checkConfiguration()
	checks = append(checks, configChecks...)
	for _, check := range configChecks {
		if check.Status == StatusUnhealthy {
			overallStatus = StatusUnhealthy
		} else if check.Status == StatusDegraded && overallStatus == StatusHealthy {
			overallStatus = StatusDegraded
		}
	}

	// Disk space checks
	diskChecks := c.checkDiskSpace()
	checks = append(checks, diskChecks...)
	for _, check := range diskChecks {
		if check.Status == StatusUnhealthy {
			overallStatus = StatusUnhealthy
		} else if check.Status == StatusDegraded && overallStatus == StatusHealthy {
			overallStatus = StatusDegraded
		}
	}

	// System checks
	systemChecks := c.checkSystem()
	checks = append(checks, systemChecks...)

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

// checkCache performs cache-related health checks
func (c *Checker) checkCache() []Check {
	checks := []Check{}

	if c.cache == nil {
		return checks
	}

	stats := c.cache.Stats()

	// Cache entries total
	checks = append(checks, Check{
		Name:        "cache_entries_total",
		Status:      StatusHealthy,
		Value:       stats["entries"],
		LastChecked: time.Now(),
	})

	// Cache file path
	cachePath := filepath.Join(c.config.CacheDir, "cache.gob")
	checks = append(checks, Check{
		Name:        "cache_file_path",
		Status:      StatusHealthy,
		Value:       cachePath,
		LastChecked: time.Now(),
	})

	// Cache file writable
	writable := c.isPathWritable(c.config.CacheDir)
	status := StatusHealthy
	if !writable {
		status = StatusDegraded
	}
	checks = append(checks, Check{
		Name:        "cache_file_writable",
		Status:      status,
		Value:       writable,
		LastChecked: time.Now(),
	})

	// Cache hit rate
	hitRate := stats["hit_rate"].(float64)
	status = StatusHealthy
	if hitRate < 0.5 && stats["total_accesses"].(uint64) > 100 {
		status = StatusDegraded
	}
	checks = append(checks, Check{
		Name:        "cache_hit_rate",
		Status:      status,
		Value:       hitRate,
		LastChecked: time.Now(),
	})

	// Cache total accesses
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
	checks := []Check{}
	
	metricValues := c.metrics.GetMetrics()

	// Certificate files total
	certFiles := metricValues["cert_files_total"]
	status := StatusHealthy
	if certFiles == 0 {
		status = StatusDegraded
	}
	checks = append(checks, Check{
		Name:        "cert_files_total",
		Status:      status,
		Value:       certFiles,
		LastChecked: time.Now(),
	})

	// Parse errors total
	parseErrors := metricValues["cert_parse_errors_total"]
	parsedTotal := metricValues["certs_parsed_total"]
	status = StatusHealthy
	if parsedTotal > 0 && parseErrors/parsedTotal > 0.1 {
		status = StatusDegraded
	}
	checks = append(checks, Check{
		Name:        "cert_parse_errors_total",
		Status:      status,
		Value:       parseErrors,
		LastChecked: time.Now(),
	})

	// Certificates parsed total
	checks = append(checks, Check{
		Name:        "certs_parsed_total",
		Status:      StatusHealthy,
		Value:       parsedTotal,
		LastChecked: time.Now(),
	})

	// Certificate scan status
	lastScan := metricValues["last_scan_timestamp"]
	scanAge := time.Since(time.Unix(int64(lastScan), 0))
	status = StatusHealthy
	message := "Last scan completed successfully"
	if scanAge > c.config.ScanInterval*2 {
		status = StatusDegraded
		message = "Scan is overdue"
	}
	checks = append(checks, Check{
		Name:        "cert_scan_status",
		Status:      status,
		Value:       scanAge.String(),
		Message:     message,
		LastChecked: time.Now(),
	})

	// Certificate directories
	checks = append(checks, Check{
		Name:        "certificate_directories",
		Status:      StatusHealthy,
		Value:       c.config.CertificateDirectories,
		LastChecked: time.Now(),
	})

	return checks
}

// checkConfiguration performs configuration-related health checks
func (c *Checker) checkConfiguration() []Check {
	checks := []Check{}

	// Config file
	configFile := "none"
	if c.config != nil {
		configFile = "loaded"
	}
	checks = append(checks, Check{
		Name:        "config_file",
		Status:      StatusHealthy,
		Value:       configFile,
		LastChecked: time.Now(),
	})

	// Hot reload enabled
	checks = append(checks, Check{
		Name:        "hot_reload_enabled",
		Status:      StatusHealthy,
		Value:       c.config.HotReload,
		LastChecked: time.Now(),
	})

	// Log file writable
	status := StatusHealthy
	if c.config.LogFile != "" {
		if !c.isPathWritable(filepath.Dir(c.config.LogFile)) {
			status = StatusDegraded
		}
	}
	checks = append(checks, Check{
		Name:        "log_file_writable",
		Status:      status,
		Value:       c.config.LogFile != "",
		LastChecked: time.Now(),
	})

	// Prometheus registry
	checks = append(checks, Check{
		Name:        "prometheus_registry",
		Status:      StatusHealthy,
		Value:       "active",
		LastChecked: time.Now(),
	})

	// Worker pool size
	checks = append(checks, Check{
		Name:        "worker_pool_size",
		Status:      StatusHealthy,
		Value:       c.config.Workers,
		LastChecked: time.Now(),
	})

	return checks
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
	checks := []Check{}

	// Memory usage
	var m runtime.MemStats
	runtime.ReadMemStats(&m)
	
	checks = append(checks, Check{
		Name:   "memory_usage",
		Status: StatusHealthy,
		Value: map[string]interface{}{
			"alloc_mb":       m.Alloc / 1024 / 1024,
			"sys_mb":         m.Sys / 1024 / 1024,
			"num_gc":         m.NumGC,
			"goroutines":     runtime.NumGoroutine(),
		},
		LastChecked: time.Now(),
	})

	return checks
}

// isPathWritable checks if a path is writable
func (c *Checker) isPathWritable(path string) bool {
	testFile := filepath.Join(path, ".healthcheck")
	file, err := os.Create(testFile)
	if err != nil {
		return false
	}
	file.Close()
	os.Remove(testFile)
	return true
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