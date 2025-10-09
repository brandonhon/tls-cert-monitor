"""
Hot reload functionality for TLS Certificate Monitor.
"""

import asyncio
from pathlib import Path
from typing import Any, Coroutine, Optional, Set

from watchdog.events import FileSystemEvent, FileSystemEventHandler
from watchdog.observers import Observer

from tls_cert_monitor.config import Config, load_config
from tls_cert_monitor.logger import get_logger, log_hot_reload
from tls_cert_monitor.scanner import CertificateScanner


class CertificateFileHandler(FileSystemEventHandler):
    """Handler for certificate file system events."""

    def __init__(self, hot_reload_manager: "HotReloadManager"):
        self.manager = hot_reload_manager
        self.logger = get_logger("hot_reload.certs")

    def on_any_event(self, event: FileSystemEvent) -> None:
        """Handle meaningful file system events only."""
        if event.is_directory:
            return

        # Only respond to meaningful events, ignore file access events
        # Note: "closed" event is included to catch file copies/writes
        meaningful_events = {"created", "modified", "deleted", "moved", "closed"}
        if event.event_type not in meaningful_events:
            return

        file_path = Path(event.src_path)

        # Check if it's a certificate file
        if file_path.suffix.lower() in CertificateScanner.SUPPORTED_EXTENSIONS:
            # Map "closed" events to "created" since they indicate a new file was written
            actual_event_type = "created" if event.event_type == "closed" else event.event_type
            self.logger.debug(
                f"Certificate file event: {event.event_type} -> {actual_event_type} - {file_path}"
            )
            self.manager._schedule_coro(
                self.manager._handle_certificate_change(str(file_path), actual_event_type)
            )


class ConfigFileHandler(FileSystemEventHandler):
    """Handler for configuration file system events."""

    def __init__(self, hot_reload_manager: "HotReloadManager"):
        self.manager = hot_reload_manager
        self.logger = get_logger("hot_reload.config")

    def on_modified(self, event: FileSystemEvent) -> None:
        """Handle configuration file modification."""
        if event.is_directory:
            return

        file_path = Path(event.src_path)

        # Skip temporary files created by editors
        if file_path.name.startswith(".") or ".tmp" in file_path.name:
            return

        # Check if it's the configuration file (handle cases where file might not exist)
        try:
            if (
                self.manager.config_path
                and file_path.exists()
                and file_path.samefile(self.manager.config_path)
            ):
                self.logger.info(f"Configuration file modified: {file_path}")
                self.manager._schedule_coro(self.manager._handle_config_change())
        except (FileNotFoundError, OSError):
            # File might be a temporary file that was quickly deleted
            pass


