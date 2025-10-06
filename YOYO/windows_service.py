import os
import time
from datetime import datetime

import servicemanager
import win32event
import win32service
import win32serviceutil


class SimpleLoggingService(win32serviceutil.ServiceFramework):
    _svc_name_ = "SimpleLoggingService"
    _svc_display_name_ = "Simple Logging Service"
    _svc_description_ = "Logs a message to a text file every 3 minutes"

    def __init__(self, args):
        win32serviceutil.ServiceFramework.__init__(self, args)
        self.stop_event = win32event.CreateEvent(None, 0, 0, None)
        self.running = True

        # Set log file path to the same directory as the script
        script_dir = os.path.dirname(os.path.abspath(__file__))
        self.log_file = os.path.join(script_dir, "service_log.txt")

    def SvcStop(self):
        self.ReportServiceStatus(win32service.SERVICE_STOP_PENDING)
        win32event.SetEvent(self.stop_event)
        self.running = False

    def SvcDoRun(self):
        servicemanager.LogMsg(
            servicemanager.EVENTLOG_INFORMATION_TYPE,
            servicemanager.PYS_SERVICE_STARTED,
            (self._svc_name_, ""),
        )
        self.main()

    def main(self):
        while self.running:
            # Log current timestamp
            timestamp = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
            log_message = f"[{timestamp}] Service is running\n"

            try:
                with open(self.log_file, "a") as f:
                    f.write(log_message)
            except Exception as e:
                servicemanager.LogErrorMsg(f"Error writing to log: {str(e)}")

            # Wait for 3 minutes (180 seconds) or until stop event
            result = win32event.WaitForSingleObject(self.stop_event, 180000)
            if result == win32event.WAIT_OBJECT_0:
                break


if __name__ == "__main__":
    win32serviceutil.HandleCommandLine(SimpleLoggingService)
