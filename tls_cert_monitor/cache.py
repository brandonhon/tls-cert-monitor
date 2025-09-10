"""
Cache management for TLS Certificate Monitor.
"""

import asyncio
import hashlib
import json
import os
import time
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Any, Dict, Optional

from tls_cert_monitor.config import Config
from tls_cert_monitor.logger import get_logger, log_cache_operation


@dataclass
class CacheEntry:
    """Cache entry with metadata."""

    value: Any
    timestamp: float
    ttl: int
    size: int
    access_count: int = 0
    last_access: float = 0.0

    def is_expired(self) -> bool:
        """Check if cache entry is expired."""
        return time.time() - self.timestamp > self.ttl

    def update_access(self) -> None:
        """Update access statistics."""
        self.access_count += 1
        self.last_access = time.time()


class CacheManager:
    """
    Cache manager for certificate data and scan results.

    Provides both in-memory and persistent caching with LRU eviction.
    """

    def __init__(self, config: Config):
        self.config = config
        self.logger = get_logger("cache")
        self.cache_dir = Path(config.cache_dir)
        self.cache_file = self.cache_dir / "cache.json"
        self.ttl = config.cache_ttl_seconds
        self.max_size = config.cache_max_size

        # In-memory cache
        self._memory_cache: Dict[str, CacheEntry] = {}
        self._current_size = 0
        self._access_count = 0
        self._hit_count = 0

        # Lock for thread safety
        self._lock = asyncio.Lock()

    async def initialize(self) -> None:
        """Initialize cache manager."""
        self.cache_dir.mkdir(parents=True, exist_ok=True)
        await self._load_persistent_cache()
        self.logger.info(f"Cache initialized - TTL: {self.ttl}s, Max size: {self.max_size} bytes")

    async def get(self, key: str) -> Optional[Any]:
        """
        Get value from cache.

        Args:
            key: Cache key

        Returns:
            Cached value or None if not found/expired
        """
        async with self._lock:
            self._access_count += 1

            if key not in self._memory_cache:
                log_cache_operation(self.logger, "miss", key)
                return None

            entry = self._memory_cache[key]

            if entry.is_expired():
                del self._memory_cache[key]
                self._current_size -= entry.size
                log_cache_operation(self.logger, "miss", key)
                return None

            entry.update_access()
            self._hit_count += 1
            log_cache_operation(self.logger, "hit", key)
            return entry.value

    async def set(self, key: str, value: Any, ttl: Optional[int] = None) -> None:
        """
        Set value in cache.

        Args:
            key: Cache key
            value: Value to cache
            ttl: Time to live in seconds (uses default if None)
        """
        async with self._lock:
            entry_ttl = ttl if ttl is not None else self.ttl

            # Calculate size
            try:
                serialized = json.dumps(value, ensure_ascii=False)
                size = len(serialized.encode("utf-8"))
            except (TypeError, ValueError) as e:
                self.logger.warning(f"Failed to serialize value for key {key}: {e}")
                return

            # Check if we need to evict entries
            await self._ensure_space(size)

            # Create cache entry
            entry = CacheEntry(value=value, timestamp=time.time(), ttl=entry_ttl, size=size)

            # Remove old entry if exists
            if key in self._memory_cache:
                old_entry = self._memory_cache[key]
                self._current_size -= old_entry.size

            # Add new entry
            self._memory_cache[key] = entry
            self._current_size += size

            log_cache_operation(self.logger, "set", key)

    async def delete(self, key: str) -> bool:
        """
        Delete key from cache.

        Args:
            key: Cache key

        Returns:
            True if key was deleted, False if not found
        """
        async with self._lock:
            if key in self._memory_cache:
                entry = self._memory_cache[key]
                del self._memory_cache[key]
                self._current_size -= entry.size
                log_cache_operation(self.logger, "invalidate", key)
                return True
            return False

    async def clear(self) -> None:
        """Clear all cache entries."""
        async with self._lock:
            self._memory_cache.clear()
            self._current_size = 0
            self.logger.info("Cache cleared")

    async def get_stats(self) -> Dict[str, Any]:
        """Get cache statistics."""
        async with self._lock:
            hit_rate = (self._hit_count / self._access_count) if self._access_count > 0 else 0.0

            return {
                "entries_total": len(self._memory_cache),
                "current_size_bytes": self._current_size,
                "max_size_bytes": self.max_size,
                "hit_rate": hit_rate,
                "total_accesses": self._access_count,
                "cache_hits": self._hit_count,
                "cache_misses": self._access_count - self._hit_count,
            }

    async def cleanup_expired(self) -> int:
        """
        Remove expired entries from cache.

        Returns:
            Number of entries removed
        """
        async with self._lock:
            expired_keys = []
            current_time = time.time()

            for key, entry in self._memory_cache.items():
                if current_time - entry.timestamp > entry.ttl:
                    expired_keys.append(key)

            for key in expired_keys:
                entry = self._memory_cache[key]
                del self._memory_cache[key]
                self._current_size -= entry.size

            if expired_keys:
                self.logger.info(f"Cleaned up {len(expired_keys)} expired cache entries")

            return len(expired_keys)

    async def save_to_disk(self) -> None:
        """Save cache to disk."""
        try:
            async with self._lock:
                # Convert cache to serializable format
                cache_data = {
                    "entries": {
                        key: asdict(entry)
                        for key, entry in self._memory_cache.items()
                        if not entry.is_expired()
                    },
                    "stats": {
                        "access_count": self._access_count,
                        "hit_count": self._hit_count,
                    },
                }

            # Write to temporary file first, then rename for atomicity
            temp_file = self.cache_file.with_suffix(".tmp")
            with open(temp_file, "w", encoding="utf-8") as f:
                json.dump(cache_data, f, ensure_ascii=False, indent=2)

            temp_file.rename(self.cache_file)
            self.logger.debug("Cache saved to disk")

        except Exception as e:
            self.logger.error(f"Failed to save cache to disk: {e}")

    async def _load_persistent_cache(self) -> None:
        """Load cache from disk."""
        if not self.cache_file.exists():
            return

        try:
            with open(self.cache_file, "r", encoding="utf-8") as f:
                cache_data = json.load(f)

            # Restore cache entries
            for key, entry_data in cache_data.get("entries", {}).items():
                entry = CacheEntry(**entry_data)
                if not entry.is_expired():
                    self._memory_cache[key] = entry
                    self._current_size += entry.size

            # Restore stats
            stats = cache_data.get("stats", {})
            self._access_count = stats.get("access_count", 0)
            self._hit_count = stats.get("hit_count", 0)

            self.logger.info(f"Loaded {len(self._memory_cache)} entries from persistent cache")

        except Exception as e:
            self.logger.warning(f"Failed to load persistent cache: {e}")
            # Remove corrupted cache file
            try:
                self.cache_file.unlink()
                self.logger.info("Removed corrupted cache file")
            except OSError as os_error:
                self.logger.warning(f"Could not remove corrupted cache file: {os_error}")

    async def _ensure_space(self, needed_size: int) -> None:
        """Ensure there's enough space in cache by evicting LRU entries."""
        if self._current_size + needed_size <= self.max_size:
            return

        # Sort entries by last access time (LRU first)
        entries_by_access = sorted(self._memory_cache.items(), key=lambda item: item[1].last_access)

        freed_space = 0
        evicted_count = 0

        for key, entry in entries_by_access:
            if self._current_size + needed_size - freed_space <= self.max_size:
                break

            del self._memory_cache[key]
            freed_space += entry.size
            evicted_count += 1

        self._current_size -= freed_space

        if evicted_count > 0:
            self.logger.info(
                f"Evicted {evicted_count} LRU cache entries to free {freed_space} bytes"
            )

    async def close(self) -> None:
        """Close cache manager and save to disk."""
        await self.save_to_disk()
        self.logger.info("Cache manager closed")

    def make_key(self, *args: Any) -> str:
        """
        Create a cache key from arguments.

        Args:
            *args: Arguments to create key from

        Returns:
            Cache key string
        """
        # Create a hash of the arguments
        key_data = str(args).encode("utf-8")
        return hashlib.sha256(key_data).hexdigest()[:16]

    async def get_health_status(self) -> Dict[str, Any]:
        """Get cache health status."""
        stats = await self.get_stats()

        return {
            "cache_entries_total": stats["entries_total"],
            "cache_file_path": str(self.cache_file),
            "cache_file_writable": os.access(self.cache_dir, os.W_OK)
            if self.cache_dir.exists()
            else False,
            "cache_hit_rate": round(stats["hit_rate"], 3),
            "cache_total_accesses": stats["total_accesses"],
        }


# Background task for cache maintenance
async def cache_maintenance_task(cache_manager: CacheManager, interval: int = 300) -> None:
    """
    Background task for cache maintenance.

    Args:
        cache_manager: Cache manager instance
        interval: Maintenance interval in seconds
    """
    logger = get_logger("cache.maintenance")

    while True:
        try:
            await asyncio.sleep(interval)

            # Clean up expired entries
            expired_count = await cache_manager.cleanup_expired()
            if expired_count > 0:
                logger.debug(f"Cleaned up {expired_count} expired cache entries")

            # Save to disk periodically
            await cache_manager.save_to_disk()

            # Log cache stats
            stats = await cache_manager.get_stats()
            logger.debug(
                f"Cache maintenance: {stats['entries_total']} entries, "
                f"{stats['current_size_bytes']} bytes, "
                f"{stats['hit_rate']:.2%} hit rate"
            )

        except asyncio.CancelledError:
            logger.info("Cache maintenance task cancelled")
            break
        except Exception as e:
            logger.error(f"Cache maintenance error: {e}")
