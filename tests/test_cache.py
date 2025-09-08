"""
Tests for cache management.
"""

import asyncio
import tempfile
from pathlib import Path

import pytest

from tls_cert_monitor.cache import CacheEntry, CacheManager
from tls_cert_monitor.config import Config


class TestCacheEntry:
    """Test cache entry functionality."""

    def test_cache_entry_creation(self):
        """Test cache entry creation."""
        entry = CacheEntry(value={"test": "data"}, timestamp=1000.0, ttl=300, size=100)

        assert entry.value == {"test": "data"}
        assert entry.timestamp == 1000.0
        assert entry.ttl == 300
        assert entry.size == 100
        assert entry.access_count == 0

    def test_cache_entry_expiration(self):
        """Test cache entry expiration check."""
        import time

        current_time = time.time()

        # Not expired
        entry = CacheEntry(
            value="test",
            timestamp=current_time - 100,  # 100 seconds ago
            ttl=300,  # 5 minutes TTL
            size=10,
        )
        assert not entry.is_expired()

        # Expired
        entry = CacheEntry(
            value="test",
            timestamp=current_time - 400,  # 400 seconds ago
            ttl=300,  # 5 minutes TTL
            size=10,
        )
        assert entry.is_expired()

    def test_access_tracking(self):
        """Test access count tracking."""
        entry = CacheEntry(value="test", timestamp=1000.0, ttl=300, size=10)

        assert entry.access_count == 0
        assert entry.last_access == 0.0

        entry.update_access()

        assert entry.access_count == 1
        assert entry.last_access > 0


@pytest.mark.asyncio
class TestCacheManager:
    """Test cache manager functionality."""

    async def test_cache_manager_initialization(self):
        """Test cache manager initialization."""
        with tempfile.TemporaryDirectory() as temp_dir:
            config = Config(cache_dir=temp_dir)
            cache = CacheManager(config)

            await cache.initialize()

            assert cache.cache_dir.exists()
            assert cache.ttl == config.cache_ttl_seconds

            await cache.close()

    async def test_cache_set_get(self):
        """Test basic cache set and get operations."""
        with tempfile.TemporaryDirectory() as temp_dir:
            config = Config(cache_dir=temp_dir)
            cache = CacheManager(config)
            await cache.initialize()

            # Set value
            await cache.set("test_key", {"data": "test_value"})

            # Get value
            result = await cache.get("test_key")
            assert result == {"data": "test_value"}

            await cache.close()

    async def test_cache_expiration(self):
        """Test cache expiration."""
        with tempfile.TemporaryDirectory() as temp_dir:
            config = Config(cache_dir=temp_dir, cache_ttl="1s")
            cache = CacheManager(config)
            await cache.initialize()

            # Set value with short TTL
            await cache.set("test_key", "test_value", ttl=1)

            # Should exist immediately
            result = await cache.get("test_key")
            assert result == "test_value"

            # Wait for expiration
            await asyncio.sleep(2)

            # Should be expired
            result = await cache.get("test_key")
            assert result is None

            await cache.close()

    async def test_cache_delete(self):
        """Test cache deletion."""
        with tempfile.TemporaryDirectory() as temp_dir:
            config = Config(cache_dir=temp_dir)
            cache = CacheManager(config)
            await cache.initialize()

            # Set and verify
            await cache.set("test_key", "test_value")
            assert await cache.get("test_key") == "test_value"

            # Delete
            deleted = await cache.delete("test_key")
            assert deleted is True

            # Should be gone
            assert await cache.get("test_key") is None

            # Delete non-existent key
            deleted = await cache.delete("non_existent")
            assert deleted is False

            await cache.close()

    async def test_cache_clear(self):
        """Test cache clear operation."""
        with tempfile.TemporaryDirectory() as temp_dir:
            config = Config(cache_dir=temp_dir)
            cache = CacheManager(config)
            await cache.initialize()

            # Set multiple values
            await cache.set("key1", "value1")
            await cache.set("key2", "value2")
            await cache.set("key3", "value3")

            # Clear cache
            await cache.clear()

            # All should be gone
            assert await cache.get("key1") is None
            assert await cache.get("key2") is None
            assert await cache.get("key3") is None

            await cache.close()

    async def test_cache_stats(self):
        """Test cache statistics."""
        with tempfile.TemporaryDirectory() as temp_dir:
            config = Config(cache_dir=temp_dir)
            cache = CacheManager(config)
            await cache.initialize()

            # Initial stats
            stats = await cache.get_stats()
            assert stats["entries_total"] == 0
            assert stats["hit_rate"] == 0.0

            # Add some entries and access them
            await cache.set("key1", "value1")
            await cache.set("key2", "value2")

            # Hit
            await cache.get("key1")
            # Miss
            await cache.get("key3")

            stats = await cache.get_stats()
            assert stats["entries_total"] == 2
            assert stats["total_accesses"] == 2
            assert stats["cache_hits"] == 1
            assert stats["cache_misses"] == 1
            assert stats["hit_rate"] == 0.5

            await cache.close()

    async def test_cache_cleanup_expired(self):
        """Test cleanup of expired entries."""
        with tempfile.TemporaryDirectory() as temp_dir:
            config = Config(cache_dir=temp_dir)
            cache = CacheManager(config)
            await cache.initialize()

            # Set entries with different TTLs
            await cache.set("short_ttl", "value1", ttl=1)
            await cache.set("long_ttl", "value2", ttl=300)

            # Wait for short TTL to expire
            await asyncio.sleep(2)

            # Cleanup
            expired_count = await cache.cleanup_expired()
            assert expired_count == 1

            # Check remaining entries
            assert await cache.get("short_ttl") is None
            assert await cache.get("long_ttl") == "value2"

            await cache.close()

    async def test_make_key(self):
        """Test cache key generation."""
        with tempfile.TemporaryDirectory() as temp_dir:
            config = Config(cache_dir=temp_dir)
            cache = CacheManager(config)

            key1 = cache.make_key("arg1", "arg2", 123)
            key2 = cache.make_key("arg1", "arg2", 123)
            key3 = cache.make_key("arg1", "arg2", 456)

            # Same arguments should produce same key
            assert key1 == key2

            # Different arguments should produce different key
            assert key1 != key3

            # Key should be reasonable length
            assert len(key1) == 16  # Truncated SHA256

    async def test_cache_size_limits(self):
        """Test cache size limit enforcement."""
        with tempfile.TemporaryDirectory() as temp_dir:
            config = Config(cache_dir=temp_dir, cache_max_size=1000)  # 1KB limit
            cache = CacheManager(config)
            await cache.initialize()

            # Add large entries that exceed the limit
            large_data = "x" * 400  # 400 bytes each

            await cache.set("key1", large_data)
            await cache.set("key2", large_data)
            await cache.set("key3", large_data)  # Should trigger eviction

            stats = await cache.get_stats()
            assert stats["current_size_bytes"] <= config.cache_max_size

            await cache.close()

    async def test_health_status(self):
        """Test cache health status."""
        with tempfile.TemporaryDirectory() as temp_dir:
            config = Config(cache_dir=temp_dir)
            cache = CacheManager(config)
            await cache.initialize()

            # Add some data
            await cache.set("test_key", "test_value")
            await cache.get("test_key")  # Create a hit

            health = await cache.get_health_status()

            assert "cache_entries_total" in health
            assert "cache_file_path" in health
            assert "cache_file_writable" in health
            assert "cache_hit_rate" in health
            assert "cache_total_accesses" in health

            assert health["cache_entries_total"] == 1
            assert health["cache_total_accesses"] == 1

            await cache.close()
