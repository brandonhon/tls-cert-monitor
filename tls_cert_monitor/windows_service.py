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
from typing import Any, Optional, TextIO

try:
    import win32event  # type: ignore[import-untyped]
    import win32service  # type: ignore[import-untyped]
    import win32serviceutil  # type: ignore[import-untyped]
    from win32service import SERVICE_RUNNING
except ImportError:
    # Not on Windows or pywin32 not available
    win32event = win32service = win32serviceutil = None
    SERVICE_RUNNING = None

# IMMEDIATE debug output at module load time
import os

from tls_cert_monitor.config import load_config
from tls_cert_monitor.logger import setup_logging

try:
    module_debug_msg = f"windows_service.py MODULE LOADED at {time.strftime('%Y-%m-%d %H:%M:%S')}\n"
    module_debug_msg += f"Process ID: {os.getpid()}\n"
    module_debug_msg += f"Command line args: {sys.argv}\n"

    # Try to write to a simple debug file
    for module_debug_path in [
        r"C:\temp\module-load-debug.log",
        r"C:\Windows\Temp\module-load-debug.log",
    ]:
        try:
            os.makedirs(os.path.dirname(module_debug_path), exist_ok=True)
            with open(module_debug_path, "a", encoding="utf-8") as module_debug_file:
                module_debug_file.write(
                    f"\n=== MODULE LOAD {time.strftime('%Y-%m-%d %H:%M:%S')} ===\n"
                )
                module_debug_file.write(module_debug_msg)
                module_debug_file.flush()
            break
        except Exception:  # nosec B112
            continue
except Exception:  # nosec B110
    pass  # Don't let debug code break the module load

