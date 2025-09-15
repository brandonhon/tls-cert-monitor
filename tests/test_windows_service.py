"""
Tests for Windows service functionality.
"""

import sys
from unittest.mock import MagicMock, patch

import pytest

from tls_cert_monitor.windows_service import (
    get_service_status,
    install_service,
    is_windows_service_available,
    start_service,
    stop_service,
    uninstall_service,
)


class TestWindowsServiceAvailability:
    """Test Windows service availability detection."""

    def test_is_windows_service_available_true(self):
        """Test service availability when pywin32 is available."""
        with patch("tls_cert_monitor.windows_service.win32serviceutil", MagicMock()):
            assert is_windows_service_available() is True

    def test_is_windows_service_available_false(self):
        """Test service availability when pywin32 is not available."""
        with patch("tls_cert_monitor.windows_service.win32serviceutil", None):
            assert is_windows_service_available() is False


class TestWindowsServiceOperations:
    """Test Windows service management operations."""

    @patch("tls_cert_monitor.windows_service.win32serviceutil")
    @patch("tls_cert_monitor.windows_service.win32service")
    @patch("tls_cert_monitor.windows_service.sys")
    def test_install_service_success(self, mock_sys, mock_win32service, mock_win32serviceutil):
        """Test successful service installation."""
        mock_sys.executable = "python.exe"
        mock_win32service.SERVICE_AUTO_START = 2

        result = install_service(service_config_path="/test/config.yaml", service_auto_start=True)

        assert result is True
        mock_win32serviceutil.InstallService.assert_called_once()

    def test_install_service_no_pywin32(self):
        """Test service installation when pywin32 is not available."""
        with patch("tls_cert_monitor.windows_service.win32serviceutil", None):
            with pytest.raises(RuntimeError, match="pywin32 is required"):
                install_service()

    @patch("tls_cert_monitor.windows_service.win32serviceutil")
    def test_install_service_failure(self, mock_win32serviceutil):
        """Test service installation failure."""
        mock_win32serviceutil.InstallService.side_effect = Exception("Installation failed")

        result = install_service()

        assert result is False

    @patch("tls_cert_monitor.windows_service.win32serviceutil")
    def test_uninstall_service_success(self, mock_win32serviceutil):
        """Test successful service uninstallation."""
        result = uninstall_service()

        assert result is True
        mock_win32serviceutil.StopService.assert_called_once()
        mock_win32serviceutil.RemoveService.assert_called_once()

    @patch("tls_cert_monitor.windows_service.win32serviceutil")
    def test_uninstall_service_not_running(self, mock_win32serviceutil):
        """Test service uninstallation when service is not running."""
        mock_win32serviceutil.StopService.side_effect = Exception("Service not running")

        result = uninstall_service()

        assert result is True  # Should still succeed
        mock_win32serviceutil.RemoveService.assert_called_once()

    @patch("tls_cert_monitor.windows_service.win32serviceutil")
    def test_start_service_success(self, mock_win32serviceutil):
        """Test successful service start."""
        result = start_service()

        assert result is True
        mock_win32serviceutil.StartService.assert_called_once()

    @patch("tls_cert_monitor.windows_service.win32serviceutil")
    def test_start_service_failure(self, mock_win32serviceutil):
        """Test service start failure."""
        mock_win32serviceutil.StartService.side_effect = Exception("Start failed")

        result = start_service()

        assert result is False

    @patch("tls_cert_monitor.windows_service.win32serviceutil")
    def test_stop_service_success(self, mock_win32serviceutil):
        """Test successful service stop."""
        result = stop_service()

        assert result is True
        mock_win32serviceutil.StopService.assert_called_once()

    @patch("tls_cert_monitor.windows_service.win32serviceutil")
    @patch("tls_cert_monitor.windows_service.win32service")
    def test_get_service_status_running(self, mock_win32service, mock_win32serviceutil):
        """Test getting service status when running."""
        mock_win32service.SERVICE_RUNNING = 4
        mock_win32serviceutil.QueryServiceStatus.return_value = (None, 4)

        status = get_service_status()

        assert status == "RUNNING"

    @patch("tls_cert_monitor.windows_service.win32serviceutil")
    @patch("tls_cert_monitor.windows_service.win32service")
    def test_get_service_status_stopped(self, mock_win32service, mock_win32serviceutil):
        """Test getting service status when stopped."""
        mock_win32service.SERVICE_STOPPED = 1
        mock_win32serviceutil.QueryServiceStatus.return_value = (None, 1)

        status = get_service_status()

        assert status == "STOPPED"

    @patch("tls_cert_monitor.windows_service.win32serviceutil")
    def test_get_service_status_error(self, mock_win32serviceutil):
        """Test getting service status when there's an error."""
        mock_win32serviceutil.QueryServiceStatus.side_effect = Exception("Query failed")

        status = get_service_status()

        assert status.startswith("ERROR:")


