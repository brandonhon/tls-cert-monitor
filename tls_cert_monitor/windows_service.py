"""
Windows Service Implementation for TLS Certificate Monitor

This module provides a proper Windows service implementation using pywin32
that works reliably with the Windows Service Control Manager (SCM).
"""

import asyncio
import logging
import sys
import threading
from typing import TYPE_CHECKING, Any, Optional

if TYPE_CHECKING:
    from tls_cert_monitor.main import TLSCertMonitor  # type: ignore[import-not-found]

try:
    import servicemanager
    import win32event
    import win32service
    import win32serviceutil
except ImportError:
    # Not on Windows or pywin32 not available
    win32event = None
    win32service = None
    win32serviceutil = None
    servicemanager = None


class TLSCertMonitorService(win32serviceutil.ServiceFramework):
    """Windows service wrapper for TLS Certificate Monitor."""

    _svc_name_ = "TLSCertMonitor"
    _svc_display_name_ = "TLS Certificate Monitor"
    _svc_description_ = "Monitor TLS/SSL certificates for expiration and security issues"
    _svc_python_location_: Optional[str] = None  # Will be set dynamically

    def __init__(self, args: Any) -> None:
        win32serviceutil.ServiceFramework.__init__(self, args)
        self.stop_event = win32event.CreateEvent(None, 0, 0, None)
        self.running = True
        self.monitor_instance: Optional["TLSCertMonitor"] = None
        self.app_thread: Optional[threading.Thread] = None

        # Set up logging
        self.logger = logging.getLogger(__name__)

        # Parse config path from service command line
        self.config_path = self._parse_config_path()

    def _parse_config_path(self) -> Optional[str]:
        """Parse config path from service command line arguments."""
        try:
            # Service command line is available in the registry
            # For now, we'll use a default path that can be overridden
            import os

            default_config = r"C:\ProgramData\tls-cert-monitor\config.yaml"
            if os.path.exists(default_config):
                return default_config
        except Exception:
            pass
        return None

    def SvcStop(self) -> None:
        """Handle service stop request from SCM."""
        self.ReportServiceStatus(win32service.SERVICE_STOP_PENDING)
        servicemanager.LogMsg(
            servicemanager.EVENTLOG_INFORMATION_TYPE,
            servicemanager.PYS_SERVICE_STOPPED,
            (self._svc_name_, "Service stop requested"),
        )

        # Signal the service to stop
        win32event.SetEvent(self.stop_event)
        self.running = False

    def SvcDoRun(self) -> None:
        """Main service entry point called by SCM."""
        servicemanager.LogMsg(
            servicemanager.EVENTLOG_INFORMATION_TYPE,
            servicemanager.PYS_SERVICE_STARTED,
            (self._svc_name_, "Service starting"),
        )

        try:
            self.main()
        except Exception as e:
            servicemanager.LogErrorMsg(f"Service failed: {e}")
            raise

    def main(self) -> None:
        """Main service execution loop."""
        try:
            # Import here to avoid circular imports
            from tls_cert_monitor.main import TLSCertMonitor

            # Create the monitor instance
            self.monitor_instance = TLSCertMonitor(config_path=self.config_path, dry_run=False)

            # Start the application in a separate thread
            self.app_thread = threading.Thread(target=self._run_app_async, daemon=False)
            self.app_thread.start()

            servicemanager.LogMsg(
                servicemanager.EVENTLOG_INFORMATION_TYPE,
                servicemanager.PYS_SERVICE_STARTED,
                (self._svc_name_, "Application started successfully"),
            )

            # Wait for stop signal
            while self.running:
                # Wait for stop event with timeout
                result = win32event.WaitForSingleObject(self.stop_event, 1000)
                if result == win32event.WAIT_OBJECT_0:
                    break

            # Shutdown the application
            self._shutdown_app()

            servicemanager.LogMsg(
                servicemanager.EVENTLOG_INFORMATION_TYPE,
                servicemanager.PYS_SERVICE_STOPPED,
                (self._svc_name_, "Service stopped successfully"),
            )

        except Exception as e:
            servicemanager.LogErrorMsg(f"Service main failed: {e}")
            raise

    def _run_app_async(self) -> None:
        """Run the TLS Certificate Monitor application in async context."""
        try:
            # Create new event loop for this thread
            loop = asyncio.new_event_loop()
            asyncio.set_event_loop(loop)

            # Run the application
            if self.monitor_instance:
                loop.run_until_complete(self.monitor_instance.run())

        except Exception as e:
            servicemanager.LogErrorMsg(f"Application failed: {e}")
            self.running = False
            win32event.SetEvent(self.stop_event)
        finally:
            if "loop" in locals():
                loop.close()

    def _shutdown_app(self) -> None:
        """Gracefully shutdown the application."""
        if self.monitor_instance:
            try:
                # Create a temporary event loop to run shutdown
                loop = asyncio.new_event_loop()
                asyncio.set_event_loop(loop)
                loop.run_until_complete(self.monitor_instance.shutdown())
                loop.close()
            except Exception as e:
                servicemanager.LogErrorMsg(f"Shutdown failed: {e}")

        if self.app_thread and self.app_thread.is_alive():
            # Give the thread some time to finish
            self.app_thread.join(timeout=10)


def is_running_as_service() -> bool:
    """Check if we're running as a Windows service."""
    if sys.platform != "win32":
        return False

    # Simple check: if we have no console window, likely a service
    try:  # type: ignore[unreachable]
        import ctypes

        kernel32 = ctypes.windll.kernel32
        return kernel32.GetConsoleWindow() == 0
    except Exception:
        return False


def install_service(config_path: Optional[str] = None) -> None:
    """Install the Windows service."""
    if not win32serviceutil:
        raise ImportError("pywin32 is required for Windows service support")

    # Set the service executable path to the current executable
    TLSCertMonitorService._svc_python_location_ = sys.executable

    # Install with config path in the command line
    service_args = [TLSCertMonitorService._svc_name_]
    if config_path:
        service_args.extend(["--config", config_path])

    win32serviceutil.InstallService(
        TLSCertMonitorService._svc_python_location_,
        TLSCertMonitorService._svc_name_,
        TLSCertMonitorService._svc_display_name_,
        description=TLSCertMonitorService._svc_description_,
    )


def run_service() -> None:
    """Run the Windows service."""
    if not win32serviceutil:
        raise ImportError("pywin32 is required for Windows service support")

    # Set the service executable path to the current executable
    TLSCertMonitorService._svc_python_location_ = sys.executable

    win32serviceutil.HandleCommandLine(TLSCertMonitorService)


if __name__ == "__main__":
    # Handle command line service operations
    run_service()
