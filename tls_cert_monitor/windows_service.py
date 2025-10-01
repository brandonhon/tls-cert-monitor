"""
Windows Service implementation for TLS Certificate Monitor.

Optimized version for Nuitka standalone build.
Fixes 1053 startup error by ensuring immediate SERVICE_RUNNING status,
absolute logging paths, and proper error handling.
"""

import asyncio
import logging
import os
import sys
import threading
import time
from typing import Any, Optional

try:
    import win32event  # type: ignore
    import win32service  # type: ignore
    import win32serviceutil  # type: ignore
except ImportError:
    win32event = win32service = win32serviceutil = None


if win32serviceutil:

    class TLSCertMonitorService(win32serviceutil.ServiceFramework):
        _svc_name_ = "TLSCertMonitor"
        _svc_display_name_ = "TLS Certificate Monitor"
        _svc_description_ = "Monitor TLS/SSL certificates for expiration and security issues"

        def __init__(self, args: Any) -> None:
            super().__init__(args)

            # Create stop event immediately - critical for 1053 prevention
            self.hWaitStop = win32event.CreateEvent(None, 0, 0, None)
            self.stop_requested = threading.Event()
            self.monitor_thread: Optional[threading.Thread] = None
            self.config_path: Optional[str] = None

            # Setup absolute logging path BEFORE any operations - prevents 1053
            self._setup_logging()

            # Parse config path from command line args
            self._parse_config_args(args)

            self.logger.info("Service initialized successfully")

        def _setup_logging(self) -> None:
            """Setup absolute logging path that works in both Python and compiled modes."""
            # Use absolute path that always works for Windows services
            log_dir = r"C:\ProgramData\TLSCertMonitor"

            # Create directory with proper error handling
            try:
                os.makedirs(log_dir, exist_ok=True)
            except OSError:
                # Fallback to temp directory if ProgramData fails
                import tempfile

                log_dir = tempfile.gettempdir()

            log_file = os.path.join(log_dir, "TLSCertMonitor.log")

            # Configure logging with absolute path
            logging.basicConfig(
                filename=log_file,
                level=logging.INFO,
                format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
                datefmt="%Y-%m-%d %H:%M:%S",
            )
            self.logger = logging.getLogger(__name__)

        def _parse_config_args(self, args: Any) -> None:
            """Parse --config or -f argument from service args."""
            if len(args) > 1:
                args_list = list(args)
                for flag in ("--config", "-f"):
                    if flag in args_list:
                        idx = args_list.index(flag)
                        if idx + 1 < len(args_list):
                            self.config_path = args_list[idx + 1]
                            self.logger.info(f"Using config path: {self.config_path}")
                            break

        def SvcStop(self) -> None:
            """Handle service stop request - must be fast to prevent 1053."""
            self.logger.info("Service stop requested")

            # Report stop pending immediately
            self.ReportServiceStatus(win32service.SERVICE_STOP_PENDING)

            # Signal threads to stop
            self.stop_requested.set()
            win32event.SetEvent(self.hWaitStop)

            # Give background thread time to cleanup gracefully
            if self.monitor_thread and self.monitor_thread.is_alive():
                self.monitor_thread.join(timeout=30)
                if self.monitor_thread.is_alive():
                    self.logger.warning("Monitor thread did not stop gracefully")

            self.logger.info("Service stopped successfully")

        def SvcDoRun(self) -> None:
            """Main service loop - critical for preventing 1053 errors."""
            try:
                # CRITICAL: Report running status IMMEDIATELY to prevent 1053
                # This must be the first operation in SvcDoRun
                self.ReportServiceStatus(win32service.SERVICE_RUNNING)
                self.logger.info("Service reported as RUNNING")

                # Small delay to ensure SCM processes the status change
                time.sleep(0.5)

                # Start monitoring in background thread - never block main thread
                self.logger.info("Starting monitor thread")
                self.monitor_thread = threading.Thread(
                    target=self._run_monitor, name="TLSMonitorThread", daemon=True
                )
                self.monitor_thread.start()
                self.logger.info("Monitor thread started successfully")

                # Wait for stop signal - this is the only blocking operation allowed
                win32event.WaitForSingleObject(self.hWaitStop, win32event.INFINITE)

            except Exception as e:
                # Critical error handling - never let exceptions propagate to SCM
                self.logger.exception(f"Fatal service error: {e}")
                self.ReportServiceStatus(win32service.SERVICE_STOPPED)
                raise

        def _run_monitor(self) -> None:
            """Background thread for running the monitoring logic."""
            try:
                self.logger.info("Monitor thread starting")

                # Dynamic import to avoid startup delays in main thread
                import importlib

                # Import the main monitor class
                main_module = importlib.import_module("tls_cert_monitor.main")
                TLSCertMonitor = main_module.TLSCertMonitor

                # Create new event loop for this thread
                loop = asyncio.new_event_loop()
                asyncio.set_event_loop(loop)

                try:
                    # Create and configure monitor
                    monitor = TLSCertMonitor(config_path=self.config_path, dry_run=False)

                    self.logger.info("Starting TLS certificate monitoring")

                    # Run the monitor with stop condition
                    loop.run_until_complete(self._run_monitor_with_stop(monitor, loop))

                finally:
                    # Always close the event loop
                    loop.close()

            except Exception as e:
                self.logger.exception(f"Monitor thread failed: {e}")
            finally:
                self.logger.info("Monitor thread exiting")

        async def _run_monitor_with_stop(self, monitor: Any, loop: Any) -> None:
            """Run monitor with proper stop handling."""
            try:
                # Create a task for the monitor
                monitor_task = loop.create_task(monitor.run())

                # Check for stop signal periodically
                while not self.stop_requested.is_set():
                    if monitor_task.done():
                        break
                    await asyncio.sleep(1)

                # Cancel monitor if stop was requested
                if not monitor_task.done():
                    monitor_task.cancel()
                    try:
                        await monitor_task
                    except asyncio.CancelledError:
                        pass

            except Exception as e:
                self.logger.exception(f"Monitor execution failed: {e}")

