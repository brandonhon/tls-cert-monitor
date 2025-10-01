"""
Windows Service implementation for TLS Certificate Monitor.

Patched version for Nuitka standalone build.
Fixes 1053 startup error by correcting image_path, absolute logging path,
and adding better error handling.
"""

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
            self.hWaitStop = win32event.CreateEvent(None, 0, 0, None)
            self.stop_requested = threading.Event()
            self.monitor_thread: Optional[threading.Thread] = None
            self.config_path: Optional[str] = None

            # Absolute log path (always write somewhere valid for a service)
            log_dir = r"C:\ProgramData\TLSCertMonitor"
            os.makedirs(log_dir, exist_ok=True)
            logging.basicConfig(
                filename=os.path.join(log_dir, "TLSCertMonitor.log"),
                level=logging.INFO,
                format="%(asctime)s [%(levelname)s] %(message)s",
            )
            self.logger = logging.getLogger(__name__)

            # Parse --config or -f argument
            if len(args) > 1:
                args_list = list(args)
                for flag in ("--config", "-f"):
                    if flag in args_list:
                        idx = args_list.index(flag)
                        if idx + 1 < len(args_list):
                            self.config_path = args_list[idx + 1]
                            break

        def SvcStop(self) -> None:
            """Handle service stop request."""
            self.logger.info("Service stop requested")
            self.ReportServiceStatus(win32service.SERVICE_STOP_PENDING)
            self.stop_requested.set()
            win32event.SetEvent(self.hWaitStop)

            # Wait for thread to finish gracefully
            if self.monitor_thread and self.monitor_thread.is_alive():
                self.monitor_thread.join(timeout=30)
            self.logger.info("Service stopped")

        def SvcDoRun(self) -> None:
            """Main service loop."""
            try:
                # Report running immediately to prevent 1053
                self.ReportServiceStatus(win32service.SERVICE_RUNNING)
                self.logger.info("Service started")
                time.sleep(1)  # buffer for SCM

                # Start monitor in background thread
                self.monitor_thread = threading.Thread(target=self._run_monitor, daemon=True)
                self.monitor_thread.start()

                # Wait for stop signal
                win32event.WaitForSingleObject(self.hWaitStop, win32event.INFINITE)

            except Exception as e:
                self.logger.exception(f"Service execution failed: {e}")
                self.ReportServiceStatus(win32service.SERVICE_STOPPED)
                raise

        def _run_monitor(self) -> None:
            """Background monitor thread."""
            try:
                import asyncio
                import importlib

                self.logger.info("Initializing TLS Certificate Monitor")
                main_module = importlib.import_module("tls_cert_monitor.main")
                TLSCertMonitor = main_module.TLSCertMonitor

                # Create asyncio event loop for this thread
                loop = asyncio.new_event_loop()
                asyncio.set_event_loop(loop)

                # Create and run monitor
                monitor = TLSCertMonitor(config_path=self.config_path, dry_run=False)
                loop.run_until_complete(monitor.run())

            except Exception as e:
                self.logger.exception(f"Monitor thread failed: {e}")

            finally:
                if "loop" in locals():
                    loop.close()
                self.logger.info("Monitor thread exiting")

else:
    # Dummy service for non-Windows
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
    if not win32serviceutil:
        raise RuntimeError("pywin32 is required for Windows service support")

    try:
        service_args = [TLSCertMonitorService._svc_name_]
        if config_path:
            service_args.extend(["--config", config_path])

        # Determine if running from compiled binary
        is_compiled = getattr(sys, "frozen", False) or hasattr(sys, "_MEIPASS")
        exe_name = sys.executable if not is_compiled else sys.argv[0]

        if not is_compiled:
            # Standard Python mode
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
            # Nuitka compiled binary mode
            image_path = f'"{exe_name}"'
            if config_path:
                image_path += f' --config "{config_path}"'

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
                    image_path,  # <-- fixed
                    None,
                    0,
                    None,
                    None,
                    None,
                )
                win32service.CloseServiceHandle(service_handle)
            finally:
                win32service.CloseServiceHandle(hs)

        print(f"Service '{TLSCertMonitorService._svc_display_name_}' installed successfully")
        return True

    except Exception as e:
        print(f"Failed to install service: {e}")
        return False


def uninstall_service() -> bool:
    if not win32serviceutil:
        raise RuntimeError("pywin32 is required for Windows service support")
    try:
        try:
            win32serviceutil.StopService(TLSCertMonitorService._svc_name_)
            time.sleep(2)
        except Exception:
            pass  # Service might not be running, continue with uninstall  # nosec B110
        win32serviceutil.RemoveService(TLSCertMonitorService._svc_name_)
        print(f"Service '{TLSCertMonitorService._svc_display_name_}' uninstalled successfully")
        return True
    except Exception as e:
        print(f"Failed to uninstall service: {e}")
        return False


def start_service() -> bool:
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
    if not win32serviceutil:
        raise RuntimeError("pywin32 is required for Windows service support")
    try:
        status = win32serviceutil.QueryServiceStatus(TLSCertMonitorService._svc_name_)[1]
        return {
            win32service.SERVICE_STOPPED: "STOPPED",
            win32service.SERVICE_START_PENDING: "START_PENDING",
            win32service.SERVICE_STOP_PENDING: "STOP_PENDING",
            win32service.SERVICE_RUNNING: "RUNNING",
            win32service.SERVICE_CONTINUE_PENDING: "CONTINUE_PENDING",
            win32service.SERVICE_PAUSE_PENDING: "PAUSE_PENDING",
            win32service.SERVICE_PAUSED: "PAUSED",
        }.get(status, f"UNKNOWN({status})")
    except Exception as e:
        return f"ERROR: {e}"


def is_windows_service_available() -> bool:
    return win32serviceutil is not None


if __name__ == "__main__":
    if win32serviceutil:
        win32serviceutil.HandleCommandLine(TLSCertMonitorService)