class HotReloadManager:
    """
    Manager for hot reloading configuration and certificate changes.

    Monitors:
    - Configuration file changes
    - Certificate directory changes
    - Certificate file additions/modifications/deletions
    """

    def __init__(
        self, config: Config, scanner: CertificateScanner, config_path: Optional[str] = None
    ):
        self.config = config
        self.scanner = scanner
        self.config_path = Path(config_path) if config_path else None
        self.logger = get_logger("hot_reload")

        self._observer = Observer()
        self._watching = False
        self._watched_paths: Set[str] = set()
        self._event_loop: Optional[asyncio.AbstractEventLoop] = None

        # Event handlers
        self._cert_handler = CertificateFileHandler(self)
        self._config_handler = ConfigFileHandler(self)

        # Debouncing for rapid file changes
        self._cert_change_tasks: Set[asyncio.Task] = set()
        self._config_change_task: Optional[asyncio.Task] = None

        self.logger.info("Hot reload manager initialized")

    def _schedule_coro(self, coro: Coroutine[Any, Any, Any]) -> None:
        """Schedule a coroutine from a thread safely."""
        if self._event_loop and not self._event_loop.is_closed():
            asyncio.run_coroutine_threadsafe(coro, self._event_loop)
        else:
            self.logger.warning("Cannot schedule coroutine: event loop not available")

    async def start(self) -> None:
        """Start hot reload monitoring."""
        if not self.config.hot_reload:
            self.logger.info("Hot reload disabled in configuration")
            return

        if self._watching:
            self.logger.warning("Hot reload already started")
            return

        # Store the event loop for thread-safe task scheduling
        self._event_loop = asyncio.get_running_loop()

        try:
            # Watch configuration file
            if self.config_path and self.config_path.exists():
                config_dir = self.config_path.parent
                self._observer.schedule(self._config_handler, str(config_dir), recursive=False)
                self._watched_paths.add(str(config_dir))
                self.logger.info(f"Watching configuration file: {self.config_path}")

            # Watch certificate directories
            for cert_dir in self.config.certificate_directories:
                cert_path = Path(cert_dir)
                if cert_path.exists() and cert_path.is_dir():
                    self._observer.schedule(self._cert_handler, str(cert_path), recursive=True)
                    self._watched_paths.add(str(cert_path))
                    self.logger.info(f"Watching certificate directory: {cert_path}")
                else:
                    self.logger.warning(f"Certificate directory does not exist: {cert_dir}")

            # Start observer
            self._observer.start()
            self._watching = True

            self.logger.info(f"Hot reload started - Watching {len(self._watched_paths)} paths")

        except Exception as e:
            self.logger.error(f"Failed to start hot reload: {e}")
            raise

    async def stop(self) -> None:
        """Stop hot reload monitoring."""
        if not self._watching:
            return

        try:
            self._observer.stop()
            self._observer.join(timeout=5.0)

            # Cancel pending tasks
            for task in self._cert_change_tasks:
                task.cancel()

            if self._config_change_task:
                self._config_change_task.cancel()

            self._watching = False
            self._watched_paths.clear()

            self.logger.info("Hot reload stopped")

        except Exception as e:
            self.logger.error(f"Error stopping hot reload: {e}")

    async def _handle_certificate_change(self, file_path: str, event_type: str) -> None:
        """
        Handle certificate file changes with debouncing.

        Args:
            file_path: Path to changed certificate file
            event_type: Type of file system event
        """
        try:
            # Cancel any existing task for this file
            tasks_to_remove = set()
            for task in self._cert_change_tasks:
                if not task.done() and hasattr(task, "_file_path") and task._file_path == file_path:
                    task.cancel()
                    tasks_to_remove.add(task)

            self._cert_change_tasks -= tasks_to_remove

            # Create new debounced task
            task = asyncio.create_task(self._debounced_cert_change(file_path, event_type))
            task._file_path = file_path  # type: ignore[attr-defined] # Store file path for cancellation
            self._cert_change_tasks.add(task)

            # Clean up completed tasks
            self._cert_change_tasks = {t for t in self._cert_change_tasks if not t.done()}

        except Exception as e:
            self.logger.error(f"Error handling certificate change for {file_path}: {e}")

    async def _debounced_cert_change(self, file_path: str, event_type: str) -> None:
        """
        Debounced certificate change handler.

        Args:
            file_path: Path to changed certificate file
            event_type: Type of file system event
        """
        try:
            # Wait for debounce period
            await asyncio.sleep(1.0)

            log_hot_reload(self.logger, file_path, event_type)

            file_path_obj = Path(file_path)

            # Invalidate cache for the changed/deleted/created file
            if hasattr(self.scanner, "cache"):
                # For created, deleted, or moved files, clear entire cache to ensure consistency
                if event_type in ("created", "deleted", "moved") or not file_path_obj.exists():
                    await self.scanner.cache.clear()
                    self.logger.info(f"Cache cleared due to certificate {event_type}: {file_path}")
                elif file_path_obj.exists():
                    # For existing files (modifications only), use mtime-based cache key
                    cache_key = self.scanner.cache.make_key(
                        "cert", str(file_path), file_path_obj.stat().st_mtime
                    )
                    await self.scanner.cache.delete(cache_key)
                    self.logger.debug(f"Invalidated cache for: {file_path}")

            # Handle file changes (created, modified, deleted, moved)
            # For any meaningful change, clear metrics and trigger re-scan
            if event_type in ("deleted", "created", "moved") or not file_path_obj.exists():
                if hasattr(self.scanner, "metrics"):
                    # Clear all certificate metrics to ensure accurate state
                    self.scanner.metrics.clear_all_certificate_metrics()
                    self.scanner.metrics.reset_scan_metrics()
                    self.logger.info(
                        f"Metrics cleared due to certificate {event_type}: {file_path}"
                    )

                # Trigger immediate re-scan to update all metrics
                try:
                    self.logger.info(
                        f"Triggering re-scan due to certificate {event_type}: {file_path}"
                    )
                    await self.scanner.scan_once()
                except Exception as e:
                    self.logger.error(f"Failed to trigger re-scan after {event_type}: {e}")
            else:
                # For modifications only, the regular scan cycle will pick up the changes
                self.logger.debug(f"Certificate modification processed: {file_path}")

        except asyncio.CancelledError:
            self.logger.debug(f"Certificate change handling cancelled for: {file_path}")
        except Exception as e:
            self.logger.error(f"Error in debounced certificate change for {file_path}: {e}")

    async def _handle_config_change(self) -> None:
        """Handle configuration file changes with debouncing."""
        try:
            # Cancel existing config change task
            if self._config_change_task and not self._config_change_task.done():
                self._config_change_task.cancel()

            # Create new debounced task
            self._config_change_task = asyncio.create_task(self._debounced_config_change())

        except Exception as e:
            self.logger.error(f"Error handling config change: {e}")

    async def _debounced_config_change(self) -> None:
        """Debounced configuration change handler."""
        try:
            # Wait for debounce period
            await asyncio.sleep(2.0)

            self.logger.info("Reloading configuration due to file change")

            # Load new configuration
            new_config = load_config(str(self.config_path) if self.config_path else None)

            # Check if certificate directories changed
            old_dirs = set(self.config.certificate_directories)
            new_dirs = set(new_config.certificate_directories)

            dirs_added = new_dirs - old_dirs
            dirs_removed = old_dirs - new_dirs

            # Check if P12 passwords changed
            old_passwords = set(self.config.p12_passwords)
            new_passwords = set(new_config.p12_passwords)
            passwords_changed = old_passwords != new_passwords

            # Check if exclude patterns changed
            old_exclude_dirs = set(self.config.exclude_directories or [])
            new_exclude_dirs = set(new_config.exclude_directories or [])
            exclude_dirs_changed = old_exclude_dirs != new_exclude_dirs

            old_exclude_patterns = set(self.config.exclude_file_patterns or [])
            new_exclude_patterns = set(new_config.exclude_file_patterns or [])
            exclude_patterns_changed = old_exclude_patterns != new_exclude_patterns

            exclude_changed = exclude_dirs_changed or exclude_patterns_changed

            # Update configuration
            old_config = self.config
            self.config = new_config
            self.scanner.config = new_config

            # Update watched directories if needed
            if dirs_added or dirs_removed:
                # Clear cache entries for removed directories
                if dirs_removed and hasattr(self.scanner, "cache"):
                    await self.scanner.cache.clear()
                    self.logger.info("Cache cleared due to directory changes")

                # Reset all metrics when directories change
                if hasattr(self.scanner, "metrics"):
                    self.scanner.metrics.clear_all_certificate_metrics()
                    self.scanner.metrics.reset_scan_metrics()
                    self.logger.info("Metrics cleared and reset due to directory changes")

                await self._update_watched_directories(dirs_added, dirs_removed)

                # Trigger immediate re-scan to update metrics with new directory structure
                try:
                    self.logger.info("Triggering certificate re-scan due to directory changes")
                    await self.scanner.scan_once()
                except Exception as e:
                    self.logger.error(f"Failed to trigger re-scan after directory change: {e}")

            # Clear cache if scan interval changed significantly
            if abs(old_config.scan_interval_seconds - new_config.scan_interval_seconds) > 60:
                if hasattr(self.scanner, "cache"):
                    await self.scanner.cache.clear()
                    self.logger.info("Cache cleared due to scan interval change")

            # Clear cache and trigger re-scan if passwords changed
            if passwords_changed:
                if hasattr(self.scanner, "cache"):
                    await self.scanner.cache.clear()
                    self.logger.info("Cache cleared due to P12 password changes")

                # Reset parse error metrics to avoid stale errors
                if hasattr(self.scanner, "metrics"):
                    self.scanner.metrics.reset_parse_error_metrics()
                    self.logger.info("Parse error metrics reset due to password changes")

                # Trigger immediate re-scan to update metrics
                try:
                    self.logger.info("Triggering certificate re-scan due to password changes")
                    await self.scanner.scan_once()
                except Exception as e:
                    self.logger.error(f"Failed to trigger re-scan after password change: {e}")

            # Clear cache and trigger re-scan if exclude patterns changed
            if exclude_changed:
                if hasattr(self.scanner, "cache"):
                    await self.scanner.cache.clear()
                    self.logger.info("Cache cleared due to exclude pattern changes")

                # Clear all certificate metrics to remove excluded certificates from metrics
                if hasattr(self.scanner, "metrics"):
                    self.scanner.metrics.clear_all_certificate_metrics()
                    self.scanner.metrics.reset_scan_metrics()
                    self.logger.info(
                        "Certificate metrics cleared and scan metrics reset due to exclude pattern changes"
                    )

                # Trigger immediate re-scan to update metrics
                try:
                    self.logger.info(
                        "Triggering certificate re-scan due to exclude pattern changes"
                    )
                    await self.scanner.scan_once()
                except Exception as e:
                    self.logger.error(
                        f"Failed to trigger re-scan after exclude pattern change: {e}"
                    )

            # Log configuration changes
            changes = []
            if dirs_added:
                changes.append(f"Added directories: {dirs_added}")
            if dirs_removed:
                changes.append(f"Removed directories: {dirs_removed}")
            if old_config.scan_interval != new_config.scan_interval:
                changes.append(
                    f"Scan interval: {old_config.scan_interval} -> {new_config.scan_interval}"
                )
            if old_config.workers != new_config.workers:
                changes.append(f"Workers: {old_config.workers} -> {new_config.workers}")
            if passwords_changed:
                passwords_added = new_passwords - old_passwords
                passwords_removed = old_passwords - new_passwords
                if passwords_added:
                    changes.append(f"Added {len(passwords_added)} P12 password(s)")
                if passwords_removed:
                    changes.append(f"Removed {len(passwords_removed)} P12 password(s)")
            if exclude_dirs_changed:
                exclude_dirs_added = new_exclude_dirs - old_exclude_dirs
                exclude_dirs_removed = old_exclude_dirs - new_exclude_dirs
                if exclude_dirs_added:
                    changes.append(f"Added exclude directories: {exclude_dirs_added}")
                if exclude_dirs_removed:
                    changes.append(f"Removed exclude directories: {exclude_dirs_removed}")
            if exclude_patterns_changed:
                exclude_patterns_added = new_exclude_patterns - old_exclude_patterns
                exclude_patterns_removed = old_exclude_patterns - new_exclude_patterns
                if exclude_patterns_added:
                    changes.append(f"Added exclude patterns: {exclude_patterns_added}")
                if exclude_patterns_removed:
                    changes.append(f"Removed exclude patterns: {exclude_patterns_removed}")

            if changes:
                self.logger.info(f"Configuration updated: {'; '.join(changes)}")
            else:
                self.logger.info("Configuration reloaded (no significant changes detected)")

            log_hot_reload(self.logger, str(self.config_path), "config_reloaded")

        except asyncio.CancelledError:
            self.logger.debug("Configuration change handling cancelled")
        except Exception as e:
            self.logger.error(f"Error reloading configuration: {e}")

    async def _update_watched_directories(
        self, dirs_added: Set[str], dirs_removed: Set[str]
    ) -> None:
        """
        Update watched certificate directories.

        Args:
            dirs_added: Set of directory paths to start watching
            dirs_removed: Set of directory paths to stop watching
        """
        try:
            # Note: watchdog doesn't support removing individual watches easily,
            # so we restart the entire observer if directories changed
            if dirs_removed:
                self.logger.info("Restarting file watcher due to directory changes")
                await self.stop()
                await self.start()
            else:
                # Just add new directories
                for cert_dir in dirs_added:
                    cert_path = Path(cert_dir)
                    if cert_path.exists() and cert_path.is_dir():
                        self._observer.schedule(self._cert_handler, str(cert_path), recursive=True)
                        self._watched_paths.add(str(cert_path))
                        self.logger.info(f"Started watching new directory: {cert_path}")
                    else:
                        self.logger.warning(f"New certificate directory does not exist: {cert_dir}")

        except Exception as e:
            self.logger.error(f"Error updating watched directories: {e}")

    def get_status(self) -> dict:
        """Get hot reload status information."""
        return {
            "enabled": self.config.hot_reload,
            "watching": self._watching,
            "watched_paths": list(self._watched_paths),
            "config_path": str(self.config_path) if self.config_path else None,
            "active_cert_tasks": len(self._cert_change_tasks),
            "active_config_task": (
                self._config_change_task is not None and not self._config_change_task.done()
            ),
        }
