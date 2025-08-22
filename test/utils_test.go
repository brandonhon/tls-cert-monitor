// test/utils_test.go

package test

import (
	"crypto/rand"
	"crypto/rsa"
	"crypto/x509"
	"crypto/x509/pkix"
	"encoding/pem"
	"math/big"
	"net"
	"os"
	"strconv"
	"strings"
	"testing"
	"time"
)

// generateTestPort generates a random port for testing
func generateTestPort() int {
	// Use crypto/rand for better randomness
	b := make([]byte, 2)
	rand.Read(b)
	port := 18000 + (int(b[0])<<8+int(b[1]))%400
	return port
}

// contains checks if a string contains a substring
func contains(s, substr string) bool {
	return strings.Contains(s, substr)
}

// generateTestCertificate generates a test certificate
func generateTestCertificate(t *testing.T, keySize int, notAfter time.Time) []byte {
	priv, err := rsa.GenerateKey(rand.Reader, keySize)
	if err != nil {
		t.Fatal(err)
	}

	template := x509.Certificate{
		SerialNumber: big.NewInt(1),
		Subject: pkix.Name{
			Organization:  []string{"Test Org"},
			Country:       []string{"US"},
			Province:      []string{""},
			Locality:      []string{"San Francisco"},
			StreetAddress: []string{""},
			PostalCode:    []string{""},
		},
		NotBefore:             time.Now().Add(-24 * time.Hour),
		NotAfter:              notAfter,
		KeyUsage:              x509.KeyUsageKeyEncipherment | x509.KeyUsageDigitalSignature,
		ExtKeyUsage:           []x509.ExtKeyUsage{x509.ExtKeyUsageServerAuth},
		BasicConstraintsValid: true,
		DNSNames:              []string{"test.example.com", "*.example.com"},
		IPAddresses:           nil,
	}

	certDER, err := x509.CreateCertificate(rand.Reader, &template, &template, &priv.PublicKey, priv)
	if err != nil {
		t.Fatal(err)
	}

	certPEM := pem.EncodeToMemory(&pem.Block{
		Type:  "CERTIFICATE",
		Bytes: certDER,
	})

	return certPEM
}

// writeCertToFile writes a certificate to a file
func writeCertToFile(t *testing.T, path string, cert []byte) {
	if err := os.WriteFile(path, cert, 0644); err != nil {
		t.Fatal(err)
	}
}

// generateCertificateWithSANs generates a certificate with specified SANs
func generateCertificateWithSANs(t *testing.T, keySize int, notAfter time.Time, dnsNames []string, ipAddresses []net.IP) []byte {
	priv, err := rsa.GenerateKey(rand.Reader, keySize)
	if err != nil {
		t.Fatal(err)
	}

	template := x509.Certificate{
		SerialNumber: big.NewInt(1),
		Subject: pkix.Name{
			Organization: []string{"Test Org"},
			Country:      []string{"US"},
		},
		NotBefore:             time.Now().Add(-24 * time.Hour),
		NotAfter:              notAfter,
		KeyUsage:              x509.KeyUsageKeyEncipherment | x509.KeyUsageDigitalSignature,
		ExtKeyUsage:           []x509.ExtKeyUsage{x509.ExtKeyUsageServerAuth},
		BasicConstraintsValid: true,
		DNSNames:              dnsNames,
		IPAddresses:           ipAddresses,
	}

	certDER, err := x509.CreateCertificate(rand.Reader, &template, &template, &priv.PublicKey, priv)
	if err != nil {
		t.Fatal(err)
	}

	return pem.EncodeToMemory(&pem.Block{
		Type:  "CERTIFICATE",
		Bytes: certDER,
	})
}

