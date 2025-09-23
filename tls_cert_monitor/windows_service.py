"""
Windows Service implementation for TLS Certificate Monitor.

This module provides Windows Service support using pywin32, allowing the
TLS Certificate Monitor to run as a native Windows service without requiring
third-party tools like NSSM.
"""

import asyncio
import logging
import sys
import threading
import time
from threading import Thread
from typing import Any, Optional

try:
    import win32event  # type: ignore[import-untyped]
    import win32service  # type: ignore[import-untyped]
    import win32serviceutil  # type: ignore[import-untyped]
    from win32service import SERVICE_RUNNING, SERVICE_STOP_PENDING
except ImportError:
    # Not on Windows or pywin32 not available
    win32event = win32service = win32serviceutil = None
    SERVICE_RUNNING = SERVICE_STOP_PENDING = None

from tls_cert_monitor.config import load_config
from tls_cert_monitor.logger import setup_logging

if win32serviceutil:

    class TLSCertMonitorService(win32serviceutil.ServiceFramework):
        """Windows Service wrapper for TLS Certificate Monitor."""

        _svc_name_ = "TLSCertMonitor"
        _svc_display_name_ = "TLS Certificate Monitor"
        _svc_description_ = "Monitor TLS/SSL certificates for expiration and security issues"

        def __init__(self, args: Any) -> None:
            """Initialize the Windows service."""
            win32serviceutil.ServiceFramework.__init__(self, args)
            self.hWaitStop = win32event.CreateEvent(None, 0, 0, None)
            self.is_alive = True
            self.monitor: Any = None
            self.monitor_thread: Optional[Thread] = None
            self.loop: Optional[asyncio.AbstractEventLoop] = None
            self.config_path: Optional[str] = None

            # Parse command line arguments for config file
            if len(args) > 1:
                self.config_path = args[1]

            # Setup basic logging early
            self.logger = logging.getLogger(__name__)

        def SvcStop(self) -> None:
            """Handle service stop request."""
            self.logger.info("Windows service stop requested")
            self.ReportServiceStatus(SERVICE_STOP_PENDING)
            win32event.SetEvent(self.hWaitStop)
            self.is_alive = False

            # Stop the monitor if running
            if self.monitor and self.loop:
                try:
                    # Schedule shutdown in the event loop
                    asyncio.run_coroutine_threadsafe(self.monitor.shutdown(), self.loop)
                except Exception as e:
                    self.logger.error(f"Error during service shutdown: {e}")

        def SvcDoRun(self) -> None:
            """Main service execution method."""
            try:
                # Setup logging for service
                try:
                    config = load_config(self.config_path)
                    setup_logging(config)
                    self.logger = logging.getLogger(__name__)
                    self.logger.info("TLS Certificate Monitor Windows service starting")
                except Exception as e:
                    # Fallback logging if config fails
                    logging.basicConfig(level=logging.INFO)
                    self.logger = logging.getLogger(__name__)
                    self.logger.error(f"Failed to load config, using defaults: {e}")

                # Report that we're running
                self.ReportServiceStatus(SERVICE_RUNNING)

                # Create and start the monitor in a separate thread
                self.monitor_thread = threading.Thread(target=self._run_monitor, daemon=True)
                self.monitor_thread.start()

                # Wait for stop signal
                win32event.WaitForSingleObject(self.hWaitStop, win32event.INFINITE)

                # Wait for monitor thread to finish
                if self.monitor_thread and self.monitor_thread.is_alive():
                    self.monitor_thread.join(timeout=30)

                self.logger.info("TLS Certificate Monitor Windows service stopped")

            except Exception as e:
                self.logger.error(f"Service execution failed: {e}")
                raise

        def _run_monitor(self) -> None:
            """Run the TLS Certificate Monitor in an async event loop."""
            try:
                # Import here to avoid circular imports
                from tls_cert_monitor.main import TLSCertMonitor  # type: ignore[import-not-found]

                # Create new event loop for this thread
                self.loop = asyncio.new_event_loop()
                asyncio.set_event_loop(self.loop)

                # Create and initialize the monitor
                self.monitor = TLSCertMonitor(config_path=self.config_path, dry_run=False)

                # Run the monitor
                self.loop.run_until_complete(self.monitor.run())

            except Exception as e:
                self.logger.error(f"Monitor execution failed: {e}")
            finally:
                if self.loop:
                    self.loop.close()

else:
    # Dummy class for non-Windows systems
    class TLSCertMonitorService:  # type: ignore[no-redef]
        """Dummy service class for non-Windows systems."""

        _svc_name_ = "TLSCertMonitor"
        _svc_display_name_ = "TLS Certificate Monitor"
        _svc_description_ = "Monitor TLS/SSL certificates for expiration and security issues"

        def __init__(self, args: Any) -> None:
            pass


