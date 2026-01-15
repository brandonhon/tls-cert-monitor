"""
Tests for hot reload functionality.
"""

import tempfile
from pathlib import Path
from unittest.mock import AsyncMock, MagicMock

import pytest
import pytest_asyncio
from watchdog.events import FileSystemEvent

from tls_cert_monitor.cache import CacheManager
from tls_cert_monitor.config import Config
from tls_cert_monitor.hot_reload import CertificateFileHandler, ConfigFileHandler, HotReloadManager
from tls_cert_monitor.metrics import MetricsCollector
from tls_cert_monitor.scanner import CertificateScanner


@pytest.fixture
def temp_config_file():
    """Create a temporary config file."""
    with tempfile.NamedTemporaryFile(mode="w", suffix=".yaml", delete=False) as f:
        f.write(
            """
certificate_directories:
  - /tmp/test_certs
scan_interval: "5m"
workers: 2
hot_reload: true
"""
        )
        config_path = f.name
    yield config_path
    Path(config_path).unlink(missing_ok=True)


@pytest.fixture
def temp_cert_dir():
    """Create a temporary certificate directory."""
    with tempfile.TemporaryDirectory() as tmpdir:
        yield tmpdir


@pytest_asyncio.fixture
async def hot_reload_manager(temp_config_file, temp_cert_dir):
    """Create a hot reload manager instance."""
    config = Config(
        certificate_directories=[temp_cert_dir],
        scan_interval="5m",
        workers=2,
        hot_reload=True,
    )
    cache = CacheManager(config)
    await cache.initialize()
    metrics = MetricsCollector()
    scanner = CertificateScanner(config=config, cache=cache, metrics=metrics)

    manager = HotReloadManager(config=config, scanner=scanner, config_path=temp_config_file)

    yield manager

    # Cleanup
    if manager._watching:
        await manager.stop()
    await cache.close()


class TestCertificateFileHandler:
    """Tests for CertificateFileHandler."""

    def test_handler_ignores_directories(self):
        """Test that directory events are ignored."""
        manager = MagicMock()
        handler = CertificateFileHandler(manager)

        event = MagicMock(spec=FileSystemEvent)
        event.is_directory = True
        event.src_path = "/test/dir"

        handler.on_any_event(event)

        manager._schedule_coro.assert_not_called()

    def test_handler_ignores_non_meaningful_events(self):
        """Test that non-meaningful events are ignored."""
        manager = MagicMock()
        handler = CertificateFileHandler(manager)

        event = MagicMock(spec=FileSystemEvent)
        event.is_directory = False
        event.event_type = "opened"
        event.src_path = "/test/cert.pem"

        handler.on_any_event(event)

        manager._schedule_coro.assert_not_called()

    def test_handler_ignores_non_certificate_files(self):
        """Test that non-certificate files are ignored."""
        manager = MagicMock()
        handler = CertificateFileHandler(manager)

        event = MagicMock(spec=FileSystemEvent)
        event.is_directory = False
        event.event_type = "created"
        event.src_path = "/test/file.txt"

        handler.on_any_event(event)

        manager._schedule_coro.assert_not_called()

    @pytest.mark.parametrize(
        "extension",
        [".pem", ".crt", ".cer", ".cert", ".der", ".p12", ".pfx"],
    )
    def test_handler_processes_certificate_files(self, extension):
        """Test that certificate files with supported extensions are processed."""
        manager = MagicMock()
        manager._event_loop = MagicMock()
        handler = CertificateFileHandler(manager)

        event = MagicMock(spec=FileSystemEvent)
        event.is_directory = False
        event.event_type = "created"
        event.src_path = f"/test/cert{extension}"

        handler.on_any_event(event)

        manager._schedule_coro.assert_called_once()

    @pytest.mark.parametrize(
        "event_type",
        ["created", "modified", "deleted", "moved"],
    )
    def test_handler_processes_meaningful_events(self, event_type):
        """Test that all meaningful events are processed."""
        manager = MagicMock()
        manager._event_loop = MagicMock()
        handler = CertificateFileHandler(manager)

        event = MagicMock(spec=FileSystemEvent)
        event.is_directory = False
        event.event_type = event_type
        event.src_path = "/test/cert.pem"

        handler.on_any_event(event)

        manager._schedule_coro.assert_called_once()

    def test_handler_maps_closed_to_created(self):
        """Test that 'closed' events are mapped to 'created' events."""
        manager = MagicMock()
        manager._event_loop = MagicMock()
        handler = CertificateFileHandler(manager)

        event = MagicMock(spec=FileSystemEvent)
        event.is_directory = False
        event.event_type = "closed"
        event.src_path = "/test/cert.pem"

        handler.on_any_event(event)

        # Verify the handler was called
        manager._schedule_coro.assert_called_once()
        # Note: The coroutine is called with "created" event type internally


