package server

import (
	"context"
	"crypto/tls"
	"encoding/json"
	"fmt"
	"net/http"
	"time"

	"github.com/brandonhon/tls-cert-monitor/internal/config"
	"github.com/brandonhon/tls-cert-monitor/internal/health"
	"github.com/brandonhon/tls-cert-monitor/internal/metrics"
	"github.com/prometheus/client_golang/prometheus"
	"github.com/prometheus/client_golang/prometheus/promhttp"
	"go.uber.org/zap"
)

// Server represents the HTTP server
type Server struct {
	config   *config.Config
	metrics  *metrics.Collector
	health   *health.Checker
	logger   *zap.Logger
	server   *http.Server
	registry *prometheus.Registry
}

// New creates a new HTTP server
func New(cfg *config.Config, metrics *metrics.Collector, health *health.Checker, logger *zap.Logger) *Server {
	return &Server{
		config:   cfg,
		metrics:  metrics,
		health:   health,
		logger:   logger,
		registry: nil, // Will use default prometheus.Handler()
	}
}

// NewWithRegistry creates a new HTTP server with a custom registry
func NewWithRegistry(cfg *config.Config, metrics *metrics.Collector, health *health.Checker, logger *zap.Logger, registry *prometheus.Registry) *Server {
	return &Server{
		config:   cfg,
		metrics:  metrics,
		health:   health,
		logger:   logger,
		registry: registry,
	}
}

// Start starts the HTTP server
func (s *Server) Start() error {
	mux := http.NewServeMux()

	// Health check endpoint
	mux.HandleFunc("/healthz", s.handleHealth)

	// Metrics endpoint - use HandlerFor with the custom registry if provided
	if s.registry != nil {
		mux.Handle("/metrics", promhttp.HandlerFor(
			s.registry,
			promhttp.HandlerOpts{
				ErrorHandling: promhttp.ContinueOnError,
			},
		))
	} else {
		mux.Handle("/metrics", promhttp.Handler())
	}

	// Root endpoint
	mux.HandleFunc("/", s.handleRoot)

	// Create server
	s.server = &http.Server{
		Addr:         fmt.Sprintf("%s:%d", s.config.BindAddress, s.config.Port),
		Handler:      s.loggingMiddleware(mux),
		ReadTimeout:  30 * time.Second,
		WriteTimeout: 30 * time.Second,
		IdleTimeout:  60 * time.Second,
	}

	// Configure TLS if certificates are provided
	if s.config.TLSCert != "" && s.config.TLSKey != "" {
		tlsConfig := &tls.Config{
			MinVersion:               tls.VersionTLS12,
			CurvePreferences:         []tls.CurveID{tls.CurveP521, tls.CurveP384, tls.CurveP256},
			PreferServerCipherSuites: true,
			CipherSuites: []uint16{
				tls.TLS_ECDHE_RSA_WITH_AES_256_GCM_SHA384,
				tls.TLS_ECDHE_RSA_WITH_AES_256_CBC_SHA,
				tls.TLS_RSA_WITH_AES_256_GCM_SHA384,
				tls.TLS_RSA_WITH_AES_256_CBC_SHA,
			},
		}

		s.server.TLSConfig = tlsConfig
		return s.server.ListenAndServeTLS(s.config.TLSCert, s.config.TLSKey)
	}

	return s.server.ListenAndServe()
}

// Shutdown gracefully shuts down the server
func (s *Server) Shutdown(ctx context.Context) error {
	if s.server == nil {
		return nil
	}
	return s.server.Shutdown(ctx)
}

