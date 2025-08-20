package main

import (
	"context"
	"flag"
	"fmt"
	"os"
	"os/signal"
	"syscall"
	"time"

	"github.com/yourusername/tls-cert-monitor/internal/config"
	"github.com/yourusername/tls-cert-monitor/internal/health"
	"github.com/yourusername/tls-cert-monitor/internal/logger"
	"github.com/yourusername/tls-cert-monitor/internal/metrics"
	"github.com/yourusername/tls-cert-monitor/internal/scanner"
	"github.com/yourusername/tls-cert-monitor/internal/server"
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
		os.Exit(0)
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
	defer log.Sync()

	// Dry run mode - validate and exit
	if *dryRun || cfg.DryRun {
		log.Info("Dry run mode - configuration validated successfully")
		os.Exit(0)
	}

	// Create context for graceful shutdown
	ctx, cancel := context.WithCancel(context.Background())
	defer cancel()

	// Initialize metrics collector
	metricsCollector := metrics.NewCollector()
	
	// Initialize health checker
	healthChecker := health.New(cfg, metricsCollector)

	// Initialize certificate scanner
	certScanner, err := scanner.New(cfg, metricsCollector, log)
	if err != nil {
		log.Fatal("Failed to initialize certificate scanner", zap.Error(err))
	}

	// Start initial scan
	log.Info("Starting initial certificate scan")
	if err := certScanner.Scan(ctx); err != nil {
		log.Error("Initial scan failed", zap.Error(err))
	}

	// Start configuration watcher for hot reload
	configWatcher := config.NewWatcher(cfg, *configFile, log)
	go configWatcher.Watch(ctx, func(newCfg *config.Config) {
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
	})

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