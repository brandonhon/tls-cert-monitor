"""
Simplified API tests to verify basic functionality.
"""

import pytest

from tls_cert_monitor.api import create_app


class TestAPI:
    """Test API basic functionality."""

    def test_api_import(self):
        """Test that API module can be imported successfully."""
        assert create_app is not None

    def test_create_app_function_exists(self):
        """Test that create_app function exists and is callable."""
        assert callable(create_app)
        # Just verify the function exists and has the expected signature
        import inspect
        sig = inspect.signature(create_app)
        assert "scanner" in sig.parameters
        assert "metrics" in sig.parameters
        assert "cache" in sig.parameters
        assert "config" in sig.parameters