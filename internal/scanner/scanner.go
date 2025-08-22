// internal/scanner/scanner.go

package scanner

import (
	"context"
	"crypto/rsa"
	"crypto/sha256"
	"crypto/x509"
	"encoding/hex"
	"encoding/pem"
	"fmt"
	"io/fs"
	"os"
	"path/filepath"
	"strings"
	"sync"
	"time"

	"github.com/brandonhon/tls-cert-monitor/internal/cache"
	"github.com/brandonhon/tls-cert-monitor/internal/config"
	"github.com/brandonhon/tls-cert-monitor/internal/metrics"
	"github.com/fsnotify/fsnotify"
	"go.uber.org/zap"
)

// Scanner scans directories for SSL/TLS certificates
type Scanner struct {
	config   *config.Config
	metrics  *metrics.Collector
	logger   *zap.Logger
	cache    *cache.Cache
	watcher  *fsnotify.Watcher
	mu       sync.RWMutex
	stopChan chan struct{}
	wg       sync.WaitGroup
}

// CertificateInfo contains certificate details
type CertificateInfo struct {
	Path               string
	Subject            string
	Issuer             string
	SerialNumber       string
	NotBefore          time.Time
	NotAfter           time.Time
	SignatureAlgorithm string
	KeySize            int
	IsWeakKey          bool
	IsExpired          bool
	IsDeprecatedAlg    bool
	SANCount           int
	Fingerprint        string
}

// New creates a new certificate scanner
func New(cfg *config.Config, metrics *metrics.Collector, logger *zap.Logger) (*Scanner, error) {
	// Initialize cache
	cacheInstance, err := cache.New(cfg.CacheDir, cfg.CacheTTL, cfg.CacheMaxSize)
	if err != nil {
		return nil, fmt.Errorf("failed to initialize cache: %w", err)
	}

	// Initialize file watcher
	watcher, err := fsnotify.NewWatcher()
	if err != nil {
		return nil, fmt.Errorf("failed to create file watcher: %w", err)
	}

	s := &Scanner{
		config:   cfg,
		metrics:  metrics,
		logger:   logger,
		cache:    cacheInstance,
		watcher:  watcher,
		stopChan: make(chan struct{}),
	}

	return s, nil
}

// Scan performs a scan of all configured certificate directories
func (s *Scanner) Scan(ctx context.Context) error {
	s.logger.Info("Starting certificate scan")
	startTime := time.Now()

	// MOVED: Reset certificate metrics BEFORE starting workers to avoid race condition
	// This ensures we start with a clean slate
	s.metrics.ResetCertificateMetrics()

	var (
		totalFiles     int
		parsedCerts    int
		parseErrors    int
		weakKeys       int
		deprecatedAlgs int
		duplicates     = make(map[string]int)
		certsMu        sync.Mutex
		wg             sync.WaitGroup
		semaphore      = make(chan struct{}, s.config.Workers)
	)

	// Collect all certificate info for later metric updates
	var allCertInfos []*CertificateInfo
	var certInfosMu sync.Mutex

	// Scan each configured directory
	for _, dir := range s.config.CertificateDirectories {
		err := filepath.WalkDir(dir, func(path string, d fs.DirEntry, err error) error {
			if err != nil {
				s.logger.Warn("Error accessing path", zap.String("path", path), zap.Error(err))
				return nil
			}

			// Skip directories
			if d.IsDir() {
				return nil
			}

			// Check if file is a certificate
			if !s.isCertificateFile(path) {
				return nil
			}

			// Process certificate in worker pool
			wg.Add(1)
			go func(certPath string) {
				defer wg.Done()

				// Acquire semaphore
				semaphore <- struct{}{}
				defer func() { <-semaphore }()

				// Check context cancellation
				select {
				case <-ctx.Done():
					return
				default:
				}

				certsMu.Lock()
				totalFiles++
				certsMu.Unlock()

				// Process certificate
				if certInfo, err := s.processCertificate(certPath); err != nil {
					s.logger.Error("Failed to process certificate",
						zap.String("path", certPath),
						zap.Error(err))
					certsMu.Lock()
					parseErrors++
					certsMu.Unlock()
				} else if certInfo != nil {
					certsMu.Lock()
					parsedCerts++

					// Track duplicates
					duplicates[certInfo.Fingerprint]++

					// Track weak keys
					if certInfo.IsWeakKey {
						weakKeys++
					}

					// Track deprecated algorithms
					if certInfo.IsDeprecatedAlg {
						deprecatedAlgs++
					}
					certsMu.Unlock()

					// Store certificate info for later metric updates
					certInfosMu.Lock()
					allCertInfos = append(allCertInfos, certInfo)
					certInfosMu.Unlock()
				}
			}(path)

			return nil
		})

		if err != nil {
			s.logger.Error("Failed to scan directory", zap.String("dir", dir), zap.Error(err))
		}
	}

	// Wait for all workers to complete
	wg.Wait()

	// NOW update all certificate-specific metrics AFTER all workers are done
	// This ensures no race condition with ResetCertificateMetrics
	s.logger.Debug("Updating certificate-specific metrics", zap.Int("certificates", len(allCertInfos)))
	for _, certInfo := range allCertInfos {
		s.updateMetrics(certInfo)
	}

	// Update operational metrics
	s.metrics.SetCertFilesTotal(float64(totalFiles))
	s.metrics.SetCertsParsedTotal(float64(parsedCerts))
	s.metrics.SetCertParseErrorsTotal(float64(parseErrors))
	s.metrics.SetWeakKeyTotal(float64(weakKeys))
	s.metrics.SetDeprecatedSigAlgTotal(float64(deprecatedAlgs))
	s.metrics.SetScanDuration(time.Since(startTime).Seconds())
	s.metrics.SetLastScanTimestamp(float64(time.Now().Unix()))

	// Update duplicate metrics
	for fingerprint, count := range duplicates {
		if count > 1 {
			s.metrics.SetCertDuplicateCount(fingerprint, float64(count))
		}
	}

	s.logger.Info("Certificate scan completed",
		zap.Int("total_files", totalFiles),
		zap.Int("parsed_certs", parsedCerts),
		zap.Int("parse_errors", parseErrors),
		zap.Int("weak_keys", weakKeys),
		zap.Int("deprecated_algorithms", deprecatedAlgs),
		zap.Duration("duration", time.Since(startTime)))

	return nil
}