// generateSelfSignedCertificate generates a self-signed certificate
func generateSelfSignedCertificate(t *testing.T, keySize int, notAfter time.Time) []byte {
	priv, err := rsa.GenerateKey(rand.Reader, keySize)
	if err != nil {
		t.Fatal(err)
	}

	template := x509.Certificate{
		SerialNumber: big.NewInt(1),
		Subject: pkix.Name{
			Organization:  []string{"Self-Signed Org"},
			Country:       []string{"US"},
			CommonName:    "self-signed.example.com",
		},
		NotBefore:             time.Now().Add(-24 * time.Hour),
		NotAfter:              notAfter,
		KeyUsage:              x509.KeyUsageKeyEncipherment | x509.KeyUsageDigitalSignature,
		ExtKeyUsage:           []x509.ExtKeyUsage{x509.ExtKeyUsageServerAuth},
		BasicConstraintsValid: true,
		IsCA:                  true,
		DNSNames:              []string{"self-signed.example.com"},
	}

	certDER, err := x509.CreateCertificate(rand.Reader, &template, &template, &priv.PublicKey, priv)
	if err != nil {
		t.Fatal(err)
	}

	return pem.EncodeToMemory(&pem.Block{
		Type:  "CERTIFICATE",
		Bytes: certDER,
	})
}

// createExpiredCertificate creates an expired certificate
func createExpiredCertificate(t *testing.T, keySize int) []byte {
	expiredTime := time.Now().Add(-30 * 24 * time.Hour) // 30 days ago
	return generateTestCertificate(t, keySize, expiredTime)
}

// createWeakKeyCertificate creates a certificate with weak key
func createWeakKeyCertificate(t *testing.T) []byte {
	futureTime := time.Now().Add(365 * 24 * time.Hour)
	return generateTestCertificate(t, 1024, futureTime) // 1024-bit is considered weak
}

// createValidCertificate creates a valid certificate
func createValidCertificate(t *testing.T) []byte {
	futureTime := time.Now().Add(365 * 24 * time.Hour)
	return generateTestCertificate(t, 2048, futureTime)
}

// createMultiSANCertificate creates a certificate with multiple SANs
func createMultiSANCertificate(t *testing.T) []byte {
	futureTime := time.Now().Add(365 * 24 * time.Hour)
	dnsNames := []string{"www.example.com", "api.example.com", "admin.example.com"}
	ipAddresses := []net.IP{net.ParseIP("192.168.1.1"), net.ParseIP("10.0.0.1")}
	return generateCertificateWithSANs(t, 2048, futureTime, dnsNames, ipAddresses)
}

// CertificateTestSet represents a set of test certificates with known properties
type CertificateTestSet struct {
	ValidCert      []byte
	WeakKeyCert    []byte
	ExpiredCert    []byte
	MultiSANCert   []byte
	SelfSignedCert []byte
	DuplicateCert  []byte // Same as ValidCert
}

// createCertificateTestSet creates a comprehensive set of test certificates
func createCertificateTestSet(t *testing.T) *CertificateTestSet {
	validCert := createValidCertificate(t)
	
	return &CertificateTestSet{
		ValidCert:      validCert,
		WeakKeyCert:    createWeakKeyCertificate(t),
		ExpiredCert:    createExpiredCertificate(t, 2048),
		MultiSANCert:   createMultiSANCertificate(t),
		SelfSignedCert: generateSelfSignedCertificate(t, 2048, time.Now().Add(365*24*time.Hour)),
		DuplicateCert:  validCert, // Same content as ValidCert
	}
}

// MetricValue represents a parsed Prometheus metric
type MetricValue struct {
	Name   string
	Labels map[string]string
	Value  float64
}

