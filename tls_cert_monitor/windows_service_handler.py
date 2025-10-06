"""
Minimal Windows Service Handler for TLS Certificate Monitor

This module provides the absolute minimum required for proper Windows service
operation without requiring pywin32. It uses ctypes to directly call Windows APIs.
"""

import asyncio
import ctypes
import ctypes.wintypes
import logging
import sys
import threading
import time
from typing import TYPE_CHECKING, Optional

if TYPE_CHECKING:
    from tls_cert_monitor.main import TLSCertMonitor  # type: ignore[import-not-found]

# Windows API constants
SERVICE_WIN32_OWN_PROCESS = 0x00000010
SERVICE_RUNNING = 0x00000004
SERVICE_START_PENDING = 0x00000002
SERVICE_STOP_PENDING = 0x00000003
SERVICE_STOPPED = 0x00000001

SERVICE_ACCEPT_STOP = 0x00000001
SERVICE_ACCEPT_SHUTDOWN = 0x00000004

SERVICE_CONTROL_STOP = 0x00000001
SERVICE_CONTROL_SHUTDOWN = 0x00000005

NO_ERROR = 0


class SERVICE_STATUS(ctypes.Structure):
    _fields_ = [
        ("dwServiceType", ctypes.wintypes.DWORD),
        ("dwCurrentState", ctypes.wintypes.DWORD),
        ("dwControlsAccepted", ctypes.wintypes.DWORD),
        ("dwWin32ExitCode", ctypes.wintypes.DWORD),
        ("dwServiceSpecificExitCode", ctypes.wintypes.DWORD),
        ("dwCheckPoint", ctypes.wintypes.DWORD),
        ("dwWaitHint", ctypes.wintypes.DWORD),
    ]


class SERVICE_STATUS_HANDLE(ctypes.wintypes.HANDLE):
    pass


# Service control handler function type
HANDLER_FUNCTION = ctypes.WINFUNCTYPE(None, ctypes.wintypes.DWORD)  # type: ignore[attr-defined]

# Service main function type
SERVICE_MAIN_FUNCTION = ctypes.WINFUNCTYPE(  # type: ignore[attr-defined]
    None, ctypes.wintypes.DWORD, ctypes.POINTER(ctypes.wintypes.LPWSTR)
)


class SERVICE_TABLE_ENTRY(ctypes.Structure):
    _fields_ = [
        ("lpServiceName", ctypes.wintypes.LPWSTR),
        ("lpServiceProc", SERVICE_MAIN_FUNCTION),
    ]