// WatchFiles watches certificate directories for changes
func (s *Scanner) WatchFiles(ctx context.Context) {
	s.wg.Add(1)
	defer s.wg.Done()

	// Add directories to watcher
	for _, dir := range s.config.CertificateDirectories {
		if err := s.watcher.Add(dir); err != nil {
			s.logger.Error("Failed to watch directory", zap.String("dir", dir), zap.Error(err))
			continue
		}
		s.logger.Info("Watching directory for changes", zap.String("dir", dir))
	}

	for {
		select {
		case <-ctx.Done():
			return
		case event, ok := <-s.watcher.Events:
			if !ok {
				return
			}

			// Check if it's a certificate file
			if !s.isCertificateFile(event.Name) {
				continue
			}

			// Handle file events
			switch {
			case event.Op&fsnotify.Write == fsnotify.Write:
				s.logger.Debug("Certificate file modified", zap.String("path", event.Name))
				s.handleFileChange(event.Name)
			case event.Op&fsnotify.Create == fsnotify.Create:
				s.logger.Debug("Certificate file created", zap.String("path", event.Name))
				s.handleFileChange(event.Name)
			case event.Op&fsnotify.Remove == fsnotify.Remove:
				s.logger.Debug("Certificate file removed", zap.String("path", event.Name))
				// Invalidate cache for removed file
				s.cache.Set(event.Name, nil)
			}

		case err, ok := <-s.watcher.Errors:
			if !ok {
				return
			}
			s.logger.Error("File watcher error", zap.Error(err))
		}
	}
}

// UpdateConfig updates the scanner configuration
func (s *Scanner) UpdateConfig(cfg *config.Config) error {
	s.mu.Lock()
	defer s.mu.Unlock()

	// Update configuration
	s.config = cfg

	// Reinitialize cache if directory changed
	if s.config.CacheDir != cfg.CacheDir {
		s.cache.Close()
		newCache, err := cache.New(cfg.CacheDir, cfg.CacheTTL, cfg.CacheMaxSize)
		if err != nil {
			return fmt.Errorf("failed to reinitialize cache: %w", err)
		}
		s.cache = newCache
	}

	return nil
}

// Close shuts down the scanner
func (s *Scanner) Close() {
	close(s.stopChan)
	s.watcher.Close()
	s.cache.Close()
	s.wg.Wait()
}

// processCertificate processes a single certificate file
func (s *Scanner) processCertificate(path string) (*CertificateInfo, error) {
	// Check cache first
	if cached := s.cache.Get(path); cached != nil {
		if certInfo, ok := cached.(*CertificateInfo); ok {
			return certInfo, nil
		}
	}

	// Read certificate file
	data, err := os.ReadFile(path)
	if err != nil {
		return nil, fmt.Errorf("failed to read certificate: %w", err)
	}

	// Parse certificate
	certInfo, err := s.parseCertificate(path, data)
	if err != nil {
		return nil, err
	}

	// Cache the result
	s.cache.Set(path, certInfo)

	return certInfo, nil
}

// parseCertificate parses certificate data
func (s *Scanner) parseCertificate(path string, data []byte) (*CertificateInfo, error) {
	// Decode PEM block
	block, _ := pem.Decode(data)
	if block == nil {
		// Try to parse as DER
		cert, err := x509.ParseCertificate(data)
		if err != nil {
			return nil, fmt.Errorf("failed to parse certificate: %w", err)
		}
		return s.extractCertInfo(path, cert), nil
	}

	// Parse PEM certificate
	cert, err := x509.ParseCertificate(block.Bytes)
	if err != nil {
		return nil, fmt.Errorf("failed to parse PEM certificate: %w", err)
	}

	return s.extractCertInfo(path, cert), nil
}

