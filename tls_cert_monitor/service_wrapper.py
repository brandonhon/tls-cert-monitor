"""
Windows Service Wrapper for TLS Certificate Monitor

This module provides native Windows service support without requiring pywin32.
It uses the built-in Windows service infrastructure and communicates with the
Service Control Manager (SCM) properly.
"""

import asyncio
import logging
import signal
import sys
import threading
import time
from typing import Optional

try:
    import win32service
    import win32serviceutil
    import win32event
    WIN32_AVAILABLE = True
except ImportError:
    WIN32_AVAILABLE = False


class TLSCertMonitorService:
    """
    Windows Service wrapper for TLS Certificate Monitor.

    This class handles Windows service lifecycle and delegates the actual
    application logic to the main TLSCertMonitor class.
    """

    def __init__(self, config_path: Optional[str] = None):
        self.config_path = config_path
        self.monitor = None
        self.loop = None
        self.thread = None
        self.stop_event = threading.Event()
        self.logger = logging.getLogger(__name__)

    def start(self):
        """Start the service."""
        self.logger.info("Starting TLS Certificate Monitor Windows Service")

        # Create and start the application thread
        self.thread = threading.Thread(target=self._run_monitor, daemon=True)
        self.thread.start()

        # Give the application time to start
        time.sleep(2)

        self.logger.info("TLS Certificate Monitor Windows Service started")

    def stop(self):
        """Stop the service."""
        self.logger.info("Stopping TLS Certificate Monitor Windows Service")

        # Set the stop event
        self.stop_event.set()

        # Stop the monitor if it exists
        if self.monitor and self.loop:
            # Schedule shutdown on the event loop
            asyncio.run_coroutine_threadsafe(self.monitor.shutdown(), self.loop)

        # Wait for the thread to finish (with timeout)
        if self.thread and self.thread.is_alive():
            self.thread.join(timeout=10)

        self.logger.info("TLS Certificate Monitor Windows Service stopped")

    def _run_monitor(self):
        """Run the monitor in a separate thread with its own event loop."""
        try:
            # Import here to avoid import issues in service context
            from tls_cert_monitor.main import TLSCertMonitor

            # Create new event loop for this thread
            self.loop = asyncio.new_event_loop()
            asyncio.set_event_loop(self.loop)

            # Create monitor instance
            self.monitor = TLSCertMonitor(self.config_path, dry_run=False)

            # Run the monitor with proper exception handling
            try:
                self.loop.run_until_complete(self._run_with_stop_check())
            except Exception as e:
                self.logger.error(f"Monitor failed: {e}")
                raise
        except Exception as e:
            self.logger.error(f"Failed to start monitor: {e}")
            # Re-raise to cause service to fail
            raise
        finally:
            if self.loop:
                self.loop.close()

    async def _run_with_stop_check(self):
        """Run the monitor with periodic stop checks."""
        # Initialize the monitor
        await self.monitor.initialize()

        # Create the server task
        server_task = asyncio.create_task(self._run_server())

        # Create stop check task
        stop_task = asyncio.create_task(self._check_stop_event())

        try:
            # Wait for either server completion or stop signal
            done, pending = await asyncio.wait(
                [server_task, stop_task],
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
            self.logger.error(f"Error in service execution: {e}")
            raise
        finally:
            # Ensure clean shutdown
            await self.monitor.shutdown()

    async def _run_server(self):
        """Run the FastAPI server."""
        import uvicorn

        if not self.monitor.app:
            raise RuntimeError("Application not initialized")

        config_dict = {
            "app": self.monitor.app,
            "host": self.monitor.config.bind_address,
            "port": self.monitor.config.port,
            "log_level": self.monitor.config.log_level.lower(),
            "access_log": True,
        }

        # Add TLS configuration if provided
        if self.monitor.config.tls_cert and self.monitor.config.tls_key:
            config_dict.update({
                "ssl_keyfile": self.monitor.config.tls_key,
                "ssl_certfile": self.monitor.config.tls_cert,
            })

        server = uvicorn.Server(uvicorn.Config(**config_dict))
        await server.serve()

    async def _check_stop_event(self):
        """Periodically check for stop event."""
        while not self.stop_event.is_set():
            await asyncio.sleep(1)


if WIN32_AVAILABLE:
    class TLSCertMonitorWindowsService(win32serviceutil.ServiceFramework):
        """
        Windows Service class that integrates with Windows Service Control Manager.
        """

        _svc_name_ = "TLSCertMonitor"
        _svc_display_name_ = "TLS Certificate Monitor"
        _svc_description_ = "Monitor TLS/SSL certificates for expiration and security issues"

        def __init__(self, args):
            win32serviceutil.ServiceFramework.__init__(self, args)
            self.hWaitStop = win32event.CreateEvent(None, 0, 0, None)
            self.service_wrapper = None

            # Get config path from command line args if provided
            config_path = None
            if len(args) > 1:
                # Parse command line for config path
                for i, arg in enumerate(args):
                    if arg == "--config" and i + 1 < len(args):
                        config_path = args[i + 1]
                        break

            self.service_wrapper = TLSCertMonitorService(config_path)

        def SvcStop(self):
            """Called when the service is requested to stop."""
            self.ReportServiceStatus(win32service.SERVICE_STOP_PENDING)
            win32event.SetEvent(self.hWaitStop)

            if self.service_wrapper:
                self.service_wrapper.stop()

        def SvcDoRun(self):
            """Called when the service is requested to start."""
            import servicemanager

            servicemanager.LogMsg(
                servicemanager.EVENTLOG_INFORMATION_TYPE,
                servicemanager.PYS_SERVICE_STARTED,
                (self._svc_name_, '')
            )

            try:
                # Start the service wrapper
                self.service_wrapper.start()

                # Wait for stop event
                win32event.WaitForSingleObject(self.hWaitStop, win32event.INFINITE)

                servicemanager.LogMsg(
                    servicemanager.EVENTLOG_INFORMATION_TYPE,
                    servicemanager.PYS_SERVICE_STOPPED,
                    (self._svc_name_, '')
                )

            except Exception as e:
                servicemanager.LogErrorMsg(f"Service failed: {e}")
                raise


def install_service(config_path: Optional[str] = None, auto_start: bool = True):
    """Install the Windows service."""
    if not WIN32_AVAILABLE:
        raise RuntimeError("pywin32 not available - cannot install Windows service")

    # Build command line
    cmd_line = [sys.executable, __file__]
    if config_path:
        cmd_line.extend(["--config", config_path])

    # Install service
    win32serviceutil.InstallService(
        TLSCertMonitorWindowsService._svc_name_,
        TLSCertMonitorWindowsService._svc_display_name_,
        cmdLine=' '.join(cmd_line),
        startType=win32service.SERVICE_AUTO_START if auto_start else win32service.SERVICE_DEMAND_START,
        description=TLSCertMonitorWindowsService._svc_description_
    )


def uninstall_service():
    """Uninstall the Windows service."""
    if not WIN32_AVAILABLE:
        raise RuntimeError("pywin32 not available - cannot uninstall Windows service")

    win32serviceutil.RemoveService(TLSCertMonitorWindowsService._svc_name_)


def start_service():
    """Start the Windows service."""
    if not WIN32_AVAILABLE:
        raise RuntimeError("pywin32 not available - cannot start Windows service")

    win32serviceutil.StartService(TLSCertMonitorWindowsService._svc_name_)


def stop_service():
    """Stop the Windows service."""
    if not WIN32_AVAILABLE:
        raise RuntimeError("pywin32 not available - cannot stop Windows service")

    win32serviceutil.StopService(TLSCertMonitorWindowsService._svc_name_)


def service_status():
    """Get Windows service status."""
    if not WIN32_AVAILABLE:
        raise RuntimeError("pywin32 not available - cannot check service status")

    return win32serviceutil.QueryServiceStatus(TLSCertMonitorWindowsService._svc_name_)


if __name__ == "__main__":
    if WIN32_AVAILABLE:
        win32serviceutil.HandleCommandLine(TLSCertMonitorWindowsService)
    else:
        print("ERROR: pywin32 not available - Windows service support disabled")
        sys.exit(1)