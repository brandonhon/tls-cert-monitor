"""
Minimal Windows Service implementation for TLS Certificate Monitor.

This module provides simplified Windows Service support using pywin32,
designed to avoid timeout issues and provide reliable service operation.
"""

import logging
import sys
import threading
import time
from typing import Any, Optional

try:
    import win32event  # type: ignore[import-untyped]
    import win32service  # type: ignore[import-untyped]
    import win32serviceutil  # type: ignore[import-untyped]
except ImportError:
    # Not on Windows or pywin32 not available
    win32event = win32service = win32serviceutil = None


if win32serviceutil:

    class TLSCertMonitorService(win32serviceutil.ServiceFramework):
        """Minimal Windows Service wrapper for TLS Certificate Monitor."""

        _svc_name_ = "TLSCertMonitor"
        _svc_display_name_ = "TLS Certificate Monitor"
        _svc_description_ = "Monitor TLS/SSL certificates for expiration and security issues"

        def __init__(self, args: Any) -> None:
            """Initialize the Windows service."""
            win32serviceutil.ServiceFramework.__init__(self, args)
            self.hWaitStop = win32event.CreateEvent(None, 0, 0, None)
            self.monitor_thread: Optional[threading.Thread] = None
            self.config_path: Optional[str] = None
            self.logger = logging.getLogger(__name__)

            # Parse config path from arguments
            if len(args) > 1:
                args_list = list(args)
                if "--config" in args_list or "-f" in args_list:
                    for flag in ["--config", "-f"]:
                        if flag in args_list:
                            try:
                                config_index = args_list.index(flag)
                                if config_index + 1 < len(args_list):
                                    self.config_path = args_list[config_index + 1]
                                    break
                            except (ValueError, IndexError):
                                pass

        def SvcStop(self) -> None:
            """Stop the service gracefully."""
            self.ReportServiceStatus(win32service.SERVICE_STOP_PENDING)
            win32event.SetEvent(self.hWaitStop)

        def SvcDoRun(self) -> None:
            """Main service execution method."""
            try:
                # Report service as running immediately
                self.ReportServiceStatus(win32service.SERVICE_RUNNING)

                # Start monitor in background thread
                self.monitor_thread = threading.Thread(target=self._run_monitor, daemon=False)
                self.monitor_thread.start()

                # Wait for stop signal
                win32event.WaitForSingleObject(self.hWaitStop, win32event.INFINITE)

                # Wait for monitor thread to finish
                if self.monitor_thread and self.monitor_thread.is_alive():
                    self.monitor_thread.join(timeout=30)

            except Exception as e:
                self.logger.error(f"Service execution failed: {e}")
                self.ReportServiceStatus(win32service.SERVICE_STOPPED)
                raise

        def _run_monitor(self) -> None:
            """Run the TLS Certificate Monitor in background thread."""
            try:
                # Import here to avoid circular imports
                import asyncio
                import importlib

                # Dynamically import to avoid type checker issues
                main_module = importlib.import_module("tls_cert_monitor.main")
                TLSCertMonitor = main_module.TLSCertMonitor

                # Create new event loop for this thread
                loop = asyncio.new_event_loop()
                asyncio.set_event_loop(loop)

                # Create and run the monitor
                monitor = TLSCertMonitor(config_path=self.config_path, dry_run=False)
                loop.run_until_complete(monitor.run())

            except Exception as e:
                self.logger.error(f"Monitor execution failed: {e}")
            finally:
                if "loop" in locals():
                    loop.close()

else:
    # Dummy class for non-Windows systems
    class TLSCertMonitorService:  # type: ignore[no-redef]
        """Dummy service class for non-Windows systems."""

        _svc_name_ = "TLSCertMonitor"
        _svc_display_name_ = "TLS Certificate Monitor"
        _svc_description_ = "Monitor TLS/SSL certificates for expiration and security issues"

        def __init__(self, args: Any) -> None:
            pass


def install_service(config_path: Optional[str] = None, auto_start: bool = True) -> bool:
    """Install the TLS Certificate Monitor as a Windows service."""
    if not win32serviceutil:
        raise RuntimeError("pywin32 is required for Windows service support")

    try:
        # Build service arguments
        service_args = [TLSCertMonitorService._svc_name_]
        if config_path:
            service_args.extend(["--config", config_path])

        # Determine if running from compiled binary
        is_compiled = (
            getattr(sys, "frozen", False)
            or hasattr(sys, "_MEIPASS")
            or "__compiled__" in globals()
            or (sys.argv[0].endswith(".exe") and not sys.argv[0].endswith("python.exe"))
        )

        if is_compiled:
            # Use direct service registration for compiled binary
            exe_name = sys.argv[0]
            if config_path:
                image_path = f'"{exe_name}" --service --config "{config_path}"'
            else:
                image_path = f'"{exe_name}" --service'

            # Register service using low-level API
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
                    image_path,
                    None,
                    0,
                    None,
                    None,
                    None,
                )

                # Set service description
                try:
                    win32service.ChangeServiceConfig2(
                        service_handle,
                        win32service.SERVICE_CONFIG_DESCRIPTION,
                        TLSCertMonitorService._svc_description_,
                    )
                except Exception:
                    pass  # Description is optional  # nosec B110

                win32service.CloseServiceHandle(service_handle)
            finally:
                win32service.CloseServiceHandle(hs)
        else:
            # Use Python class registration for script
            win32serviceutil.InstallService(
                pythonClassString=f"{TLSCertMonitorService.__module__}.{TLSCertMonitorService.__name__}",
                serviceName=TLSCertMonitorService._svc_name_,
                displayName=TLSCertMonitorService._svc_display_name_,
                startType=(
                    win32service.SERVICE_AUTO_START
                    if auto_start
                    else win32service.SERVICE_DEMAND_START
                ),
                description=TLSCertMonitorService._svc_description_,
                exeName=sys.executable,
                exeArgs=(
                    f'"{__file__}" {" ".join(service_args[1:])}'
                    if len(service_args) > 1
                    else f'"{__file__}"'
                ),
            )

        print(f"Service '{TLSCertMonitorService._svc_display_name_}' installed successfully")
        if auto_start:
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
        # Stop service if running
        try:
            win32serviceutil.StopService(TLSCertMonitorService._svc_name_)
            time.sleep(2)
        except Exception:
            pass  # Service might not be running  # nosec B110

        # Remove service
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
    if win32serviceutil:
        win32serviceutil.HandleCommandLine(TLSCertMonitorService)