def install_service(
    service_config_path: Optional[str] = None, service_auto_start: bool = True
) -> bool:
    """Install the TLS Certificate Monitor as a Windows service."""
    if not win32serviceutil:
        raise RuntimeError("pywin32 is required for Windows service support")

    try:
        # Build service parameters
        service_args = [TLSCertMonitorService._svc_name_]
        if service_config_path:
            service_args.append(service_config_path)

        # Install the service
        win32serviceutil.InstallService(
            pythonClassString=f"{TLSCertMonitorService.__module__}.{TLSCertMonitorService.__name__}",
            serviceName=TLSCertMonitorService._svc_name_,
            displayName=TLSCertMonitorService._svc_display_name_,
            startType=(
                win32service.SERVICE_AUTO_START
                if service_auto_start
                else win32service.SERVICE_DEMAND_START
            ),
            description=TLSCertMonitorService._svc_description_,
            exeName=sys.executable,
            exeArgs=f'"{__file__}" {" ".join(service_args[1:])}' if len(service_args) > 1 else None,
        )

        print(f"Service '{TLSCertMonitorService._svc_display_name_}' installed successfully")

        if service_auto_start:
            print("Service is configured to start automatically")

        return True

    except Exception as e:
        print(f"Failed to install service: {e}")
        return False


def uninstall_service() -> bool:
    """Uninstall the TLS Certificate Monitor Windows service."""
    if not win32serviceutil:
        raise RuntimeError("pywin32 is required for Windows service support")

    try:
        # Stop the service if running
        try:
            win32serviceutil.StopService(TLSCertMonitorService._svc_name_)
            print("Service stopped")
            time.sleep(2)  # Give it time to stop
        except Exception:
            # Service might not be running - this is expected behavior
            pass  # nosec B110

        # Remove the service
        win32serviceutil.RemoveService(TLSCertMonitorService._svc_name_)
        print(f"Service '{TLSCertMonitorService._svc_display_name_}' uninstalled successfully")
        return True

    except Exception as e:
        print(f"Failed to uninstall service: {e}")
        return False


def start_service() -> bool:
    """Start the TLS Certificate Monitor Windows service."""
    if not win32serviceutil:
        raise RuntimeError("pywin32 is required for Windows service support")

    try:
        win32serviceutil.StartService(TLSCertMonitorService._svc_name_)
        print(f"Service '{TLSCertMonitorService._svc_display_name_}' started successfully")
        return True
    except Exception as e:
        print(f"Failed to start service: {e}")
        return False


def stop_service() -> bool:
    """Stop the TLS Certificate Monitor Windows service."""
    if not win32serviceutil:
        raise RuntimeError("pywin32 is required for Windows service support")

    try:
        win32serviceutil.StopService(TLSCertMonitorService._svc_name_)
        print(f"Service '{TLSCertMonitorService._svc_display_name_}' stopped successfully")
        return True
    except Exception as e:
        print(f"Failed to stop service: {e}")
        return False


def get_service_status() -> str:
    """Get the current status of the TLS Certificate Monitor Windows service."""
    if not win32serviceutil:
        raise RuntimeError("pywin32 is required for Windows service support")

    try:
        service_status = win32serviceutil.QueryServiceStatus(TLSCertMonitorService._svc_name_)
        state = service_status[1]

        status_map = {
            win32service.SERVICE_STOPPED: "STOPPED",
            win32service.SERVICE_START_PENDING: "START_PENDING",
            win32service.SERVICE_STOP_PENDING: "STOP_PENDING",
            win32service.SERVICE_RUNNING: "RUNNING",
            win32service.SERVICE_CONTINUE_PENDING: "CONTINUE_PENDING",
            win32service.SERVICE_PAUSE_PENDING: "PAUSE_PENDING",
            win32service.SERVICE_PAUSED: "PAUSED",
        }

        return status_map.get(state, f"UNKNOWN({state})")

    except Exception as e:
        return f"ERROR: {e}"


def is_windows_service_available() -> bool:
    """Check if Windows service functionality is available."""
    return win32serviceutil is not None


if __name__ == "__main__":
    # Allow the service to be run directly
    if len(sys.argv) == 1:
        # No arguments - try to start as service
        try:
            win32serviceutil.HandleCommandLine(TLSCertMonitorService)
        except Exception as e:
            print(f"Failed to run as service: {e}")
            print("Try running with --install, --start, --stop, or --remove")
    else:
        # Handle service management commands
        if "--install" in sys.argv:
            config_path = None
            auto_start = "--manual" not in sys.argv

            # Look for config file argument
            for i, arg in enumerate(sys.argv):
                if arg == "--config" and i + 1 < len(sys.argv):
                    config_path = sys.argv[i + 1]
                    break

            install_service(config_path, auto_start)

        elif "--remove" in sys.argv or "--uninstall" in sys.argv:
            uninstall_service()

        elif "--start" in sys.argv:
            start_service()

        elif "--stop" in sys.argv:
            stop_service()

        elif "--status" in sys.argv:
            status = get_service_status()
            print(f"Service status: {status}")

        else:
            # Default to service framework handling
            win32serviceutil.HandleCommandLine(TLSCertMonitorService)