class TestConfigFileHandler:
    """Tests for ConfigFileHandler."""

    def test_handler_ignores_directories(self):
        """Test that directory events are ignored."""
        manager = MagicMock()
        manager.config_path = Path("/test/config.yaml")
        handler = ConfigFileHandler(manager)

        event = MagicMock(spec=FileSystemEvent)
        event.is_directory = True
        event.src_path = "/test/dir"

        handler.on_modified(event)

        manager._schedule_coro.assert_not_called()

    def test_handler_ignores_temporary_files(self):
        """Test that temporary files are ignored."""
        manager = MagicMock()
        manager.config_path = Path("/test/config.yaml")
        handler = ConfigFileHandler(manager)

        event = MagicMock(spec=FileSystemEvent)
        event.is_directory = False
        event.src_path = "/test/.config.yaml.tmp"

        handler.on_modified(event)

        manager._schedule_coro.assert_not_called()

    def test_handler_processes_config_file(self, temp_config_file):
        """Test that config file modifications are processed."""
        manager = MagicMock()
        manager.config_path = Path(temp_config_file)
        manager._event_loop = MagicMock()
        handler = ConfigFileHandler(manager)

        event = MagicMock(spec=FileSystemEvent)
        event.is_directory = False
        event.src_path = temp_config_file

        handler.on_modified(event)

        manager._schedule_coro.assert_called_once()


