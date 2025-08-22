// internal/metrics/metrics.go

package metrics

import (
	"fmt"
	"sync"

	"github.com/prometheus/client_golang/prometheus"
	"github.com/prometheus/client_golang/prometheus/collectors"
	dto "github.com/prometheus/client_model/go"
)

var (
	once     sync.Once
	instance *Collector
)

// Collector manages all Prometheus metrics
type Collector struct {
	// Certificate metrics
	certExpiration     *prometheus.GaugeVec
	certSANCount       *prometheus.GaugeVec
	certInfo           *prometheus.GaugeVec
	certDuplicateCount *prometheus.GaugeVec
	certIssuerCode     *prometheus.GaugeVec

	// Security metrics
	weakKeyTotal     prometheus.Gauge
	deprecatedSigAlg prometheus.Gauge

	// Operational metrics
	certFilesTotal       prometheus.Gauge
	certsParsedTotal     prometheus.Gauge
	certParseErrorsTotal prometheus.Gauge
	scanDuration         prometheus.Gauge
	lastScanTimestamp    prometheus.Gauge

	mu       sync.RWMutex
	registry prometheus.Registerer
}

// NewCollector creates a new metrics collector (singleton for default registry)
func NewCollector() *Collector {
	once.Do(func() {
		instance = createCollector(prometheus.DefaultRegisterer)
	})
	return instance
}

// NewCollectorWithRegistry creates a new metrics collector with a custom registry (for testing)
func NewCollectorWithRegistry(reg prometheus.Registerer) *Collector {
	return createCollector(reg)
}

// createCollector creates the actual collector instance
func createCollector(reg prometheus.Registerer) *Collector {
	c := &Collector{
		registry: reg,
		// Certificate metrics
		certExpiration: prometheus.NewGaugeVec(
			prometheus.GaugeOpts{
				Name: "ssl_cert_expiration_timestamp",
				Help: "Certificate expiration time (Unix timestamp)",
			},
			[]string{"path", "subject", "issuer"},
		),
		certSANCount: prometheus.NewGaugeVec(
			prometheus.GaugeOpts{
				Name: "ssl_cert_san_count",
				Help: "Number of Subject Alternative Names",
			},
			[]string{"path"},
		),
		certInfo: prometheus.NewGaugeVec(
			prometheus.GaugeOpts{
				Name: "ssl_cert_info",
				Help: "Certificate information with labels",
			},
			[]string{"path", "subject", "issuer", "serial", "signature_algorithm"},
		),
		certDuplicateCount: prometheus.NewGaugeVec(
			prometheus.GaugeOpts{
				Name: "ssl_cert_duplicate_count",
				Help: "Number of duplicate certificates",
			},
			[]string{"fingerprint"},
		),
		certIssuerCode: prometheus.NewGaugeVec(
			prometheus.GaugeOpts{
				Name: "ssl_cert_issuer_code",
				Help: "Numeric issuer classification",
			},
			[]string{"issuer", "common_name", "file_name"},
		),

		// Security metrics
		weakKeyTotal: prometheus.NewGauge(
			prometheus.GaugeOpts{
				Name: "ssl_cert_weak_key_total",
				Help: "Certificates with weak cryptographic keys",
			},
		),
		deprecatedSigAlg: prometheus.NewGauge(
			prometheus.GaugeOpts{
				Name: "ssl_cert_deprecated_sigalg_total",
				Help: "Certificates using deprecated signature algorithms",
			},
		),

		// Operational metrics
		certFilesTotal: prometheus.NewGauge(
			prometheus.GaugeOpts{
				Name: "ssl_cert_files_total",
				Help: "Total certificate files processed",
			},
		),
		certsParsedTotal: prometheus.NewGauge(
			prometheus.GaugeOpts{
				Name: "ssl_certs_parsed_total",
				Help: "Successfully parsed certificates",
			},
		),
		certParseErrorsTotal: prometheus.NewGauge(
			prometheus.GaugeOpts{
				Name: "ssl_cert_parse_errors_total",
				Help: "Certificate parsing errors",
			},
		),
		scanDuration: prometheus.NewGauge(
			prometheus.GaugeOpts{
				Name: "ssl_cert_scan_duration_seconds",
				Help: "Directory scan duration",
			},
		),
		lastScanTimestamp: prometheus.NewGauge(
			prometheus.GaugeOpts{
				Name: "ssl_cert_last_scan_timestamp",
				Help: "Last successful scan time",
			},
		),
	}

	// Register all metrics with the provided registerer
	c.registerMetrics(reg)

	return c
}

// safeRegister safely registers a collector, logging warnings instead of panicking on duplicates
func (c *Collector) safeRegister(reg prometheus.Registerer, collector prometheus.Collector, name string) {
	if err := reg.Register(collector); err != nil {
		if areErr, ok := err.(prometheus.AlreadyRegisteredError); ok {
			// Log warning but continue - this is expected in some scenarios
			fmt.Printf("Warning: Metric %s already registered, using existing instance: %v\n", name, areErr)
		} else {
			// Log error for other registration issues but don't panic
			fmt.Printf("Warning: Failed to register metric %s: %v\n", name, err)
		}
	}
}