// parsePrometheusMetrics parses Prometheus metrics format and extracts metric values
// FIXED VERSION: Better handling of complex labels and scientific notation
func parsePrometheusMetrics(content string) []MetricValue {
	var metrics []MetricValue
	lines := strings.Split(content, "\n")
	
	for _, line := range lines {
		line = strings.TrimSpace(line)
		
		// Skip comments and empty lines
		if line == "" || strings.HasPrefix(line, "#") {
			continue
		}
		
		// Find the metric name and value
		// Handle both cases: metric_name{labels} value and metric_name value
		var metricName string
		var labelsStr string
		var valueStr string
		
		if strings.Contains(line, "{") {
			// Has labels: metric_name{labels} value
			openBrace := strings.Index(line, "{")
			metricName = line[:openBrace]
			
			// Find the closing brace by counting braces (handles nested quotes)
			braceCount := 0
			closeBrace := -1
			inQuotes := false
			var escapeNext bool
			
			for i := openBrace; i < len(line); i++ {
				char := line[i]
				if escapeNext {
					escapeNext = false
					continue
				}
				if char == '\\' {
					escapeNext = true
					continue
				}
				if char == '"' {
					inQuotes = !inQuotes
					continue
				}
				if !inQuotes {
					if char == '{' {
						braceCount++
					} else if char == '}' {
						braceCount--
						if braceCount == 0 {
							closeBrace = i
							break
						}
					}
				}
			}
			
			if closeBrace == -1 {
				continue // Malformed line
			}
			
			labelsStr = line[openBrace+1 : closeBrace]
			remainingLine := strings.TrimSpace(line[closeBrace+1:])
			
			// Extract value (everything after the closing brace)
			fields := strings.Fields(remainingLine)
			if len(fields) > 0 {
				valueStr = fields[0]
			}
		} else {
			// No labels: metric_name value
			fields := strings.Fields(line)
			if len(fields) >= 2 {
				metricName = fields[0]
				valueStr = fields[1]
			}
		}
		
		if metricName == "" || valueStr == "" {
			continue
		}
		
		// Parse value (handle scientific notation)
		value, err := strconv.ParseFloat(valueStr, 64)
		if err != nil {
			continue
		}
		
		// Parse labels
		labels := make(map[string]string)
		if labelsStr != "" {
			labels = parseLabels(labelsStr)
		}
		
		metrics = append(metrics, MetricValue{
			Name:   metricName,
			Labels: labels,
			Value:  value,
		})
	}
	
	return metrics
}

