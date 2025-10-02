#!/usr/bin/env python3
"""
TLS Certificate Monitor - Main Application Entry Point
"""

import asyncio
import logging
import os
import signal
import sys
from pathlib import Path
from typing import Optional

import click
import uvicorn
from fastapi import FastAPI

from tls_cert_monitor import __version__
from tls_cert_monitor.api import create_app
from tls_cert_monitor.cache import CacheManager
from tls_cert_monitor.config import Config, load_config
from tls_cert_monitor.hot_reload import HotReloadManager
from tls_cert_monitor.logger import setup_logging
from tls_cert_monitor.metrics import MetricsCollector
from tls_cert_monitor.scanner import CertificateScanner


def _detect_windows_service() -> bool:
    """
    Enhanced detection for Windows service environment.

    Returns True if the application is likely running as a Windows service.
    """
    if sys.platform != "win32":
        return False

    # Multiple detection methods for reliability
    service_indicators = [
        # No console attached (typical for services)
        not sys.stdin.isatty(),

        # No interactive session
        not hasattr(sys, 'ps1'),

        # Parent process is services.exe (Windows Service Host)
        _is_parent_services_exe(),

        # Running in session 0 (services session)
        _is_session_zero(),

        # No user profile environment
        not bool(os.environ.get('USERPROFILE', ''))
    ]

    # Consider it a service if multiple indicators are present
    return sum(service_indicators) >= 2


def _is_parent_services_exe() -> bool:
    """Check if parent process is services.exe (Windows Service Host)."""
    try:
        import psutil
        current_process = psutil.Process()
        parent_process = current_process.parent()
        return parent_process and parent_process.name().lower() == 'services.exe'
    except (ImportError, psutil.Error):
        return False


def _is_session_zero() -> bool:
    """Check if running in session 0 (Windows services session)."""
    try:
        import os
        session_id = os.environ.get('SESSIONNAME', '')
        return session_id.lower() in ['', 'services']
    except Exception:
        return False


def _configure_service_environment() -> None:
    """Configure environment for Windows service operation."""
    import os
    import tempfile
    from pathlib import Path

    # Set up proper working directory for service
    if hasattr(sys, '_MEIPASS'):
        # Running as compiled binary
        working_dir = Path(sys.executable).parent
    else:
        # Running as script
        working_dir = Path(__file__).parent

    os.chdir(working_dir)

    # Ensure temp directory is available
    temp_dir = Path(tempfile.gettempdir()) / "tls-cert-monitor-service"
    temp_dir.mkdir(exist_ok=True)
    os.environ['TMP'] = str(temp_dir)
    os.environ['TEMP'] = str(temp_dir)

    # Set service-friendly logging defaults
    os.environ.setdefault('TLS_LOG_LEVEL', 'INFO')

    # Configure Windows Event Log source
    _setup_windows_event_log()


def _setup_windows_event_log() -> None:
    """Set up Windows Event Log source for service logging."""
    try:
        import winreg

        # Create event log source registry entry
        key_path = r"SYSTEM\CurrentControlSet\Services\EventLog\Application\TLSCertMonitor"

        with winreg.CreateKey(winreg.HKEY_LOCAL_MACHINE, key_path) as key:
            # Set message file (points to system message DLL)
            winreg.SetValueEx(key, "EventMessageFile", 0, winreg.REG_SZ,
                            r"%SystemRoot%\System32\kernel32.dll")
            winreg.SetValueEx(key, "TypesSupported", 0, winreg.REG_DWORD, 7)

    except (ImportError, OSError, PermissionError):
        # Event log setup failed, but service can still run
        pass


