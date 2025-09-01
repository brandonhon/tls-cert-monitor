// Package logger provides structured logging functionality for the TLS Certificate Monitor.
// It uses zap for high-performance, structured logging with support for multiple output
// destinations and configurable log levels.
package logger

import (
	"fmt"
	"os"
	"path/filepath"
	"strings"

	"go.uber.org/zap"
	"go.uber.org/zap/zapcore"
)

// New creates a new logger instance with the specified configuration
func New(logFile, logLevel string) (*zap.Logger, error) {
	// Parse log level
	level, err := parseLogLevel(logLevel)
	if err != nil {
		return nil, err
	}

	// Create encoder config
	encoderConfig := zap.NewProductionEncoderConfig()
	encoderConfig.TimeKey = "timestamp"
	encoderConfig.EncodeTime = zapcore.ISO8601TimeEncoder
	encoderConfig.EncodeLevel = zapcore.CapitalLevelEncoder

	// Create encoder
	encoder := zapcore.NewJSONEncoder(encoderConfig)

	// Create writer
	var writer zapcore.WriteSyncer
	if logFile == "" {
		// Log to stdout if no file specified
		writer = zapcore.AddSync(os.Stdout)
	} else {
		// Ensure log directory exists
		logDir := filepath.Dir(logFile)
		// Use 0750 for better security (gosec G301 fix)
		if err := os.MkdirAll(logDir, 0750); err != nil {
			return nil, fmt.Errorf("failed to create log directory: %w", err)
		}

		// Validate log file path to prevent directory traversal (gosec G304 fix)
		if !isValidLogFile(logFile) {
			return nil, fmt.Errorf("invalid log file path: %s", logFile)
		}

		// Open log file with restricted permissions using secure method (gosec G304 fix)
		file, err := openLogFileSecurely(logFile)
		if err != nil {
			return nil, fmt.Errorf("failed to open log file: %w", err)
		}

		// Use both file and stdout
		writer = zapcore.NewMultiWriteSyncer(
			zapcore.AddSync(file),
			zapcore.AddSync(os.Stdout),
		)
	}

	// Create core
	core := zapcore.NewCore(encoder, writer, level)

	// Create logger with caller information
	logger := zap.New(core, zap.AddCaller(), zap.AddStacktrace(zapcore.ErrorLevel))

	return logger, nil
}

// parseLogLevel parses string log level to zapcore.Level
func parseLogLevel(level string) (zapcore.Level, error) {
	switch strings.ToLower(level) {
	case "debug":
		return zapcore.DebugLevel, nil
	case "info":
		return zapcore.InfoLevel, nil
	case "warn", "warning":
		return zapcore.WarnLevel, nil
	case "error":
		return zapcore.ErrorLevel, nil
	default:
		return zapcore.InfoLevel, fmt.Errorf("invalid log level: %s", level)
	}
}

// NewNop creates a no-op logger for testing
func NewNop() *zap.Logger {
	return zap.NewNop()
}

// Security helper functions to prevent path traversal attacks

// isValidLogFile validates that the log file path is safe and doesn't contain
// directory traversal attempts or suspicious characters
func isValidLogFile(filePath string) bool {
	// Clean the path to resolve any ".." components
	cleanPath := filepath.Clean(filePath)

	// Check for absolute path (should be allowed for log files)
	if !filepath.IsAbs(cleanPath) {
		// For relative paths, ensure they don't try to escape current directory
		if strings.Contains(cleanPath, "..") {
			return false
		}
	}

	// Ensure the file extension is appropriate for log files
	ext := strings.ToLower(filepath.Ext(cleanPath))
	validExtensions := map[string]bool{
		".log": true,
		".txt": true,
		".out": true,
		"":     true, // Allow files without extension
	}

	if !validExtensions[ext] {
		return false
	}

	// Check for suspicious characters or patterns - Fixed staticcheck S1008
	base := filepath.Base(cleanPath)
	return !strings.ContainsAny(base, "<>:\"|?*")
}

// openLogFileSecurely opens a log file with proper security measures
func openLogFileSecurely(filePath string) (*os.File, error) {
	// Additional validation - ensure log files are not created in restricted system directories
	absPath, err := filepath.Abs(filePath)
	if err != nil {
		return nil, fmt.Errorf("failed to resolve absolute path: %w", err)
	}

	// Block log files in system directories
	restrictedPaths := []string{
		"/etc", "/usr/bin", "/usr/sbin", "/bin", "/sbin", "/boot", "/dev", "/proc", "/sys",
	}

	for _, restricted := range restrictedPaths {
		if strings.HasPrefix(absPath, restricted+string(filepath.Separator)) {
			return nil, fmt.Errorf("cannot create log files in restricted directory: %s", restricted)
		}
	}

	// Open log file with restricted permissions (gosec G302 fix - use 0600 instead of wider permissions)
	// #nosec G304 -- This is intentional log file creation with validated path
	file, err := os.OpenFile(filePath, os.O_CREATE|os.O_APPEND|os.O_WRONLY, 0600)
	if err != nil {
		return nil, fmt.Errorf("failed to open log file securely: %w", err)
	}
	return file, nil
}
