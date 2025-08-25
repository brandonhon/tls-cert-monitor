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

// Watcher watches for configuration changes.
// Field order is optimized to minimize memory padding.
type Watcher struct {
	config     *Config      // 8 bytes (pointer)
	logger     *zap.Logger  // 8 bytes (pointer)
	configFile string       // 16 bytes (string header)
	mu         sync.RWMutex // 24 bytes
}

// NewWatcher creates a new configuration watcher
func NewWatcher(cfg *Config, configFile string, logger *zap.Logger) *Watcher {
	return &Watcher{
		config:     cfg,
		configFile: configFile,
		logger:     logger,
	}
}

// Watch starts watching for configuration changes.
// This function is refactored to reduce cyclomatic complexity.
func (w *Watcher) Watch(ctx context.Context, callback ReloadCallback) error {
	if !w.shouldWatch() {
		w.logger.Info("Hot reload disabled or no config file specified")
		return nil
	}

	watcher, err := w.setupWatcher()
	if err != nil {
		return err
	}
	defer w.closeWatcher(watcher)

	w.logger.Info("Watching for configuration changes", zap.String("file", w.configFile))

	// Setup debounce timer
	debouncer := &configDebouncer{
		duration: 500 * time.Millisecond,
	}

	for {
		select {
		case <-ctx.Done():
			debouncer.stop()
			return ctx.Err()

		case event, ok := <-watcher.Events:
			if !ok {
				return nil
			}
			w.handleFileEvent(event, debouncer, callback)

		case err, ok := <-watcher.Errors:
			if !ok {
				return nil
			}
			w.logger.Error("Configuration watcher error", zap.Error(err))
		}
	}
}

// shouldWatch determines if watching should be enabled
func (w *Watcher) shouldWatch() bool {
	return w.config.HotReload && w.configFile != ""
}

// setupWatcher creates and configures the file watcher
func (w *Watcher) setupWatcher() (*fsnotify.Watcher, error) {
	watcher, err := fsnotify.NewWatcher()
	if err != nil {
		return nil, err
	}

	// Watch the config file's directory
	configDir := filepath.Dir(w.configFile)
	if err := watcher.Add(configDir); err != nil {
		closeErr := watcher.Close()
		if closeErr != nil {
			w.logger.Warn("Failed to close watcher after setup error", zap.Error(closeErr))
		}
		return nil, err
	}

	return watcher, nil
}

// closeWatcher safely closes the watcher and logs any errors
func (w *Watcher) closeWatcher(watcher *fsnotify.Watcher) {
	if err := watcher.Close(); err != nil {
		w.logger.Error("Failed to close configuration watcher", zap.Error(err))
	}
}

// handleFileEvent processes file change events
func (w *Watcher) handleFileEvent(event fsnotify.Event, debouncer *configDebouncer, callback ReloadCallback) {
	// Check if the event is for our config file
	if filepath.Clean(event.Name) != filepath.Clean(w.configFile) {
		return
	}

	// Handle write and create events
	if event.Op&fsnotify.Write == fsnotify.Write || event.Op&fsnotify.Create == fsnotify.Create {
		debouncer.trigger(func() {
			w.handleConfigChange(callback)
		})
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

// configDebouncer helps debounce configuration reload events
type configDebouncer struct {
	timer    *time.Timer
	duration time.Duration
	mu       sync.Mutex
}

// trigger starts or resets the debounce timer
func (d *configDebouncer) trigger(fn func()) {
	d.mu.Lock()
	defer d.mu.Unlock()

	// Cancel previous timer if exists
	if d.timer != nil {
		d.timer.Stop()
	}

	// Set new timer
	d.timer = time.AfterFunc(d.duration, fn)
}

// stop cancels any pending timer
func (d *configDebouncer) stop() {
	d.mu.Lock()
	defer d.mu.Unlock()

	if d.timer != nil {
		d.timer.Stop()
		d.timer = nil
	}
}
