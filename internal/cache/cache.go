package cache

import (
	"encoding/gob"
	"fmt"
	"os"
	"path/filepath"
	"sync"
	"sync/atomic"
	"time"
)

// Entry represents a cache entry
type Entry struct {
	Key        string
	Value      interface{}
	Expiration time.Time
	Size       int64
}

// Cache provides a thread-safe in-memory cache with disk persistence
type Cache struct {
	entries     map[string]*Entry
	mu          sync.RWMutex
	dir         string
	ttl         time.Duration
	maxSize     int64
	currentSize int64
	hits        atomic.Uint64
	misses      atomic.Uint64
	evictions   atomic.Uint64
	stopChan    chan struct{}
	wg          sync.WaitGroup
}

// New creates a new cache instance
func New(dir string, ttl time.Duration, maxSize int64) (*Cache, error) {
	// Create cache directory if it doesn't exist
	if dir != "" {
		if err := os.MkdirAll(dir, 0755); err != nil {
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

	f, err := os.Create(tempFile)
	if err != nil {
		return fmt.Errorf("failed to create cache file: %w", err)
	}
	defer f.Close()

	encoder := gob.NewEncoder(f)
	if err := encoder.Encode(entries); err != nil {
		os.Remove(tempFile)
		return fmt.Errorf("failed to encode cache: %w", err)
	}

	if err := f.Sync(); err != nil {
		os.Remove(tempFile)
		return fmt.Errorf("failed to sync cache file: %w", err)
	}

	// Atomic rename
	if err := os.Rename(tempFile, file); err != nil {
		os.Remove(tempFile)
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
	f, err := os.Open(file)
	if err != nil {
		if os.IsNotExist(err) {
			return nil // No cache file yet
		}
		return fmt.Errorf("failed to open cache file: %w", err)
	}
	defer f.Close()

	var entries map[string]*Entry
	decoder := gob.NewDecoder(f)
	if err := decoder.Decode(&entries); err != nil {
		return fmt.Errorf("failed to decode cache: %w", err)
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
	c.save()
}