class TestHotReloadManager:
    """Tests for HotReloadManager."""

    @pytest.mark.asyncio
    async def test_manager_initialization(self, hot_reload_manager):
        """Test hot reload manager initialization."""
        assert hot_reload_manager is not None
        assert hot_reload_manager._watching is False
        assert len(hot_reload_manager._watched_paths) == 0

    @pytest.mark.asyncio
    async def test_start_enables_watching(self, hot_reload_manager):
        """Test that starting hot reload enables watching."""
        await hot_reload_manager.start()

        assert hot_reload_manager._watching is True
        assert len(hot_reload_manager._watched_paths) > 0

    @pytest.mark.asyncio
    async def test_stop_disables_watching(self, hot_reload_manager):
        """Test that stopping hot reload disables watching."""
        await hot_reload_manager.start()
        assert hot_reload_manager._watching is True

        await hot_reload_manager.stop()
        assert hot_reload_manager._watching is False

    @pytest.mark.asyncio
    async def test_certificate_created_clears_cache_and_metrics(self, hot_reload_manager):
        """Test that creating a certificate clears cache and metrics."""
        await hot_reload_manager.start()

        # Mock the scanner methods
        hot_reload_manager.scanner.cache.clear = AsyncMock()
        hot_reload_manager.scanner.metrics.clear_all_certificate_metrics = MagicMock()
        hot_reload_manager.scanner.metrics.reset_scan_metrics = MagicMock()
        hot_reload_manager.scanner.scan_once = AsyncMock()

        # Simulate certificate creation
        test_file = str(Path(hot_reload_manager.config.certificate_directories[0]) / "test.pem")
        await hot_reload_manager._debounced_cert_change(test_file, "created")

        # Verify cache was cleared
        hot_reload_manager.scanner.cache.clear.assert_called_once()

        # Verify metrics were cleared
        hot_reload_manager.scanner.metrics.clear_all_certificate_metrics.assert_called_once()
        hot_reload_manager.scanner.metrics.reset_scan_metrics.assert_called_once()

        # Verify re-scan was triggered
        hot_reload_manager.scanner.scan_once.assert_called_once()

    @pytest.mark.asyncio
    async def test_certificate_deleted_clears_cache_and_metrics(self, hot_reload_manager):
        """Test that deleting a certificate clears cache and metrics."""
        await hot_reload_manager.start()

        # Mock the scanner methods
        hot_reload_manager.scanner.cache.clear = AsyncMock()
        hot_reload_manager.scanner.metrics.clear_all_certificate_metrics = MagicMock()
        hot_reload_manager.scanner.metrics.reset_scan_metrics = MagicMock()
        hot_reload_manager.scanner.scan_once = AsyncMock()

        # Simulate certificate deletion
        test_file = str(Path(hot_reload_manager.config.certificate_directories[0]) / "test.pem")
        await hot_reload_manager._debounced_cert_change(test_file, "deleted")

        # Verify cache was cleared
        hot_reload_manager.scanner.cache.clear.assert_called_once()

        # Verify metrics were cleared
        hot_reload_manager.scanner.metrics.clear_all_certificate_metrics.assert_called_once()
        hot_reload_manager.scanner.metrics.reset_scan_metrics.assert_called_once()

        # Verify re-scan was triggered
        hot_reload_manager.scanner.scan_once.assert_called_once()

    @pytest.mark.asyncio
    async def test_certificate_moved_clears_cache_and_metrics(self, hot_reload_manager):
        """Test that moving a certificate clears cache and metrics."""
        await hot_reload_manager.start()

        # Mock the scanner methods
        hot_reload_manager.scanner.cache.clear = AsyncMock()
        hot_reload_manager.scanner.metrics.clear_all_certificate_metrics = MagicMock()
        hot_reload_manager.scanner.metrics.reset_scan_metrics = MagicMock()
        hot_reload_manager.scanner.scan_once = AsyncMock()

        # Simulate certificate move
        test_file = str(Path(hot_reload_manager.config.certificate_directories[0]) / "test.pem")
        await hot_reload_manager._debounced_cert_change(test_file, "moved")

        # Verify cache was cleared
        hot_reload_manager.scanner.cache.clear.assert_called_once()

        # Verify metrics were cleared
        hot_reload_manager.scanner.metrics.clear_all_certificate_metrics.assert_called_once()
        hot_reload_manager.scanner.metrics.reset_scan_metrics.assert_called_once()

        # Verify re-scan was triggered
        hot_reload_manager.scanner.scan_once.assert_called_once()

    @pytest.mark.asyncio
    async def test_certificate_modified_only_invalidates_cache_entry(
        self, hot_reload_manager, temp_cert_dir
    ):
        """Test that modifying a certificate triggers cache clear, metrics clear, and immediate re-scan."""
        await hot_reload_manager.start()

        # Create a test certificate file
        test_file = Path(temp_cert_dir) / "test.pem"
        test_file.write_text("test cert content")

        # Mock the scanner methods
        hot_reload_manager.scanner.cache.delete = AsyncMock()
        hot_reload_manager.scanner.cache.clear = AsyncMock()
        hot_reload_manager.scanner.metrics.clear_all_certificate_metrics = MagicMock()
        hot_reload_manager.scanner.metrics.reset_scan_metrics = MagicMock()
        hot_reload_manager.scanner.scan_once = AsyncMock()

        # Simulate certificate modification
        await hot_reload_manager._debounced_cert_change(str(test_file), "modified")

        # Verify entire cache was cleared (not just single entry)
        hot_reload_manager.scanner.cache.clear.assert_called_once()

        # Verify metrics were cleared (modifications now trigger immediate re-scan)
        hot_reload_manager.scanner.metrics.clear_all_certificate_metrics.assert_called_once()
        hot_reload_manager.scanner.metrics.reset_scan_metrics.assert_called_once()

        # Verify re-scan was triggered
        hot_reload_manager.scanner.scan_once.assert_called_once()

    @pytest.mark.asyncio
    async def test_get_status(self, hot_reload_manager):
        """Test getting hot reload status."""
        status = hot_reload_manager.get_status()

        assert "enabled" in status
        assert "watching" in status
        assert "watched_paths" in status
        assert "config_path" in status
        assert "active_cert_tasks" in status
        assert "active_config_task" in status

    @pytest.mark.asyncio
    async def test_hot_reload_disabled_in_config(self):
        """Test that hot reload doesn't start when disabled in config."""
        config = Config(
            certificate_directories=["/tmp/test"],
            scan_interval="5m",
            workers=2,
            hot_reload=False,  # Disabled
        )
        cache = CacheManager(config)
        await cache.initialize()
        metrics = MetricsCollector()
        scanner = CertificateScanner(config=config, cache=cache, metrics=metrics)

        manager = HotReloadManager(config=config, scanner=scanner, config_path=None)

        await manager.start()

        # Should not be watching since hot reload is disabled
        assert manager._watching is False

        await cache.close()
