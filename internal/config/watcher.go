package config

import (
	"context"
	"path/filepath"
	"sync"
	"time"

	"github.com/fsnotify/fsnotify"
	"go.uber.org/zap"
)

// ReloadCallback is called when configuration changes
type ReloadCallback func(*Config)

// Watcher watches for configuration changes
type Watcher struct {
	config     *Config
	configFile string
	logger     *zap.Logger
	mu         sync.RWMutex
}

// NewWatcher creates a new configuration watcher
func NewWatcher(cfg *Config, configFile string, logger *zap.Logger) *Watcher {
	return &Watcher{
		config:     cfg,
		configFile: configFile,
		logger:     logger,
	}
}

// Watch starts watching for configuration changes
func (w *Watcher) Watch(ctx context.Context, callback ReloadCallback) error {
	if !w.config.HotReload || w.configFile == "" {
		w.logger.Info("Hot reload disabled or no config file specified")
		return nil
	}

	watcher, err := fsnotify.NewWatcher()
	if err != nil {
		return err
	}
	defer watcher.Close()

	// Watch the config file's directory
	configDir := filepath.Dir(w.configFile)
	if err := watcher.Add(configDir); err != nil {
		return err
	}

	w.logger.Info("Watching for configuration changes", zap.String("file", w.configFile))

	// Debounce timer to avoid multiple reloads
	var debounceTimer *time.Timer
	debounce := 500 * time.Millisecond

	for {
		select {
		case <-ctx.Done():
			if debounceTimer != nil {
				debounceTimer.Stop()
			}
			return ctx.Err()

		case event, ok := <-watcher.Events:
			if !ok {
				return nil
			}

			// Check if the event is for our config file
			if filepath.Clean(event.Name) != filepath.Clean(w.configFile) {
				continue
			}

			// Handle write and create events
			if event.Op&fsnotify.Write == fsnotify.Write || event.Op&fsnotify.Create == fsnotify.Create {
				// Cancel previous timer if exists
				if debounceTimer != nil {
					debounceTimer.Stop()
				}

				// Set new timer
				debounceTimer = time.AfterFunc(debounce, func() {
					w.handleConfigChange(callback)
				})
			}

		case err, ok := <-watcher.Errors:
			if !ok {
				return nil
			}
			w.logger.Error("Configuration watcher error", zap.Error(err))
		}
	}
}

// handleConfigChange handles configuration file changes
func (w *Watcher) handleConfigChange(callback ReloadCallback) {
	w.logger.Info("Configuration file changed, reloading...")

	// Load new configuration
	newConfig, err := Load(w.configFile)
	if err != nil {
		w.logger.Error("Failed to reload configuration", zap.Error(err))
		return
	}

	// Update configuration
	w.mu.Lock()
	w.config = newConfig
	w.mu.Unlock()

	// Call the callback with new configuration
	if callback != nil {
		callback(newConfig)
	}

	w.logger.Info("Configuration reloaded successfully")
}

// GetConfig returns the current configuration
func (w *Watcher) GetConfig() *Config {
	w.mu.RLock()
	defer w.mu.RUnlock()
	return w.config
}