def _service_startup_sequence(monitor: 'TLSCertMonitor') -> None:
    """
    Enhanced startup sequence for Windows service operation.

    This provides better coordination with the Service Control Manager
    and handles the async event loop in a service-friendly way.
    """
    import time
    import threading
    from concurrent.futures import ThreadPoolExecutor

    # Service startup coordination
    startup_success = threading.Event()
    shutdown_requested = threading.Event()

    def service_main():
        """Main service execution in separate thread."""
        try:
            # Small delay to allow SCM to register service as starting
            time.sleep(1)

            # Create new event loop for service thread
            loop = asyncio.new_event_loop()
            asyncio.set_event_loop(loop)

            # Set up signal handlers for service shutdown
            _setup_service_signal_handlers(shutdown_requested, loop)

            try:
                # Initialize and run the monitor
                loop.run_until_complete(monitor.initialize())
                startup_success.set()  # Signal successful startup

                # Run with shutdown monitoring
                loop.run_until_complete(_run_with_shutdown_monitoring(monitor, shutdown_requested))

            finally:
                # Clean shutdown
                loop.run_until_complete(monitor.shutdown())
                loop.close()

        except Exception as e:
            # Log to Windows Event Log
            _log_service_error(f"Service execution failed: {e}")
            raise

    # Start service in background thread
    service_thread = threading.Thread(target=service_main, daemon=False)
    service_thread.start()

    # Wait for startup or timeout
    if startup_success.wait(timeout=30):
        # Service started successfully, wait for it to complete
        service_thread.join()
    else:
        # Startup timeout - this prevents the 1053 error
        shutdown_requested.set()
        service_thread.join(timeout=10)
        raise TimeoutError("Service failed to start within 30 seconds")


def _setup_service_signal_handlers(shutdown_event: threading.Event, loop: asyncio.AbstractEventLoop) -> None:
    """Set up signal handlers for graceful service shutdown."""
    def signal_handler(signum, frame):
        shutdown_event.set()
        # Schedule shutdown on the event loop
        if loop and not loop.is_closed():
            loop.call_soon_threadsafe(lambda: asyncio.create_task(_shutdown_handler()))

    # Windows service shutdown signals
    signal.signal(signal.SIGTERM, signal_handler)
    signal.signal(signal.SIGINT, signal_handler)

    # Windows-specific signals
    if hasattr(signal, 'SIGBREAK'):
        signal.signal(signal.SIGBREAK, signal_handler)


async def _shutdown_handler() -> None:
    """Handle graceful shutdown."""
    # Get all running tasks and cancel them
    tasks = [task for task in asyncio.all_tasks() if not task.done()]
    for task in tasks:
        task.cancel()

    # Wait for tasks to complete cancellation
    if tasks:
        await asyncio.gather(*tasks, return_exceptions=True)


async def _run_with_shutdown_monitoring(monitor: 'TLSCertMonitor', shutdown_event: threading.Event) -> None:
    """Run the monitor with periodic shutdown checks."""

    async def shutdown_monitor():
        """Monitor for shutdown requests."""
        while not shutdown_event.is_set():
            await asyncio.sleep(1)

    # Create monitoring task
    shutdown_task = asyncio.create_task(shutdown_monitor())

    # Create main application task
    app_task = asyncio.create_task(monitor.run())

    try:
        # Wait for either shutdown request or app completion
        done, pending = await asyncio.wait(
            [app_task, shutdown_task],
            return_when=asyncio.FIRST_COMPLETED
        )

        # Cancel pending tasks
        for task in pending:
            task.cancel()
            try:
                await task
            except asyncio.CancelledError:
                pass

    except Exception as e:
        _log_service_error(f"Error in service monitoring: {e}")
        raise


def _log_service_error(message: str) -> None:
    """Log error to Windows Event Log if available."""
    try:
        import win32evtlog
        import win32evtlogutil

        win32evtlogutil.ReportEvent(
            "TLSCertMonitor",
            1001,  # Event ID
            eventType=win32evtlog.EVENTLOG_ERROR_TYPE,
            strings=[message]
        )
    except ImportError:
        # Fallback to stderr
        print(f"ERROR: {message}", file=sys.stderr)
    except Exception:
        # Last resort - just print
        print(f"ERROR: {message}", file=sys.stderr)


