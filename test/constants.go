// ============================================================================
// test/constants.go
// ============================================================================
//go:build integration
// +build integration

// Package test provides testing utilities and constants for the TLS Certificate Monitor.
// This file contains shared constants to avoid goconst linting issues.
package test

// import "os"

const (
	// SSL cert metric names - extracted to fix goconst issue
	metricSSLCertIssuerCode = "ssl_cert_issuer_code"

	// Common file permissions for testing
	testDirPermissions  = 0750 // Secure directory permissions
	testFilePermissions = 0600 // Secure file permissions
)

// Common file mode constants that can be used across test files
const (
	// TestDirPermissions provides secure directory permissions for tests
	TestDirPermissions = testDirPermissions
	// TestFilePermissions provides secure file permissions for tests
	TestFilePermissions = testFilePermissions
	// MetricSSLCertIssuerCode provides the SSL cert issuer code metric name
	MetricSSLCertIssuerCode = metricSSLCertIssuerCode
)
