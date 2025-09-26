#!/usr/bin/env python3
"""
TLS Certificate Monitor - Main Application Entry Point
"""

import asyncio
import logging
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
@click.option("--service-install", is_flag=True, help="Install as Windows service (Windows only)")
@click.option("--service-uninstall", is_flag=True, help="Uninstall Windows service (Windows only)")
@click.option("--service-start", is_flag=True, help="Start Windows service (Windows only)")
@click.option("--service-stop", is_flag=True, help="Stop Windows service (Windows only)")
@click.option("--service-status", is_flag=True, help="Show Windows service status (Windows only)")
@click.option(
    "--service-manual",
    is_flag=True,
    help="Install service with manual start (use with --service-install)",
)
@click.option(
    "--service",
    is_flag=True,
    hidden=True,
    help="Internal flag - run as Windows service (used by service installation)",
)
def main(
    config: Optional[Path],
    version: bool,
    dry_run: bool,
    service_install: bool,
    service_uninstall: bool,
    service_start: bool,
    service_stop: bool,
    service_status: bool,
    service_manual: bool,
    service: bool,
) -> None:
    """TLS Certificate Monitor - Monitor SSL/TLS certificates for expiration and security issues."""

    # Handle special flags first (before any potential import issues)
    if version:
        print(f"TLS Certificate Monitor v{__version__}")
        return

    # Handle Windows service commands
    if service_install or service_uninstall or service_start or service_stop or service_status:
        try:
            from tls_cert_monitor.windows_service import (
                get_service_status,
                install_service,
                is_windows_service_available,
                start_service,
                stop_service,
                uninstall_service,
            )
        except ImportError as e:
            print("ERROR: Windows service functionality is not available.")
            print(f"Import error: {e}")
            print("This requires Windows and the pywin32 package.")
            sys.exit(1)

        if not is_windows_service_available():
            print("ERROR: Windows service functionality is not available.")
            print("This requires Windows and the pywin32 package.")
            sys.exit(1)

        config_path = str(config) if config else None

        if service_install:
            auto_start = not service_manual
            success = install_service(config_path, auto_start)
            sys.exit(0 if success else 1)
        elif service_uninstall:
            success = uninstall_service()
            sys.exit(0 if success else 1)
        elif service_start:
            success = start_service()
            sys.exit(0 if success else 1)
        elif service_stop:
            success = stop_service()
            sys.exit(0 if success else 1)
        elif service_status:
            status = get_service_status()
            print(f"Service status: {status}")
            sys.exit(0)

        return  # Exit after handling service commands

    # Handle Windows service mode
    if service:
        try:
            import win32serviceutil

            from tls_cert_monitor.windows_service import TLSCertMonitorService

            # Use the service framework
            win32serviceutil.HandleCommandLine(TLSCertMonitorService)
            return
        except ImportError as e:
            print("ERROR: Windows service functionality is not available.")
            print(f"Import error: {e}")
            print("This requires Windows and the pywin32 package.")
            sys.exit(1)
        except Exception as e:
            print(f"ERROR: Exception in service mode: {e}")
            sys.exit(1)

    try:
        monitor = TLSCertMonitor(str(config) if config else None, dry_run=dry_run)
        asyncio.run(monitor.run())
    except KeyboardInterrupt:
        print("\nShutdown requested by user")
        sys.exit(0)
    except Exception as e:
        print(f"Application failed: {e}")
        sys.exit(1)


if __name__ == "__main__":
    main()