// loggingMiddleware logs HTTP requests
func (s *Server) loggingMiddleware(next http.Handler) http.Handler {
	return http.HandlerFunc(func(w http.ResponseWriter, r *http.Request) {
		start := time.Now()

		// Create response writer wrapper to capture status code
		wrapped := &responseWriter{
			ResponseWriter: w,
			statusCode:     200,
		}

		// Process request
		next.ServeHTTP(wrapped, r)

		// Log request
		s.logger.Info("HTTP request",
			zap.String("method", r.Method),
			zap.String("path", r.URL.Path),
			zap.String("remote_addr", r.RemoteAddr),
			zap.Int("status", wrapped.statusCode),
			zap.Duration("duration", time.Since(start)),
		)
	})
}

// responseWriter wraps http.ResponseWriter to capture status code
type responseWriter struct {
	http.ResponseWriter
	statusCode int
}

func (rw *responseWriter) WriteHeader(code int) {
	rw.statusCode = code
	rw.ResponseWriter.WriteHeader(code)
}

// handleRoot handles the root endpoint
func (s *Server) handleRoot(w http.ResponseWriter, r *http.Request) {
	if r.URL.Path != "/" {
		http.NotFound(w, r)
		return
	}

	w.Header().Set("Content-Type", "text/html; charset=utf-8")
	fmt.Fprintf(w, `<!DOCTYPE html>
<html>
<head>
    <title>TLS Certificate Monitor</title>
    <style>
        body {
            font-family: -apple-system, BlinkMacSystemFont, "Segoe UI", Roboto, "Helvetica Neue", Arial, sans-serif;
            max-width: 800px;
            margin: 50px auto;
            padding: 20px;
            background: #f5f5f5;
        }
        h1 {
            color: #333;
            border-bottom: 2px solid #4CAF50;
            padding-bottom: 10px;
        }
        .endpoints {
            background: white;
            border-radius: 8px;
            padding: 20px;
            box-shadow: 0 2px 4px rgba(0,0,0,0.1);
        }
        .endpoint {
            margin: 15px 0;
            padding: 10px;
            background: #f9f9f9;
            border-left: 4px solid #4CAF50;
        }
        a {
            color: #4CAF50;
            text-decoration: none;
        }
        a:hover {
            text-decoration: underline;
        }
        code {
            background: #e8e8e8;
            padding: 2px 6px;
            border-radius: 3px;
            font-family: "Courier New", monospace;
        }
    </style>
</head>
<body>
    <h1>🔒 TLS Certificate Monitor</h1>
    <div class="endpoints">
        <h2>Available Endpoints</h2>
        <div class="endpoint">
            <strong><a href="/metrics">/metrics</a></strong><br>
            Prometheus metrics endpoint for certificate monitoring
        </div>
        <div class="endpoint">
            <strong><a href="/healthz">/healthz</a></strong><br>
            Health check endpoint with detailed system status
        </div>
        <h2>Configuration</h2>
        <div class="endpoint">
            <strong>Port:</strong> <code>%d</code><br>
            <strong>TLS Enabled:</strong> <code>%v</code><br>
            <strong>Workers:</strong> <code>%d</code><br>
            <strong>Scan Interval:</strong> <code>%v</code><br>
            <strong>Monitored Directories:</strong> <code>%v</code>
        </div>
    </div>
</body>
</html>`,
		s.config.Port,
		s.config.TLSCert != "" && s.config.TLSKey != "",
		s.config.Workers,
		s.config.ScanInterval,
		s.config.CertificateDirectories,
	)
}

// handleHealth handles the health check endpoint
func (s *Server) handleHealth(w http.ResponseWriter, r *http.Request) {
	response := s.health.Check()

	// Set status code based on health
	statusCode := http.StatusOK
	switch response.Status {
	case health.StatusDegraded:
		statusCode = http.StatusOK // Still return 200 for degraded
	case health.StatusUnhealthy:
		statusCode = http.StatusServiceUnavailable
	}

	// Send response
	w.Header().Set("Content-Type", "application/json")
	w.WriteHeader(statusCode)

	if err := json.NewEncoder(w).Encode(response); err != nil {
		s.logger.Error("Failed to encode health response", zap.Error(err))
	}
}