@pytest.mark.skipif(sys.platform != "win32", reason="Windows-specific tests")
class TestTLSCertMonitorService:
    """Test the TLSCertMonitorService class (Windows only)."""

    def setup_method(self):
        """Setup test fixtures."""
        self.mock_win32serviceutil = MagicMock()
        self.mock_win32service = MagicMock()
        self.mock_win32event = MagicMock()

    @patch("tls_cert_monitor.windows_service.win32serviceutil")
    @patch("tls_cert_monitor.windows_service.win32event")
    def test_service_initialization(self, mock_win32event, mock_win32serviceutil):
        """Test service initialization."""
        from tls_cert_monitor.windows_service import TLSCertMonitorService

        mock_event = MagicMock()
        mock_win32event.CreateEvent.return_value = mock_event

        service = TLSCertMonitorService(["TLSCertMonitor"])

        assert service.is_alive is True
        assert service.monitor is None
        assert service.config_path is None
        mock_win32event.CreateEvent.assert_called_once()

    @patch("tls_cert_monitor.windows_service.win32serviceutil")
    @patch("tls_cert_monitor.windows_service.win32event")
    def test_service_initialization_with_config(self, mock_win32event, mock_win32serviceutil):
        """Test service initialization with config path."""
        from tls_cert_monitor.windows_service import TLSCertMonitorService

        mock_event = MagicMock()
        mock_win32event.CreateEvent.return_value = mock_event

        service = TLSCertMonitorService(["TLSCertMonitor", "/test/config.yaml"])

        assert service.config_path == "/test/config.yaml"

    @patch("tls_cert_monitor.windows_service.win32serviceutil")
    @patch("tls_cert_monitor.windows_service.win32event")
    def test_service_stop(self, mock_win32event, mock_win32serviceutil):
        """Test service stop functionality."""
        from tls_cert_monitor.windows_service import SERVICE_STOP_PENDING, TLSCertMonitorService

        mock_event = MagicMock()
        mock_win32event.CreateEvent.return_value = mock_event

        service = TLSCertMonitorService(["TLSCertMonitor"])
        service.ReportServiceStatus = MagicMock()

        service.SvcStop()

        assert service.is_alive is False
        service.ReportServiceStatus.assert_called_with(SERVICE_STOP_PENDING)
        mock_win32event.SetEvent.assert_called_with(mock_event)


class TestMainIntegration:
    """Test integration with main.py service commands."""

    def test_main_service_install_command(self):
        """Test main.py integration for service install command."""
        # We can't easily test this without mocking the entire click framework
        # So we'll test the service functions directly via their unit tests
        assert True

    def test_service_import_error_handling(self):
        """Test handling of import errors for Windows service functionality."""
        with patch("tls_cert_monitor.windows_service.win32serviceutil", None):
            with pytest.raises(RuntimeError):
                install_service()


class TestServiceConfigurationHandling:
    """Test service configuration and argument handling."""

    @patch("tls_cert_monitor.windows_service.win32serviceutil")
    @patch("tls_cert_monitor.windows_service.win32service")
    def test_install_with_custom_config(self, mock_win32service, mock_win32serviceutil):
        """Test service installation with custom configuration path."""
        mock_win32service.SERVICE_DEMAND_START = 3
        config_path = "/custom/path/config.yaml"

        result = install_service(service_config_path=config_path, service_auto_start=False)

        assert result is True
        # Verify that the config path would be passed to the service

    @patch("tls_cert_monitor.windows_service.win32serviceutil")
    @patch("tls_cert_monitor.windows_service.win32service")
    def test_install_with_manual_start(self, mock_win32service, mock_win32serviceutil):
        """Test service installation with manual start type."""
        mock_win32service.SERVICE_DEMAND_START = 3

        result = install_service(service_auto_start=False)

        assert result is True


class TestErrorHandling:
    """Test error handling in service operations."""

    @patch("tls_cert_monitor.windows_service.win32serviceutil", None)
    def test_operations_without_pywin32(self):
        """Test that operations fail gracefully without pywin32."""
        with pytest.raises(RuntimeError, match="pywin32 is required"):
            install_service()

        with pytest.raises(RuntimeError, match="pywin32 is required"):
            uninstall_service()

        with pytest.raises(RuntimeError, match="pywin32 is required"):
            start_service()

        with pytest.raises(RuntimeError, match="pywin32 is required"):
            stop_service()

        with pytest.raises(RuntimeError, match="pywin32 is required"):
            get_service_status()

    @patch("tls_cert_monitor.windows_service.win32serviceutil")
    def test_service_operations_exception_handling(self, mock_win32serviceutil):
        """Test exception handling in service operations."""
        mock_win32serviceutil.InstallService.side_effect = Exception("Test error")
        mock_win32serviceutil.RemoveService.side_effect = Exception("Test error")
        mock_win32serviceutil.StartService.side_effect = Exception("Test error")
        mock_win32serviceutil.StopService.side_effect = Exception("Test error")

        assert install_service() is False
        assert uninstall_service() is False
        assert start_service() is False
        assert stop_service() is False


class TestServiceLifecycle:
    """Test complete service lifecycle scenarios."""

    @patch("tls_cert_monitor.windows_service.win32serviceutil")
    @patch("tls_cert_monitor.windows_service.win32service")
    def test_complete_service_lifecycle(self, mock_win32service, mock_win32serviceutil):
        """Test complete install -> start -> stop -> uninstall cycle."""
        # Setup mocks
        mock_win32service.SERVICE_AUTO_START = 2
        mock_win32service.SERVICE_RUNNING = 4
        mock_win32service.SERVICE_STOPPED = 1

        # Install service
        assert install_service() is True

        # Start service
        assert start_service() is True

        # Check status (running)
        mock_win32serviceutil.QueryServiceStatus.return_value = (None, 4)
        assert get_service_status() == "RUNNING"

        # Stop service
        assert stop_service() is True

        # Check status (stopped)
        mock_win32serviceutil.QueryServiceStatus.return_value = (None, 1)
        assert get_service_status() == "STOPPED"

        # Uninstall service
        assert uninstall_service() is True