// registerMetrics registers all metrics with the provided registerer
func (c *Collector) registerMetrics(reg prometheus.Registerer) {
	// Certificate metrics - use safe registration
	c.safeRegister(reg, c.certExpiration, "ssl_cert_expiration_timestamp")
	c.safeRegister(reg, c.certSANCount, "ssl_cert_san_count")
	c.safeRegister(reg, c.certInfo, "ssl_cert_info")
	c.safeRegister(reg, c.certDuplicateCount, "ssl_cert_duplicate_count")
	c.safeRegister(reg, c.certIssuerCode, "ssl_cert_issuer_code")

	// Security metrics
	c.safeRegister(reg, c.weakKeyTotal, "ssl_cert_weak_key_total")
	c.safeRegister(reg, c.deprecatedSigAlg, "ssl_cert_deprecated_sigalg_total")

	// Operational metrics
	c.safeRegister(reg, c.certFilesTotal, "ssl_cert_files_total")
	c.safeRegister(reg, c.certsParsedTotal, "ssl_certs_parsed_total")
	c.safeRegister(reg, c.certParseErrorsTotal, "ssl_cert_parse_errors_total")
	c.safeRegister(reg, c.scanDuration, "ssl_cert_scan_duration_seconds")
	c.safeRegister(reg, c.lastScanTimestamp, "ssl_cert_last_scan_timestamp")

	// Only register Go runtime metrics if using default registry
	// Use safe registration for these as they're commonly registered by other code
	if reg == prometheus.DefaultRegisterer {
		c.safeRegister(reg, collectors.NewGoCollector(), "go_collector")
		c.safeRegister(reg, collectors.NewProcessCollector(collectors.ProcessCollectorOpts{}), "process_collector")
	}
}

// ResetCertificateMetrics resets certificate-specific metrics
func (c *Collector) ResetCertificateMetrics() {
	c.mu.Lock()
	defer c.mu.Unlock()

	c.certExpiration.Reset()
	c.certSANCount.Reset()
	c.certInfo.Reset()
	c.certDuplicateCount.Reset()
	c.certIssuerCode.Reset()
}

// SetCertExpiration sets certificate expiration metric
func (c *Collector) SetCertExpiration(path, subject, issuer string, timestamp float64) {
	c.certExpiration.WithLabelValues(path, subject, issuer).Set(timestamp)
}

// SetCertSANCount sets SAN count metric
func (c *Collector) SetCertSANCount(path string, count float64) {
	c.certSANCount.WithLabelValues(path).Set(count)
}

// SetCertInfo sets certificate info metric
func (c *Collector) SetCertInfo(path, subject, issuer, serial, sigAlg string) {
	c.certInfo.WithLabelValues(path, subject, issuer, serial, sigAlg).Set(1)
}

// SetCertDuplicateCount sets duplicate count metric
func (c *Collector) SetCertDuplicateCount(fingerprint string, count float64) {
	c.certDuplicateCount.WithLabelValues(fingerprint).Set(count)
}

// SetCertIssuerCode sets issuer code metric (legacy method for backward compatibility)
func (c *Collector) SetCertIssuerCode(issuer string, code float64) {
	c.certIssuerCode.WithLabelValues(issuer, "", "").Set(code)
}

// SetCertIssuerCodeWithLabels sets issuer code metric with additional labels
func (c *Collector) SetCertIssuerCodeWithLabels(issuer, commonName, fileName string, code float64) {
	c.certIssuerCode.WithLabelValues(issuer, commonName, fileName).Set(code)
}

// SetWeakKeyTotal sets weak key total metric
func (c *Collector) SetWeakKeyTotal(total float64) {
	c.weakKeyTotal.Set(total)
}

// SetDeprecatedSigAlgTotal sets deprecated signature algorithm total metric
func (c *Collector) SetDeprecatedSigAlgTotal(total float64) {
	c.deprecatedSigAlg.Set(total)
}

// SetCertFilesTotal sets total certificate files metric
func (c *Collector) SetCertFilesTotal(total float64) {
	c.certFilesTotal.Set(total)
}

// SetCertsParsedTotal sets parsed certificates total metric
func (c *Collector) SetCertsParsedTotal(total float64) {
	c.certsParsedTotal.Set(total)
}

// SetCertParseErrorsTotal sets parse errors total metric
func (c *Collector) SetCertParseErrorsTotal(total float64) {
	c.certParseErrorsTotal.Set(total)
}

// SetScanDuration sets scan duration metric
func (c *Collector) SetScanDuration(seconds float64) {
	c.scanDuration.Set(seconds)
}

// SetLastScanTimestamp sets last scan timestamp metric
func (c *Collector) SetLastScanTimestamp(timestamp float64) {
	c.lastScanTimestamp.Set(timestamp)
}

// GetMetrics returns current metric values for health checks
func (c *Collector) GetMetrics() map[string]float64 {
	c.mu.RLock()
	defer c.mu.RUnlock()

	metrics := make(map[string]float64)

	// Gather current values
	metrics["cert_files_total"] = c.getGaugeValue(c.certFilesTotal)
	metrics["certs_parsed_total"] = c.getGaugeValue(c.certsParsedTotal)
	metrics["cert_parse_errors_total"] = c.getGaugeValue(c.certParseErrorsTotal)
	metrics["weak_key_total"] = c.getGaugeValue(c.weakKeyTotal)
	metrics["deprecated_sigalg_total"] = c.getGaugeValue(c.deprecatedSigAlg)
	metrics["last_scan_timestamp"] = c.getGaugeValue(c.lastScanTimestamp)

	return metrics
}

// getGaugeValue safely retrieves a gauge value
func (c *Collector) getGaugeValue(gauge prometheus.Gauge) float64 {
	metric := &dto.Metric{}
	gauge.Write(metric)
	if metric.Gauge != nil && metric.Gauge.Value != nil {
		return *metric.Gauge.Value
	}
	return 0
}
