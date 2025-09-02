// Package cache provides a thread-safe in-memory cache with disk persistence
// for the TLS Certificate Monitor. It includes TTL support, size limits,
// and automatic cleanup of expired entries.
package cache

import (
	"encoding/gob"
	"fmt"
	"os"
	"path/filepath"
	"strings"
	"sync"
	"sync/atomic"
	"time"
)

// Entry represents a cache entry with metadata
// Field order optimized for memory alignment (fieldalignment fix)
type Entry struct {
	Value      interface{} // 16 bytes (interface)
	Expiration time.Time   // 24 bytes
	Key        string      // 16 bytes
	Size       int64       // 8 bytes
}

// Cache provides a thread-safe in-memory cache with disk persistence
// Field order optimized for memory alignment (fieldalignment fix)
type Cache struct {
	currentSize int64             // 8 bytes (atomic access, must be first for alignment)
	maxSize     int64             // 8 bytes
	ttl         time.Duration     // 8 bytes
	hits        atomic.Uint64     // 8 bytes
	misses      atomic.Uint64     // 8 bytes
	evictions   atomic.Uint64     // 8 bytes
	entries     map[string]*Entry // 8 bytes (pointer)
	stopChan    chan struct{}     // 8 bytes (pointer)
	dir         string            // 16 bytes
	mu          sync.RWMutex      // 24 bytes
	wg          sync.WaitGroup    // 12 bytes (but padded to 16)
}

// New creates a new cache instance
func New(dir string, ttl time.Duration, maxSize int64) (*Cache, error) {
	// Create cache directory if it doesn't exist
	if dir != "" {
		// Use 0750 for better security (gosec G301 fix)
		if err := os.MkdirAll(dir, 0750); err != nil {
			return nil, fmt.Errorf("failed to create cache directory: %w", err)
		}
	}

	c := &Cache{
		entries:  make(map[string]*Entry),
		dir:      dir,
		ttl:      ttl,
		maxSize:  maxSize,
		stopChan: make(chan struct{}),
	}

	// Load cache from disk if exists
	if err := c.load(); err != nil {
		// Log error but don't fail - cache will start empty
		fmt.Printf("Failed to load cache from disk: %v\n", err)
	}

	// Start cleanup goroutine
	c.wg.Add(1)
	go c.cleanup()

	return c, nil
}

// Get retrieves a value from the cache
func (c *Cache) Get(key string) interface{} {
	c.mu.RLock()
	entry, exists := c.entries[key]
	c.mu.RUnlock()

	if !exists {
		c.misses.Add(1)
		return nil
	}

	// Check expiration
	if time.Now().After(entry.Expiration) {
		c.mu.Lock()
		delete(c.entries, key)
		c.currentSize -= entry.Size
		c.mu.Unlock()
		c.misses.Add(1)
		return nil
	}

	c.hits.Add(1)
	return entry.Value
}

// Set stores a value in the cache
func (c *Cache) Set(key string, value interface{}) {
	// Estimate size (simplified)
	size := int64(len(key) + 100) // Rough estimate

	entry := &Entry{
		Key:        key,
		Value:      value,
		Expiration: time.Now().Add(c.ttl),
		Size:       size,
	}

	c.mu.Lock()
	defer c.mu.Unlock()

	// Check if we need to evict entries
	for c.currentSize+size > c.maxSize && len(c.entries) > 0 {
		c.evictOldest()
	}

	// Remove old entry if exists
	if oldEntry, exists := c.entries[key]; exists {
		c.currentSize -= oldEntry.Size
	}

	c.entries[key] = entry
	c.currentSize += size
}

// evictOldest removes the oldest entry from cache
func (c *Cache) evictOldest() {
	var oldestKey string
	var oldestTime time.Time

	for key, entry := range c.entries {
		if oldestKey == "" || entry.Expiration.Before(oldestTime) {
			oldestKey = key
			oldestTime = entry.Expiration
		}
	}

	if oldestKey != "" {
		c.currentSize -= c.entries[oldestKey].Size
		delete(c.entries, oldestKey)
		c.evictions.Add(1)
	}
}

// Clear removes all entries from the cache
func (c *Cache) Clear() {
	c.mu.Lock()
	defer c.mu.Unlock()

	c.entries = make(map[string]*Entry)
	c.currentSize = 0
}