class TLSCertMonitor:
    """Main application class for TLS Certificate Monitor."""

    def __init__(self, config_path: Optional[str] = None, dry_run: bool = False):
        self.config: Optional[Config] = None
        self.scanner: Optional[CertificateScanner] = None
        self.metrics: Optional[MetricsCollector] = None
        self.cache: Optional[CacheManager] = None
        self.hot_reload: Optional[HotReloadManager] = None
        self.app: Optional[FastAPI] = None
        self.config_path = config_path
        self.dry_run = dry_run
        self._shutdown_event = asyncio.Event()
        # Initialize logger early to avoid AttributeError
        self.logger = logging.getLogger(__name__)

    def _ensure_temp_directory(self) -> None:
        """Ensure Nuitka temp directory exists for compiled binaries."""
        import os
        import platform
        import tempfile

        system = platform.system()

        if system == "Windows":
            # Windows runtime temp directory resolution
            candidates = [
                Path(os.environ.get("TEMP", r"C:\Windows\Temp")) / "tls-cert-monitor",
                Path(os.environ.get("LOCALAPPDATA", r"C:\Users\Default\AppData\Local"))
                / "tls-cert-monitor",
                Path(tempfile.gettempdir()) / "tls-cert-monitor",
            ]

            # Find first working directory
            for candidate in candidates:
                try:
                    candidate.mkdir(parents=True, exist_ok=True)
                    # Test write access
                    test_file = candidate / ".write_test"
                    test_file.touch()
                    test_file.unlink()
                    # Set environment variable for Nuitka
                    os.environ["ONEFILE_TEMPDIR"] = str(candidate)
                    break
                except (OSError, PermissionError):
                    continue
        else:
            # Linux/macOS: Ensure /var/tmp/tls-cert-monitor exists for Nuitka
            temp_dir = Path("/var/tmp/tls-cert-monitor")
            try:
                temp_dir.mkdir(parents=True, exist_ok=True)
                # Set world-writable permissions so any user can use it
                temp_dir.chmod(0o1777)  # Sticky bit + rwxrwxrwx
            except (OSError, PermissionError):
                # If we can't create /var/tmp/tls-cert-monitor, try fallbacks
                fallback_candidates = [
                    Path.home() / ".cache" / "tls-cert-monitor",
                    Path("/tmp/tls-cert-monitor"),
                    Path(tempfile.gettempdir()) / "tls-cert-monitor",
                ]

                for candidate in fallback_candidates:
                    try:
                        candidate.mkdir(parents=True, exist_ok=True)
                        # Test write access
                        test_file = candidate / ".write_test"
                        test_file.touch()
                        test_file.unlink()
                        # Override Nuitka's temp directory
                        os.environ["ONEFILE_TEMPDIR"] = str(candidate)
                        break
                    except (OSError, PermissionError):
                        continue

    async def initialize(self) -> None:
        """Initialize all application components."""
        try:
            # Ensure Nuitka temp directory exists (for compiled binaries)
            self._ensure_temp_directory()

            # Load configuration
            self.config = load_config(self.config_path)

            # Setup logging
            setup_logging(self.config)
            self.logger.info("Initializing TLS Certificate Monitor")

            # Initialize cache
            self.cache = CacheManager(self.config)
            await self.cache.initialize()

            # Initialize metrics collector
            self.metrics = MetricsCollector()

            # Initialize certificate scanner
            self.scanner = CertificateScanner(
                config=self.config, cache=self.cache, metrics=self.metrics
            )

            # Initialize hot reload manager
            if self.config.hot_reload:
                self.hot_reload = HotReloadManager(
                    config=self.config, scanner=self.scanner, config_path=self.config_path
                )
                await self.hot_reload.start()

            # Create FastAPI app
            self.app = create_app(
                scanner=self.scanner, metrics=self.metrics, cache=self.cache, config=self.config
            )

            # Start initial scan
            await self.scanner.start_scanning()

            self.logger.info("TLS Certificate Monitor initialized successfully")

        except Exception as e:
            self.logger.error(f"Failed to initialize application: {e}")
            raise

    async def run(self) -> None:
        """Run the application server or perform dry-run scan."""
        if not self.app:
            await self.initialize()

        # At this point, config is guaranteed to be set by initialize()
        assert self.config is not None, "Config should be initialized"

        # Handle dry-run mode
        if self.dry_run:
            self.logger.info("Running in dry-run mode - scanning certificates only")
            # Perform one scan and exit
            if self.scanner:
                await self.scanner.scan_once()
            self.logger.info("Dry-run scan completed")
            await self.shutdown()
            return

        config_dict = {
            "app": self.app,
            "host": self.config.bind_address,
            "port": self.config.port,
            "log_level": self.config.log_level.lower(),
            "access_log": True,
        }

        # Add TLS configuration if provided
        if self.config.tls_cert and self.config.tls_key:
            config_dict.update(
                {
                    "ssl_keyfile": self.config.tls_key,
                    "ssl_certfile": self.config.tls_cert,
                }
            )
            self.logger.info(
                f"Starting HTTPS server on {self.config.bind_address}:{self.config.port}"
            )
        else:
            self.logger.info(
                f"Starting HTTP server on {self.config.bind_address}:{self.config.port}"
            )

        # Setup signal handlers for graceful shutdown
        for sig in [signal.SIGTERM, signal.SIGINT]:
            signal.signal(sig, self._signal_handler)

        server = uvicorn.Server(uvicorn.Config(**config_dict))

        # Run server with graceful shutdown
        try:
            await server.serve()
        except KeyboardInterrupt:
            self.logger.info("Received interrupt signal")
        finally:
            await self.shutdown()

    def _signal_handler(self, signum: int, frame: Optional[object]) -> None:
        """Handle shutdown signals."""
        if hasattr(self, "logger"):
            self.logger.info(f"Received signal {signum}, initiating graceful shutdown")
        self._shutdown_event.set()

    async def shutdown(self) -> None:
        """Gracefully shutdown all components."""
        if hasattr(self, "logger"):
            self.logger.info("Starting graceful shutdown")

        # Stop hot reload manager
        if self.hot_reload:
            await self.hot_reload.stop()

        # Stop scanner
        if self.scanner:
            await self.scanner.stop()

        # Close cache
        if self.cache:
            await self.cache.close()

        if hasattr(self, "logger"):
            self.logger.info("Graceful shutdown completed")