if win32serviceutil:

    class TLSCertMonitorService(win32serviceutil.ServiceFramework):
        """Windows Service wrapper for TLS Certificate Monitor."""

        _svc_name_ = "TLSCertMonitor"
        _svc_display_name_ = "TLS Certificate Monitor"
        _svc_description_ = "Monitor TLS/SSL certificates for expiration and security issues"

        def __init__(self, args: Any) -> None:
            """Initialize the Windows service."""
            # IMMEDIATE debug output to multiple locations
            import tempfile

            # Create multiple debug files in different locations
            timestamp = time.strftime("%Y-%m-%d %H:%M:%S")
            debug_msg = f"SERVICE __init__ CALLED at {timestamp} with args: {args}\n"

            # Try multiple locations for debug files
            debug_locations = [
                os.path.join(tempfile.gettempdir(), "tls-cert-monitor-service-debug.log"),
                r"C:\temp\tls-cert-monitor-service-debug.log",
                r"C:\Windows\Temp\tls-cert-monitor-service-debug.log",
                os.path.join(os.getcwd(), "tls-cert-monitor-service-debug.log"),
            ]

            for debug_location in debug_locations:
                try:
                    os.makedirs(os.path.dirname(debug_location), exist_ok=True)
                    with open(debug_location, "a", encoding="utf-8") as debug_file:
                        debug_file.write(f"\n=== SERVICE INIT START {timestamp} ===\n")
                        debug_file.write(debug_msg)
                        debug_file.flush()
                    print(f"DEBUG: Created debug file at {debug_location}")
                    break
                except Exception as e:
                    print(f"DEBUG: Failed to create debug file at {debug_location}: {e}")
                    continue

            # Setup the main debug log
            debug_log = debug_locations[0]  # Default to temp directory
            self._debug_log: Optional[TextIO] = None
            try:
                self._debug_log = open(debug_log, "a", encoding="utf-8")
                self._debug_log.write(debug_msg)
                self._debug_log.flush()
            except Exception as e:
                print(f"DEBUG: Failed to setup main debug log: {e}")
                self._debug_log = None

            print("DEBUG: TLSCertMonitorService.__init__ called")
            print(f"DEBUG: Service init args: {args}")
            print(f"DEBUG: Process ID: {os.getpid()}")
            print(f"DEBUG: Parent Process ID: {os.getppid() if hasattr(os, 'getppid') else 'N/A'}")
            print(f"DEBUG: Current working directory: {os.getcwd()}")
            print(f"DEBUG: Debug log file: {debug_log}")

            # Also write to Windows Event Log
            try:
                import win32evtlog  # type: ignore[import-untyped]
                import win32evtlogutil  # type: ignore[import-untyped]

                win32evtlogutil.ReportEvent(
                    "TLS Certificate Monitor",
                    1001,
                    eventCategory=0,
                    eventType=win32evtlog.EVENTLOG_INFORMATION_TYPE,
                    strings=[f"Service initialization started with args: {args}"],
                )
            except Exception:
                # Don't fail if event log doesn't work - continue service startup
                if self._debug_log:
                    self._debug_log.write("DEBUG: Event log reporting failed, continuing\n")
                    self._debug_log.flush()

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
            if hasattr(self, "_debug_log") and self._debug_log:
                self._debug_log.write(f"DEBUG: {full_message}\n")
                self._debug_log.flush()

        def SvcStop(self) -> None:
            """Stop the service gracefully."""
            self._debug("SvcStop called - initiating shutdown")
            try:
                self.ReportServiceStatus(win32service.SERVICE_STOP_PENDING)
            except Exception as e:
                self._debug(f"EXCEPTION during ReportServiceStatus(STOP_PENDING): {e}")

            # Signal the stop event so SvcDoRun unblocks
            win32event.SetEvent(self.hWaitStop)
            self._debug("Stop event set, waiting for SvcDoRun to finish")
            self.is_alive = False

            # Optional: join monitor thread here as extra safeguard
            if hasattr(self, "monitor_thread") and self.monitor_thread is not None:
                try:
                    self.monitor_thread.join(timeout=30)
                    self._debug("Monitor thread joined successfully in SvcStop")
                except Exception as join_e:
                    self._debug(f"Exception while joining monitor thread in SvcStop: {join_e}")

            self._debug("SvcStop completed")

        def SvcDoRun(self) -> None:
            """Main service execution method for TLS Certificate Monitor."""

            # Debug logging is already setup in __init__, write SvcDoRun start marker
            if hasattr(self, "_debug_log") and self._debug_log:
                self._debug_log.write(
                    f"\n=== SvcDoRun START {time.strftime('%Y-%m-%d %H:%M:%S')} ===\n"
                )
                self._debug_log.flush()

            self._debug("SvcDoRun called - service is starting")

            # Report START_PENDING
            try:
                self._debug("Reporting SERVICE_START_PENDING to SCM")
                self.ReportServiceStatus(win32service.SERVICE_START_PENDING)
            except Exception as e:
                self._debug(f"EXCEPTION during ReportServiceStatus(START_PENDING): {e}")

            try:
                # Minimal logging so we can see startup messages
                self._debug("Setting up minimal logging")
                logging.basicConfig(level=logging.INFO)
                self.logger = logging.getLogger(__name__)
                self.logger.info("TLS Certificate Monitor Windows service starting")

                # Report RUNNING to SCM
                try:
                    self.ReportServiceStatus(win32service.SERVICE_RUNNING)
                    self.logger.info("Successfully reported service as RUNNING to SCM")
                except Exception as e:
                    self._debug(f"EXCEPTION during ReportServiceStatus(RUNNING): {e}")
                    try:
                        # Fallback in case SERVICE_RUNNING constant imported differently
                        self.ReportServiceStatus(SERVICE_RUNNING)
                    except Exception as inner_e:
                        self._debug(f"Fallback SERVICE_RUNNING failed: {inner_e}")

                # Start monitor thread
                self._debug("Starting monitor thread")
                self.monitor_thread = threading.Thread(
                    target=self._run_monitor_with_stop_wait, daemon=False
                )
                self.monitor_thread.start()
                self.logger.info("Monitor thread started, service fully operational")

                # === Important fix: wait here for stop event instead of returning ===
                self._debug("SvcDoRun entering wait loop (waiting for stop event)...")
                win32event.WaitForSingleObject(self.hWaitStop, win32event.INFINITE)

                # When stop is requested, execution continues here
                self._debug("SvcDoRun detected stop event, proceeding to shutdown")

                # Optionally join monitor thread for graceful shutdown
                if self.monitor_thread is not None:
                    try:
                        self.logger.info("Waiting for monitor thread to exit...")
                        self.monitor_thread.join(timeout=30)
                    except Exception as join_e:
                        self._debug(f"Exception while joining monitor thread: {join_e}")

                self.logger.info("SvcDoRun completed shutdown sequence")

            except Exception as e:
                # Fatal startup or runtime error
                err_msg = f"Service execution failed: {e}"
                self._debug(err_msg)
                if self.logger:
                    self.logger.error(err_msg)
                try:
                    self.ReportServiceStatus(win32service.SERVICE_STOPPED)
                except Exception:  # nosec B110
                    pass  # Intentionally ignore errors during error handling
                raise

        def _run_monitor_with_stop_wait(self) -> None:
            """Run the TLS Certificate Monitor in background thread."""
            try:
                self.logger.info("Starting monitor thread...")

                # Do the heavy initialization work in this background thread
                self.logger.info("Loading configuration and setting up logging...")
                try:
                    self._debug("Loading configuration in background thread")
                    config = load_config(self.config_path)
                    setup_logging(config)
                    # Update logger after full logging setup
                    self.logger = logging.getLogger(__name__)
                    self.logger.info(
                        "Configuration loaded and logging setup completed in background"
                    )
                    self._debug("Full logging setup completed successfully in background")
                except Exception as e:
                    # Config loading failed, continue with basic logging
                    self._debug(
                        "Config loading failed in background, continuing with basic logging", str(e)
                    )
                    self.logger.error(f"Failed to load config in background, using defaults: {e}")

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
                # Run the monitor - this will block until the monitor shuts down
                self.loop.run_until_complete(self.monitor.run())

                self.logger.info("Monitor execution completed")

            except Exception as e:
                self.logger.error(f"Monitor execution failed: {e}")
                import traceback

                self.logger.error(f"Monitor traceback: {traceback.format_exc()}")
                # Signal that we've failed
                self.is_alive = False
            finally:
                self.logger.info("Monitor thread finishing...")
                if self.loop:
                    try:
                        # Shutdown the monitor gracefully if it's still running
                        if self.monitor:
                            self.logger.info("Shutting down monitor...")
                            self.loop.run_until_complete(self.monitor.shutdown())
                    except Exception as e:
                        self.logger.error(f"Error during monitor shutdown: {e}")
                    finally:
                        self.loop.close()
                self.logger.info("Monitor thread finished")

        def _run_monitor(self) -> None:
            """Legacy monitor runner - kept for compatibility."""
            # Redirect to the new implementation
            self._run_monitor_with_stop_wait()

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
            # Running from compiled binary - use simple executable with parameters
            exe_name = sys.argv[0]

            # Build the complete command line with parameters
            # Always include --service flag so the app knows it's running as a service
            if service_config_path:
                image_path = f'"{exe_name}" --service -f "{service_config_path}"'
            else:
                image_path = f'"{exe_name}" --service'

            print("DEBUG: Installing service with ImagePath approach")
            print(f"DEBUG: exe_name = {exe_name}")
            print(f"DEBUG: image_path = {image_path}")

            # Use low-level win32service API for clean binary registration
            print("DEBUG: Opening Service Control Manager")
            hs = win32service.OpenSCManager(None, None, win32service.SC_MANAGER_ALL_ACCESS)
            try:
                print("DEBUG: Creating service with parameters:")
                print(f"  Service name: {TLSCertMonitorService._svc_name_}")
                print(f"  Display name: {TLSCertMonitorService._svc_display_name_}")
                print(f"  Image path: {image_path}")
                print(f"  Auto start: {service_auto_start}")

                service_handle = win32service.CreateService(
                    hs,
                    TLSCertMonitorService._svc_name_,
                    TLSCertMonitorService._svc_display_name_,
                    win32service.SERVICE_ALL_ACCESS,
                    win32service.SERVICE_WIN32_OWN_PROCESS,
                    (
                        win32service.SERVICE_AUTO_START
                        if service_auto_start
                        else win32service.SERVICE_DEMAND_START
                    ),
                    win32service.SERVICE_ERROR_NORMAL,
                    image_path,  # Full command line with parameters
                    None,
                    0,
                    None,
                    None,
                    None,
                )
                print("DEBUG: Service created successfully, handle:", service_handle)

                # Set service description
                try:
                    win32service.ChangeServiceConfig2(
                        service_handle,
                        win32service.SERVICE_CONFIG_DESCRIPTION,
                        TLSCertMonitorService._svc_description_,
                    )
                    print("DEBUG: Service description set successfully")
                except Exception as e:
                    print(f"Warning: Could not set service description: {e}")

                win32service.CloseServiceHandle(service_handle)
                print("DEBUG: Service handle closed")
            except Exception as e:
                print(f"ERROR: Failed to create service: {e}")
                import traceback

                print(f"DEBUG: Service creation traceback: {traceback.format_exc()}")
                raise
            finally:
                win32service.CloseServiceHandle(hs)
                print("DEBUG: SCM handle closed")
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