// parseLabels parses the label string inside braces
func parseLabels(labelsStr string) map[string]string {
	labels := make(map[string]string)
	
	// Split by commas, but respect quoted values
	var parts []string
	var current strings.Builder
	inQuotes := false
	var escapeNext bool
	
	for _, char := range labelsStr {
		if escapeNext {
			current.WriteRune(char)
			escapeNext = false
			continue
		}
		
		if char == '\\' {
			escapeNext = true
			current.WriteRune(char)
			continue
		}
		
		if char == '"' {
			inQuotes = !inQuotes
			current.WriteRune(char)
			continue
		}
		
		if char == ',' && !inQuotes {
			parts = append(parts, current.String())
			current.Reset()
			continue
		}
		
		current.WriteRune(char)
	}
	
	// Add the last part
	if current.Len() > 0 {
		parts = append(parts, current.String())
	}
	
	// Parse each part as key="value"
	for _, part := range parts {
		part = strings.TrimSpace(part)
		if part == "" {
			continue
		}
		
		eqIndex := strings.Index(part, "=")
		if eqIndex == -1 {
			continue
		}
		
		key := strings.TrimSpace(part[:eqIndex])
		valueWithQuotes := strings.TrimSpace(part[eqIndex+1:])
		
		// Remove surrounding quotes
		value := valueWithQuotes
		if len(value) >= 2 && value[0] == '"' && value[len(value)-1] == '"' {
			value = value[1 : len(value)-1]
			// Unescape quotes
			value = strings.ReplaceAll(value, `\"`, `"`)
			value = strings.ReplaceAll(value, `\\`, `\`)
		}
		
		labels[key] = value
	}
	
	return labels
}

// verifyMetricExists checks if a metric with the given name exists
func verifyMetricExists(t *testing.T, metrics []MetricValue, metricName string) {
	for _, metric := range metrics {
		if metric.Name == metricName {
			return
		}
	}
	t.Errorf("Metric %s not found in metrics output", metricName)
}

// verifyMetricValue checks if a metric has the expected value
func verifyMetricValue(t *testing.T, metrics []MetricValue, metricName string, expectedValue float64) {
	for _, metric := range metrics {
		if metric.Name == metricName && len(metric.Labels) == 0 {
			if metric.Value != expectedValue {
				t.Errorf("Metric %s: expected value %f, got %f", metricName, expectedValue, metric.Value)
			}
			return
		}
	}
	t.Errorf("Metric %s not found or has unexpected labels", metricName)
}

// verifyMetricWithLabels checks if a metric with specific labels exists
func verifyMetricWithLabels(t *testing.T, metrics []MetricValue, metricName string, expectedLabels map[string]string) {
	for _, metric := range metrics {
		if metric.Name == metricName {
			// Check if all expected labels match
			allMatch := true
			for key, expectedValue := range expectedLabels {
				if value, exists := metric.Labels[key]; !exists || value != expectedValue {
					allMatch = false
					break
				}
			}
			if allMatch {
				return
			}
		}
	}
	t.Errorf("Metric %s with labels %v not found", metricName, expectedLabels)
}

// getMetricCount returns the count of metrics with the given name
func getMetricCount(metrics []MetricValue, metricName string) int {
	count := 0
	for _, metric := range metrics {
		if metric.Name == metricName {
			count++
		}
	}
	return count
}

// createCertificateWithIssuer creates a certificate with a custom issuer string
func createCertificateWithIssuer(t *testing.T, issuerStr string) []byte {
	// Create two key pairs - one for issuer, one for subject
	privIssuer, err := rsa.GenerateKey(rand.Reader, 2048)
	if err != nil {
		t.Fatal(err)
	}
	
	privSubject, err := rsa.GenerateKey(rand.Reader, 2048)
	if err != nil {
		t.Fatal(err)
	}

	// Parse the issuer string into a pkix.Name
	issuer := parseDN(issuerStr)
	
	// Create subject (different from issuer)
	subject := pkix.Name{
		CommonName:   "test-subject.example.com",
		Organization: []string{"Test Subject Org"},
		Country:      []string{"US"},
	}

	// Create issuer certificate template
	issuerTemplate := x509.Certificate{
		SerialNumber: big.NewInt(1),
		Subject:      issuer,
		Issuer:       issuer, // Self-signed issuer
		NotBefore:    time.Now().Add(-48 * time.Hour),
		NotAfter:     time.Now().Add(2 * 365 * 24 * time.Hour),
		KeyUsage:     x509.KeyUsageCertSign | x509.KeyUsageDigitalSignature,
		ExtKeyUsage:  []x509.ExtKeyUsage{x509.ExtKeyUsageServerAuth},
		BasicConstraintsValid: true,
		IsCA: true,
	}

	// Create the issuer certificate (self-signed)
	issuerCertDER, err := x509.CreateCertificate(rand.Reader, &issuerTemplate, &issuerTemplate, &privIssuer.PublicKey, privIssuer)
	if err != nil {
		t.Fatal(err)
	}
	
	// Parse the issuer certificate
	issuerCert, err := x509.ParseCertificate(issuerCertDER)
	if err != nil {
		t.Fatal(err)
	}

	// Create subject certificate template
	subjectTemplate := x509.Certificate{
		SerialNumber: big.NewInt(2),
		Subject:      subject,
		Issuer:       issuer, // This will be the custom issuer we want
		NotBefore:    time.Now().Add(-24 * time.Hour),
		NotAfter:     time.Now().Add(365 * 24 * time.Hour),
		KeyUsage:     x509.KeyUsageKeyEncipherment | x509.KeyUsageDigitalSignature,
		ExtKeyUsage:  []x509.ExtKeyUsage{x509.ExtKeyUsageServerAuth},
		BasicConstraintsValid: true,
		DNSNames:     []string{"test-subject.example.com"},
	}

	// Create the subject certificate signed by the issuer
	subjectCertDER, err := x509.CreateCertificate(rand.Reader, &subjectTemplate, issuerCert, &privSubject.PublicKey, privIssuer)
	if err != nil {
		t.Fatal(err)
	}

	return pem.EncodeToMemory(&pem.Block{
		Type:  "CERTIFICATE",
		Bytes: subjectCertDER,
	})
}

// parseDN parses a distinguished name string into pkix.Name
func parseDN(dn string) pkix.Name {
	name := pkix.Name{}
	
	// Split by commas and parse each component
	parts := strings.Split(dn, ",")
	for _, part := range parts {
		part = strings.TrimSpace(part)
		if part == "" {
			continue
		}
		
		// Split by = to get key and value
		kvParts := strings.SplitN(part, "=", 2)
		if len(kvParts) != 2 {
			continue
		}
		
		key := strings.TrimSpace(kvParts[0])
		value := strings.TrimSpace(kvParts[1])
		
		switch strings.ToUpper(key) {
		case "CN":
			name.CommonName = value
		case "O":
			name.Organization = append(name.Organization, value)
		case "OU":
			name.OrganizationalUnit = append(name.OrganizationalUnit, value)
		case "C":
			name.Country = append(name.Country, value)
		case "L":
			name.Locality = append(name.Locality, value)
		case "ST", "S":
			name.Province = append(name.Province, value)
		}
	}
	
	return name
}