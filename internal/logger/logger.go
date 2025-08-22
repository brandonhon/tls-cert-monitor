package logger

import (
	"fmt"
	"os"
	"path/filepath"
	"strings"

	"go.uber.org/zap"
	"go.uber.org/zap/zapcore"
)

// New creates a new logger instance
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
		if err := os.MkdirAll(logDir, 0755); err != nil {
			return nil, fmt.Errorf("failed to create log directory: %w", err)
		}

		// Open log file
		file, err := os.OpenFile(logFile, os.O_CREATE|os.O_APPEND|os.O_WRONLY, 0644)
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