// extractCertInfo extracts information from a certificate
func (s *Scanner) extractCertInfo(path string, cert *x509.Certificate) *CertificateInfo {
	// Calculate fingerprint
	hash := sha256.Sum256(cert.Raw)
	fingerprint := hex.EncodeToString(hash[:])

	// Determine key size
	keySize := 0
	isWeakKey := false

	if cert.PublicKeyAlgorithm == x509.RSA {
		if rsaKey, ok := cert.PublicKey.(*rsa.PublicKey); ok {
			keySize = rsaKey.N.BitLen()
			isWeakKey = keySize < 2048
		}
	}

	// Check for deprecated signature algorithms
	isDeprecatedAlg := false
	switch cert.SignatureAlgorithm {
	case x509.MD5WithRSA, x509.SHA1WithRSA, x509.DSAWithSHA1, x509.ECDSAWithSHA1:
		isDeprecatedAlg = true
	}

	// Count SANs
	sanCount := len(cert.DNSNames) + len(cert.IPAddresses) + len(cert.EmailAddresses) + len(cert.URIs)

	return &CertificateInfo{
		Path:               path,
		Subject:            cert.Subject.String(),
		Issuer:             cert.Issuer.String(),
		SerialNumber:       cert.SerialNumber.String(),
		NotBefore:          cert.NotBefore,
		NotAfter:           cert.NotAfter,
		SignatureAlgorithm: cert.SignatureAlgorithm.String(),
		KeySize:            keySize,
		IsWeakKey:          isWeakKey,
		IsExpired:          time.Now().After(cert.NotAfter),
		IsDeprecatedAlg:    isDeprecatedAlg,
		SANCount:           sanCount,
		Fingerprint:        fingerprint,
	}
}

// updateMetrics updates Prometheus metrics for a certificate
func (s *Scanner) updateMetrics(certInfo *CertificateInfo) {
	// Certificate expiration
	s.metrics.SetCertExpiration(
		certInfo.Path,
		certInfo.Subject,
		certInfo.Issuer,
		float64(certInfo.NotAfter.Unix()),
	)

	// SAN count
	s.metrics.SetCertSANCount(certInfo.Path, float64(certInfo.SANCount))

	// Certificate info
	s.metrics.SetCertInfo(
		certInfo.Path,
		certInfo.Subject,
		certInfo.Issuer,
		certInfo.SerialNumber,
		certInfo.SignatureAlgorithm,
	)

	// Extract common name from subject
	commonName := extractCommonName(certInfo.Subject)
	if commonName == "" {
		commonName = "unknown"
	}

	// Extract filename from path
	fileName := filepath.Base(certInfo.Path)

	// Issuer classification with additional labels
	issuerCode := s.classifyIssuer(certInfo.Issuer)
	s.metrics.SetCertIssuerCodeWithLabels(certInfo.Issuer, commonName, fileName, float64(issuerCode))
}

// classifyIssuer classifies certificate issuer with updated classification codes
// Returns specific numeric codes for different CA types:
// DigiCert=30, Amazon=31, Other=32, Self-signed=33
func (s *Scanner) classifyIssuer(issuer string) int {
	lowerIssuer := strings.ToLower(issuer)

	// Self-signed certificates
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

// isCertificateFile checks if a file is likely a certificate
func (s *Scanner) isCertificateFile(path string) bool {
	ext := strings.ToLower(filepath.Ext(path))
	certExts := []string{".pem", ".crt", ".cer", ".cert", ".der", ".p7b", ".p7c", ".pfx", ".p12"}

	for _, certExt := range certExts {
		if ext == certExt {
			return true
		}
	}

	// Check filename patterns
	basename := strings.ToLower(filepath.Base(path))
	patterns := []string{"cert", "certificate", "chain", "bundle"}

	for _, pattern := range patterns {
		if strings.Contains(basename, pattern) {
			return true
		}
	}

	return false
}

// extractCommonName extracts the common name from a certificate subject string
func extractCommonName(subject string) string {
	// Subject format is typically: CN=example.com,O=Organization,C=US
	parts := strings.Split(subject, ",")
	for _, part := range parts {
		part = strings.TrimSpace(part)
		if strings.HasPrefix(strings.ToUpper(part), "CN=") {
			return strings.TrimSpace(part[3:]) // Remove "CN=" prefix
		}
	}
	return ""
}

// handleFileChange handles certificate file changes
func (s *Scanner) handleFileChange(path string) {
	// Process the changed certificate
	certInfo, err := s.processCertificate(path)
	if err != nil {
		s.logger.Error("Failed to process changed certificate",
			zap.String("path", path),
			zap.Error(err))
		return
	}

	if certInfo != nil {
		// Update metrics for the changed certificate
		s.updateMetrics(certInfo)
		s.logger.Info("Certificate updated",
			zap.String("path", path),
			zap.String("subject", certInfo.Subject))
	}
}