// cleanup periodically removes expired entries
func (c *Cache) cleanup() {
	defer c.wg.Done()

	ticker := time.NewTicker(1 * time.Minute)
	defer ticker.Stop()

	for {
		select {
		case <-c.stopChan:
			return
		case <-ticker.C:
			c.removeExpired()
			// Periodically save to disk
			if err := c.save(); err != nil {
				fmt.Printf("Failed to save cache to disk: %v\n", err)
			}
		}
	}
}

// removeExpired removes all expired entries
func (c *Cache) removeExpired() {
	now := time.Now()

	c.mu.Lock()
	defer c.mu.Unlock()

	for key, entry := range c.entries {
		if now.After(entry.Expiration) {
			c.currentSize -= entry.Size
			delete(c.entries, key)
		}
	}
}

// save persists the cache to disk
func (c *Cache) save() error {
	if c.dir == "" {
		return nil
	}

	c.mu.RLock()
	entries := make(map[string]*Entry, len(c.entries))
	for k, v := range c.entries {
		entries[k] = v
	}
	c.mu.RUnlock()

	file := filepath.Join(c.dir, "cache.gob")
	tempFile := file + ".tmp"

	// Validate file paths to prevent directory traversal (gosec G304 fix)
	if !isValidCacheFile(tempFile, c.dir) {
		return fmt.Errorf("invalid cache file path: %s", tempFile)
	}

	// Use secure file creation with proper permissions (gosec G304 fix)
	f, err := createSecureFile(tempFile)
	if err != nil {
		return fmt.Errorf("failed to create cache file: %w", err)
	}
	defer func() {
		// Always close the file (errcheck fix)
		if closeErr := f.Close(); closeErr != nil && err == nil {
			err = fmt.Errorf("failed to close cache file: %w", closeErr)
		}
	}()

	encoder := gob.NewEncoder(f)
	if err := encoder.Encode(entries); err != nil {
		// Clean up temp file on error (errcheck fix)
		if removeErr := os.Remove(tempFile); removeErr != nil {
			// Log but don't override the original error
			fmt.Printf("Failed to remove temp file: %v\n", removeErr)
		}
		// Enhanced error handling for gob encoding issues
		if strings.Contains(err.Error(), "type not registered") {
			fmt.Printf("Warning: Cache contains unregistered types, skipping cache save: %v\n", err)
			return nil // Don't treat this as a fatal error
		}
		return fmt.Errorf("failed to encode cache: %w", err)
	}

	if err := f.Sync(); err != nil {
		// Clean up temp file on error (errcheck fix)
		if removeErr := os.Remove(tempFile); removeErr != nil {
			fmt.Printf("Failed to remove temp file: %v\n", removeErr)
		}
		return fmt.Errorf("failed to sync cache file: %w", err)
	}

	// Atomic rename
	if err := os.Rename(tempFile, file); err != nil {
		// Clean up temp file on error (errcheck fix)
		if removeErr := os.Remove(tempFile); removeErr != nil {
			fmt.Printf("Failed to remove temp file: %v\n", removeErr)
		}
		return fmt.Errorf("failed to rename cache file: %w", err)
	}

	return nil
}

// load restores the cache from disk
func (c *Cache) load() error {
	if c.dir == "" {
		return nil
	}

	file := filepath.Join(c.dir, "cache.gob")

	// Validate file path to prevent directory traversal (gosec G304 fix)
	if !isValidCacheFile(file, c.dir) {
		return fmt.Errorf("invalid cache file path: %s", file)
	}

	// Check if cache file exists before attempting to open
	if _, err := os.Stat(file); os.IsNotExist(err) {
		// Cache file doesn't exist yet - this is normal for first run
		return nil
	}

	// Use secure file opening (gosec G304 fix)
	f, err := openSecureFile(file)
	if err != nil {
		// If we can't open the cache file, it's not critical - start with empty cache
		fmt.Printf("Warning: Failed to load cache from disk (starting with empty cache): %v\n", err)
		return nil // Don't treat as fatal error
	}
	defer func() {
		// Always close the file (errcheck fix)
		if closeErr := f.Close(); closeErr != nil {
			fmt.Printf("Failed to close cache file during load: %v\n", closeErr)
		}
	}()

	var entries map[string]*Entry
	decoder := gob.NewDecoder(f)
	if err := decoder.Decode(&entries); err != nil {
		// If we can't decode the cache file, it might be corrupted - start fresh
		fmt.Printf("Warning: Failed to decode cache file (starting with empty cache): %v\n", err)
		return nil // Don't treat as fatal error
	}

	// Remove expired entries and calculate size
	now := time.Now()
	var totalSize int64

	c.mu.Lock()
	defer c.mu.Unlock()

	for key, entry := range entries {
		if now.Before(entry.Expiration) {
			c.entries[key] = entry
			totalSize += entry.Size
		}
	}

	c.currentSize = totalSize
	return nil
}

