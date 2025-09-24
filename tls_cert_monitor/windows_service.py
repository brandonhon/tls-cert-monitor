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
            # Setup debug logging to file immediately
            import os
            import tempfile

            debug_log = os.path.join(tempfile.gettempdir(), "tls-cert-monitor-service-debug.log")
            self._debug_log = open(debug_log, "a", encoding="utf-8")
            self._debug_log.write(
                f"\n=== SERVICE INIT START {time.strftime('%Y-%m-%d %H:%M:%S')} ===\n"
            )
            self._debug_log.write("DEBUG: TLSCertMonitorService.__init__ called\n")
            self._debug_log.write(f"DEBUG: Service init args: {args}\n")
            self._debug_log.flush()

            print("DEBUG: TLSCertMonitorService.__init__ called")
            print(f"DEBUG: Service init args: {args}")
            print(f"DEBUG: Debug log file: {debug_log}")

            try:
                win32serviceutil.ServiceFramework.__init__(self, args)
                print("DEBUG: ServiceFramework.__init__ completed")
            except Exception as e:
                print(f"ERROR: ServiceFramework.__init__ failed: {e}")
                import traceback

                print(f"DEBUG: ServiceFramework init traceback: {traceback.format_exc()}")
                raise

            self.hWaitStop = win32event.CreateEvent(None, 0, 0, None)
            self.is_alive = True
            self.monitor: Any = None
            self.monitor_thread: Optional[Thread] = None
            self.loop: Optional[asyncio.AbstractEventLoop] = None
            self.config_path: Optional[str] = None

            print("DEBUG: Service member variables initialized")

            # Parse command line arguments for config file
            # Arguments come as: [service_name, --service, --config, path]
            # or: [service_name, path] (legacy format)
            if len(args) > 1:
                args_list = list(args)
                # Debug output for service argument parsing
                print("Service initialization debug:")
                print(f"  args received: {args}")
                print(f"  args_list: {args_list}")

                if "--config" in args_list:
                    try:
                        config_index = args_list.index("--config")
                        if config_index + 1 < len(args_list):
                            self.config_path = args_list[config_index + 1]
                            print(f"  config_path from --config: {self.config_path}")
                    except (ValueError, IndexError):
                        print("  Failed to parse --config argument")
                elif len(args_list) > 1:
                    # Legacy format: assume second argument is config path
                    self.config_path = args_list[1]
                    print(f"  config_path from legacy format: {self.config_path}")
            else:
                print("Service initialization debug: No arguments provided")

            # Setup basic logging early
            self.logger = logging.getLogger(__name__)
            self._debug("Service initialized with config_path", self.config_path)
            print(f"DEBUG: Service initialized with config_path: {self.config_path}")

        def _debug(self, message: str, *args: Any) -> None:
            """Write debug message to both console and file."""
            timestamp = time.strftime("%Y-%m-%d %H:%M:%S")
            full_message = f"[{timestamp}] {message}"
            if args:
                full_message += f": {' '.join(str(arg) for arg in args)}"

            print(f"DEBUG: {full_message}")
            if hasattr(self, "_debug_log"):
                self._debug_log.write(f"DEBUG: {full_message}\n")
                self._debug_log.flush()

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
            start_time = time.time()
            self._debug("SvcDoRun called - service is starting")
            try:
                # Setup logging for service
                self._debug("Setting up logging and configuration")
                try:
                    config = load_config(self.config_path)
                    setup_logging(config)
                    self.logger = logging.getLogger(__name__)
                    self.logger.info("TLS Certificate Monitor Windows service starting")
                    self._debug("Logging setup completed successfully")
                except Exception as e:
                    # Fallback logging if config fails
                    self._debug("Config loading failed", str(e))
                    logging.basicConfig(level=logging.INFO)
                    self.logger = logging.getLogger(__name__)
                    self.logger.error(f"Failed to load config, using defaults: {e}")
                    self._debug("Fallback logging setup completed")

                # Create and start the monitor in a separate thread BEFORE reporting running
                self._debug("Creating monitor thread")
                self.monitor_thread = threading.Thread(target=self._run_monitor, daemon=True)
                self._debug("Starting monitor thread")
                self.monitor_thread.start()

                # Give the monitor thread a moment to start up
                self._debug("Waiting 2 seconds for monitor thread startup")
                time.sleep(2)

                # Check if monitor thread is still alive after startup
                thread_alive = self.monitor_thread.is_alive()
                self._debug("Checking monitor thread status: alive =", thread_alive)
                if not thread_alive:
                    error_msg = "Monitor thread failed to start properly"
                    self._debug("ERROR:", error_msg)
                    self.logger.error(error_msg)
                    raise RuntimeError(error_msg)

                # Report that we're running only after successful startup
                elapsed = time.time() - start_time
                self._debug(f"About to report SERVICE_RUNNING to SCM (elapsed: {elapsed:.2f}s)")
                self.logger.info("Reporting service as running to SCM")
                self.ReportServiceStatus(SERVICE_RUNNING)
                self._debug("SERVICE_RUNNING reported to SCM successfully")

                # Wait for stop signal
                self.logger.info("Service running, waiting for stop signal...")
                win32event.WaitForSingleObject(self.hWaitStop, win32event.INFINITE)

                # Wait for monitor thread to finish
                self.logger.info("Stop signal received, shutting down monitor...")
                if self.monitor_thread and self.monitor_thread.is_alive():
                    self.monitor_thread.join(timeout=30)

                self.logger.info("TLS Certificate Monitor Windows service stopped")

            except Exception as e:
                self.logger.error(f"Service execution failed: {e}")
                # Report service stopped on error
                self.ReportServiceStatus(win32service.SERVICE_STOPPED)
                raise

        def _run_monitor(self) -> None:
            """Run the TLS Certificate Monitor in an async event loop."""
            try:
                self.logger.info("Starting monitor thread...")

                # Import here to avoid circular imports
                from tls_cert_monitor.main import TLSCertMonitor  # type: ignore[import-not-found]

                self.logger.info("Creating event loop...")
                # Create new event loop for this thread
                self.loop = asyncio.new_event_loop()
                asyncio.set_event_loop(self.loop)

                self.logger.info("Initializing TLS Certificate Monitor...")
                # Create and initialize the monitor
                self.monitor = TLSCertMonitor(config_path=self.config_path, dry_run=False)

                self.logger.info("Starting monitor execution...")
                # Run the monitor
                self.loop.run_until_complete(self.monitor.run())

            except Exception as e:
                self.logger.error(f"Monitor execution failed: {e}")
                import traceback

                self.logger.error(f"Monitor traceback: {traceback.format_exc()}")
                # Signal that we've failed
                self.is_alive = False
            finally:
                self.logger.info("Monitor thread finishing...")
                if self.loop:
                    self.loop.close()
                self.logger.info("Monitor thread finished")

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
        # Detect if running from compiled binary or Python script
        # Check multiple indicators for different binary packers
        is_compiled = (
            getattr(sys, "frozen", False)  # PyInstaller, cx_Freeze
            or hasattr(sys, "_MEIPASS")  # PyInstaller
            or "__compiled__" in globals()  # Nuitka
            or (
                sys.argv[0].endswith(".exe") and not sys.argv[0].endswith("python.exe")
            )  # General executable
        )

        # Debug output to understand detection
        print("Service installation debug:")
        print(f"  sys.frozen: {getattr(sys, 'frozen', 'Not set')}")
        print(f"  sys._MEIPASS: {hasattr(sys, '_MEIPASS')}")
        print(f"  __compiled__ in globals: {'__compiled__' in globals()}")
        print(f"  sys.argv[0]: {sys.argv[0]}")
        print(f"  is_compiled: {is_compiled}")

        if is_compiled:
            # Running from compiled binary - use direct executable approach (like manual sc.exe)
            exe_name = sys.argv[0]
            exe_args_str = ""
            if service_config_path:
                exe_args_str = f'-f "{service_config_path}"'

            print("DEBUG: Installing service with direct executable approach")
            print(f"DEBUG: exe_name = {exe_name}")
            print(f"DEBUG: exe_args_str = {exe_args_str}")

            # Use direct executable registration (no pythonClassString)
            win32serviceutil.InstallService(
                serviceName=TLSCertMonitorService._svc_name_,
                displayName=TLSCertMonitorService._svc_display_name_,
                startType=(
                    win32service.SERVICE_AUTO_START
                    if service_auto_start
                    else win32service.SERVICE_DEMAND_START
                ),
                description=TLSCertMonitorService._svc_description_,
                exeName=exe_name,
                exeArgs=exe_args_str,
            )
        else:
            # Running from Python script - use traditional service class approach
            service_args = [TLSCertMonitorService._svc_name_]
            if service_config_path:
                service_args.append(service_config_path)
            exe_name = sys.executable
            exe_args_str = (
                f'"{__file__}" {" ".join(service_args[1:])}'
                if len(service_args) > 1
                else f'"{__file__}"'
            )

            print("DEBUG: Installing service with Python class approach")
            print(f"DEBUG: exe_name = {exe_name}")
            print(f"DEBUG: exe_args_str = {exe_args_str}")

            # Use Python class registration
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
                exeName=exe_name,
                exeArgs=exe_args_str,
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

        # Track if any removal method succeeded
        removal_succeeded = False

        # Remove the service using pywin32
        try:
            win32serviceutil.RemoveService(TLSCertMonitorService._svc_name_)
            print(f"Service '{TLSCertMonitorService._svc_display_name_}' marked for deletion")
            removal_succeeded = True
            time.sleep(1)  # Brief pause
        except Exception as e:
            print(f"Warning: pywin32 removal failed: {e}")

        # Force deletion using sc delete as fallback
        import subprocess  # nosec B404

        try:
            result = subprocess.run(  # nosec B603, B607
                ["sc", "delete", TLSCertMonitorService._svc_name_],
                capture_output=True,
                text=True,
                check=False,
            )
            if result.returncode == 0:
                print(f"Service '{TLSCertMonitorService._svc_display_name_}' deleted successfully")
                removal_succeeded = True
            elif (
                "does not exist" in result.stderr.lower()
                or "specified service does not exist" in result.stderr.lower()
            ):
                print(f"Service '{TLSCertMonitorService._svc_display_name_}' was already removed")
                removal_succeeded = True
            else:
                print(f"sc delete output: {result.stderr.strip()}")
        except Exception as e:
            print(f"Warning: sc delete failed: {e}")

        return removal_succeeded

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
