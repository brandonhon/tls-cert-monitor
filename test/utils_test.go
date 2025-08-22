package test

import (
	"crypto/rand"
	"crypto/rsa"
	"crypto/x509"
	"crypto/x509/pkix"
	"encoding/pem"
	"math/big"
	"os"
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