else:
    # Dummy service for non-Windows platforms
    class TLSCertMonitorService:  # type: ignore[no-redef]
        _svc_name_ = "TLSCertMonitor"
        _svc_display_name_ = "TLS Certificate Monitor"
        _svc_description_ = "Monitor TLS/SSL certificates for expiration and security issues"

        def __init__(self, args: Any) -> None:
            pass


# =========================
# Utility functions
# =========================


def install_service(config_path: Optional[str] = None, auto_start: bool = True) -> bool:
    """Install the TLS Certificate Monitor as a Windows service.

    Handles both Python script mode and Nuitka compiled binary mode.
    """
    if not win32serviceutil:
        raise RuntimeError("pywin32 is required for Windows service support")

    try:
        # Build service arguments
        service_args = [TLSCertMonitorService._svc_name_]
        if config_path:
            service_args.extend(["--config", config_path])

        # Detect execution mode - critical for proper service installation
        is_compiled = getattr(sys, "frozen", False) or hasattr(sys, "_MEIPASS")

        if not is_compiled:
            # Standard Python script mode
            exe_args = (
                f'"{__file__}" {" ".join(service_args[1:])}'
                if len(service_args) > 1
                else f'"{__file__}"'
            )

            win32serviceutil.InstallService(
                pythonClassString=f"{TLSCertMonitorService.__module__}.{TLSCertMonitorService.__name__}",
                serviceName=TLSCertMonitorService._svc_name_,
                displayName=TLSCertMonitorService._svc_display_name_,
                description=TLSCertMonitorService._svc_description_,
                startType=(
                    win32service.SERVICE_AUTO_START
                    if auto_start
                    else win32service.SERVICE_DEMAND_START
                ),
                exeName=sys.executable,
                exeArgs=exe_args,
            )
        else:
            # Nuitka compiled binary mode - use direct SCM API
            # This ensures correct image path for compiled executables
            exe_name = sys.argv[0]  # Full path to compiled executable
            image_path = f'"{exe_name}"'

            if config_path:
                image_path += f' --config "{config_path}"'

            # Use Windows Service Control Manager directly
            hs = win32service.OpenSCManager(None, None, win32service.SC_MANAGER_ALL_ACCESS)
            try:
                service_handle = win32service.CreateService(
                    hs,
                    TLSCertMonitorService._svc_name_,
                    TLSCertMonitorService._svc_display_name_,
                    win32service.SERVICE_ALL_ACCESS,
                    win32service.SERVICE_WIN32_OWN_PROCESS,
                    (
                        win32service.SERVICE_AUTO_START
                        if auto_start
                        else win32service.SERVICE_DEMAND_START
                    ),
                    win32service.SERVICE_ERROR_NORMAL,
                    image_path,  # Correct binary path
                    None,  # No load order group
                    0,  # No tag ID
                    None,  # No dependencies
                    None,  # Use LocalSystem account
                    None,  # No password
                )
                win32service.CloseServiceHandle(service_handle)
            finally:
                win32service.CloseServiceHandle(hs)

        print(f"Service '{TLSCertMonitorService._svc_display_name_}' installed successfully")
        if auto_start:
            print("Service is configured to start automatically")
        else:
            print("Service is configured for manual start")
        return True

    except Exception as e:
        print(f"Failed to install service: {e}")
        return False


def uninstall_service() -> bool:
    """Uninstall the TLS Certificate Monitor Windows service."""
    if not win32serviceutil:
        raise RuntimeError("pywin32 is required for Windows service support")

    try:
        # Stop service first if running
        try:
            win32serviceutil.StopService(TLSCertMonitorService._svc_name_)
            time.sleep(2)  # Give service time to stop
        except Exception:
            pass  # Service might not be running  # nosec B110

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
        status = win32serviceutil.QueryServiceStatus(TLSCertMonitorService._svc_name_)[1]
        status_map = {
            win32service.SERVICE_STOPPED: "STOPPED",
            win32service.SERVICE_START_PENDING: "START_PENDING",
            win32service.SERVICE_STOP_PENDING: "STOP_PENDING",
            win32service.SERVICE_RUNNING: "RUNNING",
            win32service.SERVICE_CONTINUE_PENDING: "CONTINUE_PENDING",
            win32service.SERVICE_PAUSE_PENDING: "PAUSE_PENDING",
            win32service.SERVICE_PAUSED: "PAUSED",
        }
        return status_map.get(status, f"UNKNOWN({status})")

    except Exception as e:
        return f"ERROR: {e}"


def is_windows_service_available() -> bool:
    """Check if Windows service functionality is available."""
    return win32serviceutil is not None


if __name__ == "__main__":
    if win32serviceutil:
        win32serviceutil.HandleCommandLine(TLSCertMonitorService)
