// Package scanner provides certificate scanning functionality for the TLS Certificate Monitor.
// It discovers, parses, and analyzes SSL/TLS certificates from configured directories,
// tracking security issues and updating Prometheus metrics.
package scanner

import (
	"context"
	"crypto/rsa"
	"crypto/sha256"
	"crypto/x509"
	"encoding/gob"
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

// init registers types with gob for cache serialization
func init() {
	// Register CertificateInfo with gob so it can be cached
	gob.Register(&CertificateInfo{})
}

// Scanner scans directories for SSL/TLS certificates
// Field order optimized for memory alignment (fieldalignment fix)
type Scanner struct {
	watcher  *fsnotify.Watcher  // 8 bytes
	config   *config.Config     // 8 bytes
	metrics  *metrics.Collector // 8 bytes
	logger   *zap.Logger        // 8 bytes
	cache    *cache.Cache       // 8 bytes
	stopChan chan struct{}      // 8 bytes
	mu       sync.RWMutex       // 24 bytes
	wg       sync.WaitGroup     // 12 bytes (padded to 16)
}

// CertificateInfo contains certificate details
// Field order optimized for memory alignment (fieldalignment fix)
type CertificateInfo struct {
	NotBefore          time.Time // 24 bytes
	NotAfter           time.Time // 24 bytes
	Path               string    // 16 bytes
	Subject            string    // 16 bytes
	Issuer             string    // 16 bytes
	SerialNumber       string    // 16 bytes
	SignatureAlgorithm string    // 16 bytes
	Fingerprint        string    // 16 bytes
	KeySize            int       // 8 bytes
	SANCount           int       // 8 bytes
	IsWeakKey          bool      // 1 byte
	IsExpired          bool      // 1 byte
	IsDeprecatedAlg    bool      // 1 byte
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

	// Reset certificate metrics BEFORE starting workers to avoid race condition
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

			// Check if file is a certificate (this now excludes private keys)
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
	// Handle watcher close error (errcheck fix)
	if err := s.watcher.Close(); err != nil {
		s.logger.Error("Failed to close file watcher", zap.Error(err))
	}
	s.cache.Close()
	s.wg.Wait()
}

// processCertificate processes a single certificate file
func (s *Scanner) processCertificate(path string) (*CertificateInfo, error) {
	// Validate file path to prevent directory traversal (gosec G304 fix)
	if !s.isPathAllowed(path) {
		return nil, fmt.Errorf("path not allowed: %s", path)
	}

	// Check cache first
	if cached := s.cache.Get(path); cached != nil {
		if certInfo, ok := cached.(*CertificateInfo); ok {
			return certInfo, nil
		}
	}

	// Read certificate file using secure method (gosec G304 fix)
	data, err := s.readCertificateFileSecurely(path)
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

	// Check for deprecated signature algorithms (exhaustive fix)
	isDeprecatedAlg := false
	switch cert.SignatureAlgorithm {
	case x509.MD5WithRSA, x509.SHA1WithRSA, x509.DSAWithSHA1, x509.ECDSAWithSHA1,
		x509.MD2WithRSA: // Added missing deprecated algorithms
		isDeprecatedAlg = true
	case x509.UnknownSignatureAlgorithm,
		x509.SHA256WithRSA, x509.SHA384WithRSA, x509.SHA512WithRSA,
		x509.DSAWithSHA256,
		x509.ECDSAWithSHA256, x509.ECDSAWithSHA384, x509.ECDSAWithSHA512,
		x509.SHA256WithRSAPSS, x509.SHA384WithRSAPSS, x509.SHA512WithRSAPSS,
		x509.PureEd25519:
		// Modern algorithms - not deprecated
		isDeprecatedAlg = false
	default:
		// Unknown algorithm - treat as not deprecated
		isDeprecatedAlg = false
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

// classifyIssuer classifies certificate issuer
// Refactored to reduce cyclomatic complexity (gocyclo fix)
func (s *Scanner) classifyIssuer(issuer string) int {
	lowerIssuer := strings.ToLower(issuer)

	// Use classification functions to reduce complexity
	if s.isSelfSignedIssuer(lowerIssuer) {
		return 33 // Self-signed
	}

	if s.isDigiCertFamily(lowerIssuer) {
		return 30 // DigiCert
	}

	if s.isAmazonIssuer(lowerIssuer) {
		return 31 // Amazon
	}

	if s.isOtherKnownCA(lowerIssuer) {
		return 32 // Other
	}

	if s.isInternalCA(lowerIssuer) {
		return 33 // Self-signed (internal CAs treated as self-signed)
	}

	// Default for unknown issuers
	return 32 // Other
}

// Helper functions for issuer classification to reduce complexity

// isSelfSignedIssuer checks if the issuer appears to be self-signed
func (s *Scanner) isSelfSignedIssuer(lowerIssuer string) bool {
	return strings.Contains(lowerIssuer, "self-signed") ||
		strings.Contains(lowerIssuer, "self signed") ||
		(strings.Contains(lowerIssuer, "cn=") &&
			(strings.Contains(lowerIssuer, "localhost") ||
				strings.Contains(lowerIssuer, "example.com") ||
				strings.Contains(lowerIssuer, "test")))
}

// isDigiCertFamily checks if the issuer is part of the DigiCert family
func (s *Scanner) isDigiCertFamily(lowerIssuer string) bool {
	digiCertKeywords := []string{
		"digicert", "rapidssl", "geotrust", "thawte", "verisign", "symantec",
	}

	for _, keyword := range digiCertKeywords {
		if strings.Contains(lowerIssuer, keyword) {
			return true
		}
	}
	return false
}

// isAmazonIssuer checks if the issuer is Amazon/AWS related
func (s *Scanner) isAmazonIssuer(lowerIssuer string) bool {
	amazonKeywords := []string{"amazon", "aws", "acm"}

	for _, keyword := range amazonKeywords {
		if strings.Contains(lowerIssuer, keyword) {
			return true
		}
	}
	return false
}

// isOtherKnownCA checks if the issuer is another well-known CA
func (s *Scanner) isOtherKnownCA(lowerIssuer string) bool {
	otherCAKeywords := []string{
		"let's encrypt", "letsencrypt", "isrg", "comodo", "sectigo",
		"godaddy", "globalsign", "entrust", "trustwave", "ssl.com",
		"certigna", "buypass", "zerossl",
	}

	for _, keyword := range otherCAKeywords {
		if strings.Contains(lowerIssuer, keyword) {
			return true
		}
	}
	return false
}

// isInternalCA checks if the issuer is an internal/enterprise CA
func (s *Scanner) isInternalCA(lowerIssuer string) bool {
	internalKeywords := []string{"internal", "enterprise", "corporate", "private"}

	for _, keyword := range internalKeywords {
		if strings.Contains(lowerIssuer, keyword) {
			return true
		}
	}
	return false
}

// isCertificateFile checks if a file is likely a certificate (excluding private keys)
func (s *Scanner) isCertificateFile(path string) bool {
	ext := strings.ToLower(filepath.Ext(path))
	basename := strings.ToLower(filepath.Base(path))

	// FIRST: Exclude private key files by extension
	privateKeyExts := []string{".key", ".pem.key", ".private", ".priv"}
	for _, keyExt := range privateKeyExts {
		if ext == keyExt {
			s.logger.Debug("Excluding private key file by extension", zap.String("path", path), zap.String("extension", ext))
			return false
		}
	}

	// SECOND: Exclude private key files by name patterns
	if strings.Contains(basename, "private") ||
		strings.Contains(basename, ".key") ||
		strings.Contains(basename, "_key") ||
		strings.Contains(basename, "-key") ||
		strings.HasSuffix(basename, "key.pem") {
		s.logger.Debug("Excluding private key file by name pattern", zap.String("path", path), zap.String("basename", basename))
		return false
	}

	// THIRD: Check for certificate extensions
	certExts := []string{".pem", ".crt", ".cer", ".cert", ".der", ".p7b", ".p7c", ".pfx", ".p12"}
	for _, certExt := range certExts {
		if ext == certExt {
			s.logger.Debug("Including certificate file by extension", zap.String("path", path), zap.String("extension", ext))
			return true
		}
	}

	// FOURTH: Check filename patterns for certificates
	certPatterns := []string{"cert", "certificate", "chain", "bundle", "ca-cert", "cacert"}
	for _, pattern := range certPatterns {
		if strings.Contains(basename, pattern) {
			s.logger.Debug("Including certificate file by name pattern", zap.String("path", path), zap.String("pattern", pattern))
			return true
		}
	}

	s.logger.Debug("File does not match certificate patterns", zap.String("path", path))
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

// Security helper functions to prevent path traversal attacks

// isPathAllowed validates that the path is within configured certificate directories
func (s *Scanner) isPathAllowed(path string) bool {
	cleanPath := filepath.Clean(path)

	for _, dir := range s.config.CertificateDirectories {
		cleanDir := filepath.Clean(dir)

		// Check if path is within the allowed directory
		rel, err := filepath.Rel(cleanDir, cleanPath)
		if err != nil {
			continue
		}

		// Check for path traversal - path should not start with ".." or be absolute
		if !strings.HasPrefix(rel, "..") && !filepath.IsAbs(rel) {
			return true
		}
	}

	return false
}

// readCertificateFileSecurely reads a certificate file with security validation
func (s *Scanner) readCertificateFileSecurely(path string) ([]byte, error) {
	// Double-check path validation
	if !s.isPathAllowed(path) {
		return nil, fmt.Errorf("path not within allowed directories: %s", path)
	}

	// Check file size to prevent reading extremely large files
	fileInfo, err := os.Stat(path)
	if err != nil {
		return nil, fmt.Errorf("failed to stat file: %w", err)
	}

	// Limit certificate file size to 1MB (certificates are typically much smaller)
	const maxCertSize = 1024 * 1024 // 1MB
	if fileInfo.Size() > maxCertSize {
		return nil, fmt.Errorf("certificate file too large: %d bytes", fileInfo.Size())
	}

	// Additional security check - ensure file is a regular file
	if !fileInfo.Mode().IsRegular() {
		return nil, fmt.Errorf("not a regular file: %s", path)
	}

	// Use secure file reading
	// gosec G304: This is intentional file reading with validated path within allowed directories
	return os.ReadFile(path) // #nosec G304
}
