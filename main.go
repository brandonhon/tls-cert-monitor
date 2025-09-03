// Package main is the entry point for the TLS Certificate Monitor application.
// It initializes all components, handles configuration, and manages the lifecycle
// of the monitoring service.
package main

import (
	"context"
	"flag"
	"fmt"
	"os"
	"os/signal"
	"syscall"
	"time"

	"github.com/brandonhon/tls-cert-monitor/internal/config"
	"github.com/brandonhon/tls-cert-monitor/internal/health"
	"github.com/brandonhon/tls-cert-monitor/internal/logger"
	"github.com/brandonhon/tls-cert-monitor/internal/metrics"
	"github.com/brandonhon/tls-cert-monitor/internal/scanner"
	"github.com/brandonhon/tls-cert-monitor/internal/server"
	"go.uber.org/zap"
)

var (
	version   = "dev"
	buildTime = "unknown"
	gitCommit = "unknown"
)

func main() {
	var (
		configFile  = flag.String("config", "", "Path to configuration file")
		showVersion = flag.Bool("version", false, "Show version information")
		dryRun      = flag.Bool("dry-run", false, "Run in dry-run mode (validate config only)")
	)
	flag.Parse()

	if *showVersion {
		fmt.Printf("TLS Certificate Monitor\nVersion: %s\nBuild Time: %s\nGit Commit: %s\n",
			version, buildTime, gitCommit)
		return // Fixed gocritic exitAfterDefer - use return instead of os.Exit
	}

	// Initialize configuration
	cfg, err := config.Load(*configFile)
	if err != nil {
		fmt.Fprintf(os.Stderr, "Failed to load configuration: %v\n", err)
		os.Exit(1)
	}

	// Initialize logger
	log, err := logger.New(cfg.LogFile, cfg.LogLevel)
	if err != nil {
		fmt.Fprintf(os.Stderr, "Failed to initialize logger: %v\n", err)
		os.Exit(1)
	}
	// Store sync error for later handling and handle stdout/stderr sync gracefully
	defer func() {
		if err := syncLogger(log, cfg.LogFile); err != nil {
			// Only log to stderr if it's a real error, not stdout/stderr sync issues
			fmt.Fprintf(os.Stderr, "Failed to sync logger: %v\n", err)
		}
	}()

	// Dry run mode - validate and exit (exitAfterDefer fix - moved outside defer)
	if *dryRun || cfg.DryRun {
		log.Info("Dry run mode - configuration validated successfully")
		// Sync logs before exit
		if err := syncLogger(log, cfg.LogFile); err != nil {
			fmt.Fprintf(os.Stderr, "Failed to sync logger: %v\n", err)
		}
		return // Fixed gocritic exitAfterDefer - use return instead of os.Exit
	}

	// Create context for graceful shutdown
	ctx, cancel := context.WithCancel(context.Background())
	defer cancel()

	// Initialize metrics collector
	metricsCollector := metrics.NewCollector()

	// Initialize health checker
	healthChecker := health.New(cfg, metricsCollector)

	// Initialize certificate scanner - handle error without os.Exit to avoid exitAfterDefer
	certScanner, err := scanner.New(cfg, metricsCollector, log)
	if err != nil {
		log.Error("Failed to initialize certificate scanner", zap.Error(err))
		return // Fixed gocritic exitAfterDefer - use return instead of os.Exit
	}

	// Start initial scan
	log.Info("Starting initial certificate scan")
	if err := certScanner.Scan(ctx); err != nil {
		log.Error("Initial scan failed", zap.Error(err))
	}

	// Start configuration watcher for hot reload
	configWatcher := config.NewWatcher(cfg, *configFile, log)
	go func() {
		// Handle Watch error (errcheck fix)
		if err := configWatcher.Watch(ctx, func(newCfg *config.Config) {
			log.Info("Configuration changed, reloading...")

			// Update scanner with new config
			if err := certScanner.UpdateConfig(newCfg); err != nil {
				log.Error("Failed to update scanner configuration", zap.Error(err))
				return
			}

			// Trigger rescan
			if err := certScanner.Scan(ctx); err != nil {
				log.Error("Rescan after config change failed", zap.Error(err))
			}

			// Update health checker
			healthChecker.UpdateConfig(newCfg)
		}); err != nil {
			log.Error("Configuration watcher error", zap.Error(err))
		}
	}()

	// Start certificate file watcher
	go certScanner.WatchFiles(ctx)

	// Start periodic scanning
	go func() {
		ticker := time.NewTicker(cfg.ScanInterval)
		defer ticker.Stop()

		for {
			select {
			case <-ctx.Done():
				return
			case <-ticker.C:
				log.Debug("Running periodic certificate scan")
				if err := certScanner.Scan(ctx); err != nil {
					log.Error("Periodic scan failed", zap.Error(err))
				}
			}
		}
	}()

	// Initialize and start HTTP server
	srv := server.New(cfg, metricsCollector, healthChecker, log)

	// Start server in goroutine
	serverErrors := make(chan error, 1)
	go func() {
		log.Info("Starting HTTP server",
			zap.String("address", cfg.BindAddress),
			zap.Int("port", cfg.Port),
			zap.Bool("tls", cfg.TLSCert != "" && cfg.TLSKey != ""))
		serverErrors <- srv.Start()
	}()

	// Setup signal handling for graceful shutdown
	sigChan := make(chan os.Signal, 1)
	signal.Notify(sigChan, syscall.SIGINT, syscall.SIGTERM)

	// Wait for shutdown signal or server error
	select {
	case sig := <-sigChan:
		log.Info("Received shutdown signal", zap.String("signal", sig.String()))
	case err := <-serverErrors:
		log.Error("Server error", zap.Error(err))
	}

	// Graceful shutdown
	log.Info("Starting graceful shutdown...")

	// Cancel context to stop all goroutines
	cancel()

	// Shutdown server with timeout
	shutdownCtx, shutdownCancel := context.WithTimeout(context.Background(), 30*time.Second)
	defer shutdownCancel()

	if err := srv.Shutdown(shutdownCtx); err != nil {
		log.Error("Server shutdown error", zap.Error(err))
	}

	// Final cleanup
	certScanner.Close()

	log.Info("Shutdown complete")
}

// syncLogger safely syncs the logger, handling stdout/stderr sync issues gracefully
func syncLogger(log *zap.Logger, logFile string) error {
	err := log.Sync()
	if err != nil {
		// Check if this is the common stdout/stderr sync error that can be safely ignored
		if isStdoutSyncError(err, logFile) {
			// This is expected when logging to stdout/stderr - not a real error
			return nil
		}
		// This is a real sync error for file-based logging
		return err
	}
	return nil
}

// isStdoutSyncError checks if the sync error is the harmless stdout/stderr sync issue
func isStdoutSyncError(err error, logFile string) bool {
	// If no log file is specified, we're logging to stdout
	if logFile == "" {
		// Check for the specific error messages related to stdout/stderr sync
		errStr := err.Error()
		return errStr == "sync /dev/stdout: invalid argument" ||
			errStr == "sync /dev/stderr: invalid argument" ||
			errStr == "sync /dev/stdout: inappropriate ioctl for device" ||
			errStr == "sync /dev/stderr: inappropriate ioctl for device"
	}
	return false
}