@click.command()
@click.option(
    "--config",
    "-f",
    type=click.Path(exists=True, path_type=Path),
    help="Path to configuration file",
)
@click.option("--version", "-v", is_flag=True, help="Show version information")
@click.option("--dry-run", is_flag=True, help="Enable dry-run mode (scan only, don't start server)")
def main(
    config: Optional[Path],
    version: bool,
    dry_run: bool,
) -> None:
    """TLS Certificate Monitor - Monitor SSL/TLS certificates for expiration and security issues."""

    # Handle special flags first (before any potential import issues)
    if version:
        print(f"TLS Certificate Monitor v{__version__}")
        return

    try:
        # Enhanced Windows service detection
        is_windows_service = _detect_windows_service()

        if is_windows_service:
            # Configure service-friendly environment
            _configure_service_environment()

        monitor = TLSCertMonitor(str(config) if config else None, dry_run=dry_run)

        # For Windows service scenarios, add startup coordination
        if is_windows_service:
            _service_startup_sequence(monitor)
        else:
            asyncio.run(monitor.run())
    except KeyboardInterrupt:
        print("\nShutdown requested by user")
        sys.exit(0)
    except Exception as e:
        # Log error to Windows Event Log if available
        if sys.platform == "win32":
            try:
                import win32evtlog
                import win32api
                win32evtlog.ReportEvent(
                    win32evtlog.RegisterEventSource(None, "TLSCertMonitor"),
                    win32evtlog.EVENTLOG_ERROR_TYPE,
                    0,
                    1001,
                    None,
                    [f"TLS Certificate Monitor failed: {e}"]
                )
            except ImportError:
                pass

        print(f"Application failed: {e}")
        sys.exit(1)


if __name__ == "__main__":
    main()