class WindowsServiceHandler:
    """Minimal Windows service handler using ctypes."""

    def __init__(self, service_name: str = "TLSCertMonitor"):
        self.service_name = service_name
        self.status_handle: Optional[SERVICE_STATUS_HANDLE] = None
        self.status = SERVICE_STATUS()
        self.stop_event = threading.Event()
        self.logger = logging.getLogger(__name__)

        # Initialize service status
        self.status.dwServiceType = SERVICE_WIN32_OWN_PROCESS
        self.status.dwCurrentState = SERVICE_STOPPED
        self.status.dwControlsAccepted = SERVICE_ACCEPT_STOP | SERVICE_ACCEPT_SHUTDOWN
        self.status.dwWin32ExitCode = NO_ERROR
        self.status.dwServiceSpecificExitCode = 0
        self.status.dwCheckPoint = 0
        self.status.dwWaitHint = 0

        # Get Windows API functions
        self.advapi32 = ctypes.windll.advapi32  # type: ignore[attr-defined]
        self.kernel32 = ctypes.windll.kernel32  # type: ignore[attr-defined]

    def service_ctrl_handler(self, control_code: int) -> None:
        """Handle service control requests from SCM."""
        if control_code == SERVICE_CONTROL_STOP:
            self.logger.info("Service stop requested")
            self.report_status(SERVICE_STOP_PENDING)
            self.stop_event.set()

        elif control_code == SERVICE_CONTROL_SHUTDOWN:
            self.logger.info("System shutdown requested")
            self.report_status(SERVICE_STOP_PENDING)
            self.stop_event.set()

    def report_status(
        self, current_state: int, exit_code: int = NO_ERROR, wait_hint: int = 0
    ) -> bool:
        """Report service status to SCM."""
        if not self.status_handle:
            return False

        self.status.dwCurrentState = current_state
        self.status.dwWin32ExitCode = exit_code
        self.status.dwWaitHint = wait_hint

        if current_state == SERVICE_START_PENDING:
            self.status.dwControlsAccepted = 0
        else:
            self.status.dwControlsAccepted = SERVICE_ACCEPT_STOP | SERVICE_ACCEPT_SHUTDOWN

        if current_state in [SERVICE_RUNNING, SERVICE_STOPPED]:
            self.status.dwCheckPoint = 0
        else:
            self.status.dwCheckPoint += 1

        # Call SetServiceStatus
        return bool(self.advapi32.SetServiceStatus(self.status_handle, ctypes.byref(self.status)))

    def service_main(self, argc: int, argv: object) -> None:  # pylint: disable=unused-argument
        """Main service entry point called by SCM."""
        try:
            # Register control handler
            handler_func = HANDLER_FUNCTION(self.service_ctrl_handler)
            self.status_handle = self.advapi32.RegisterServiceCtrlHandlerW(
                self.service_name, handler_func
            )

            if not self.status_handle:
                self.logger.error("Failed to register service control handler")
                return

            # Report start pending
            self.report_status(SERVICE_START_PENDING, wait_hint=3000)

            # Parse config path from command line arguments
            config_path = None
            try:
                # Look for --config in command line args
                for i, arg in enumerate(sys.argv):
                    if arg == "--config" and i + 1 < len(sys.argv):
                        config_path = sys.argv[i + 1]
                        break
                    elif arg.startswith("--config="):
                        config_path = arg.split("=", 1)[1]
                        break
            except Exception:
                # Silently continue if config parsing fails
                pass

            # Start the actual application
            self.run_application(config_path)

        except Exception as e:
            self.logger.error(f"Service main failed: {e}")
            self.report_status(SERVICE_STOPPED, exit_code=1)

    def run_application(self, config_path: Optional[str] = None) -> None:
        """Run the TLS Certificate Monitor application."""
        try:
            # Import here to avoid circular imports
            from tls_cert_monitor.main import TLSCertMonitor

            # Report start pending with longer wait hint
            self.report_status(SERVICE_START_PENDING, wait_hint=10000)

            # Create application instance with config path from service command line
            monitor = TLSCertMonitor(config_path=config_path)

            # Start application in separate thread
            app_thread = threading.Thread(target=self._run_app_async, args=(monitor,), daemon=True)
            app_thread.start()

            # Wait a moment for initialization
            time.sleep(2)

            # Report running status
            self.report_status(SERVICE_RUNNING)
            self.logger.info("Service reported as running to SCM")

            # Wait for stop signal
            self.stop_event.wait()

            # Report stop pending
            self.report_status(SERVICE_STOP_PENDING, wait_hint=5000)

            # Stop the application
            # The app_thread will handle its own cleanup

            # Report stopped
            self.report_status(SERVICE_STOPPED)
            self.logger.info("Service stopped")

        except Exception as e:
            self.logger.error(f"Application failed: {e}")
            self.report_status(SERVICE_STOPPED, exit_code=1)

    def _run_app_async(self, monitor: "TLSCertMonitor") -> None:
        """Run the application in async context."""
        try:
            loop = asyncio.new_event_loop()
            asyncio.set_event_loop(loop)

            # Set up stop monitoring
            async def stop_monitor() -> None:
                while not self.stop_event.is_set():
                    await asyncio.sleep(1)
                # Trigger graceful shutdown
                await monitor.shutdown()

            async def run_with_monitoring() -> None:
                await monitor.initialize()

                # Start monitoring task
                stop_task = asyncio.create_task(stop_monitor())
                app_task = asyncio.create_task(monitor.run())

                # Wait for either completion or stop signal
                _, pending = await asyncio.wait(
                    [app_task, stop_task], return_when=asyncio.FIRST_COMPLETED
                )

                # Cancel pending tasks
                for task in pending:
                    task.cancel()
                    try:
                        await task
                    except asyncio.CancelledError:
                        pass

            loop.run_until_complete(run_with_monitoring())

        except Exception as e:
            self.logger.error(f"Async application failed: {e}")
        finally:
            if "loop" in locals():
                loop.close()

    def start_service_dispatcher(self) -> bool:
        """Start the service control dispatcher."""
        # Create service table
        service_main_func = SERVICE_MAIN_FUNCTION(self.service_main)

        service_table = (SERVICE_TABLE_ENTRY * 2)()
        service_table[0].lpServiceName = self.service_name
        service_table[0].lpServiceProc = service_main_func
        service_table[1].lpServiceName = None
        service_table[1].lpServiceProc = None

        # Start service control dispatcher
        result = self.advapi32.StartServiceCtrlDispatcherW(service_table)

        if not result:
            error_code = self.kernel32.GetLastError()
            self.logger.error(f"StartServiceCtrlDispatcher failed with error {error_code}")
            return False

        return True


def is_running_as_service() -> bool:
    """Check if we're running as a Windows service."""
    if sys.platform != "win32":
        return False

    try:  # type: ignore[unreachable]
        # Try to get the console window using ctypes
        kernel32 = ctypes.windll.kernel32
        console_window = kernel32.GetConsoleWindow()

        # Services typically don't have console windows
        if console_window == 0:
            return True

        # Additional check: see if we can get the parent process
        try:
            import psutil

            current = psutil.Process()
            parent = current.parent()
            if parent and parent.name().lower() == "services.exe":
                return True
        except Exception:
            # Silently continue if service detection fails
            pass

        return False

    except Exception:
        return False


def run_as_service(service_name: str = "TLSCertMonitor") -> None:
    """Run the application as a Windows service."""
    handler = WindowsServiceHandler(service_name)

    if not handler.start_service_dispatcher():
        print("Failed to start service dispatcher", file=sys.stderr)
        sys.exit(1)