// Stats returns cache statistics
func (c *Cache) Stats() map[string]interface{} {
	c.mu.RLock()
	entriesCount := len(c.entries)
	c.mu.RUnlock()

	totalAccesses := c.hits.Load() + c.misses.Load()
	hitRate := float64(0)
	if totalAccesses > 0 {
		hitRate = float64(c.hits.Load()) / float64(totalAccesses)
	}

	return map[string]interface{}{
		"entries":        entriesCount,
		"size":           c.currentSize,
		"max_size":       c.maxSize,
		"hits":           c.hits.Load(),
		"misses":         c.misses.Load(),
		"evictions":      c.evictions.Load(),
		"hit_rate":       hitRate,
		"total_accesses": totalAccesses,
	}
}

// Close shuts down the cache
func (c *Cache) Close() {
	close(c.stopChan)
	c.wg.Wait()
	// Handle save error (errcheck fix)
	if err := c.save(); err != nil {
		fmt.Printf("Failed to save cache on close: %v\n", err)
	}
}

// Security helper functions to prevent path traversal attacks

// isValidCacheFile validates that the file path is within the allowed cache directory
// and contains only safe characters to prevent directory traversal attacks
func isValidCacheFile(filePath, baseDir string) bool {
	// Clean the paths to resolve any ".." components
	cleanFile := filepath.Clean(filePath)
	cleanBase := filepath.Clean(baseDir)

	// Ensure baseDir exists and is a directory
	if info, err := os.Stat(cleanBase); err != nil || !info.IsDir() {
		// If base directory doesn't exist, it's not valid (but don't error - cache will handle)
		return false
	}

	// Check if the file is within the base directory
	rel, err := filepath.Rel(cleanBase, cleanFile)
	if err != nil {
		return false
	}

	// Reject paths that try to escape the base directory
	if rel == ".." || len(rel) >= 3 && rel[:3] == ".."+string(filepath.Separator) {
		return false
	}

	// Ensure the filename is exactly "cache.gob" or "cache.gob.tmp"
	filename := filepath.Base(cleanFile)
	if filename != "cache.gob" && filename != "cache.gob.tmp" {
		return false
	}

	return true
}

// createSecureFile creates a file with secure permissions and validation
func createSecureFile(filePath string) (*os.File, error) {
	// Additional validation - ensure we don't create files in restricted system directories
	absPath, err := filepath.Abs(filePath)
	if err != nil {
		return nil, fmt.Errorf("failed to resolve absolute path: %w", err)
	}

	// Block creation in system directories
	restrictedPaths := []string{
		"/etc", "/usr", "/bin", "/sbin", "/boot", "/dev", "/proc", "/sys",
	}

	for _, restricted := range restrictedPaths {
		if strings.HasPrefix(absPath, restricted+string(filepath.Separator)) {
			return nil, fmt.Errorf("cannot create files in restricted directory: %s", restricted)
		}
	}

	// Create file with restrictive permissions (0600 - owner read/write only)
	// #nosec G304 -- This is intentional file creation with validated path
	file, err := os.OpenFile(filePath, os.O_CREATE|os.O_WRONLY|os.O_TRUNC, 0600)
	if err != nil {
		return nil, fmt.Errorf("failed to create secure file: %w", err)
	}
	return file, nil
}

// openSecureFile opens a file with validation
func openSecureFile(filePath string) (*os.File, error) {
	// Additional validation - ensure we don't open files in restricted system directories
	absPath, err := filepath.Abs(filePath)
	if err != nil {
		return nil, fmt.Errorf("failed to resolve absolute path: %w", err)
	}

	// Block opening files in restricted system directories (except for reading cache files)
	if !strings.Contains(absPath, "cache") {
		restrictedPaths := []string{
			"/etc/shadow", "/etc/passwd", "/proc", "/sys", "/dev",
		}

		for _, restricted := range restrictedPaths {
			if strings.HasPrefix(absPath, restricted) {
				return nil, fmt.Errorf("cannot open restricted file: %s", restricted)
			}
		}
	}

	// Open file for reading only
	// #nosec G304 -- This is intentional file opening with validated path
	file, err := os.OpenFile(filePath, os.O_RDONLY, 0)
	if err != nil {
		return nil, fmt.Errorf("failed to open secure file: %w", err)
	}
	return file, nil
}
