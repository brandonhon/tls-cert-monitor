#!/usr/bin/env python3
"""
Development server entry point for TLS Certificate Monitor.
This module provides a FastAPI app instance that uvicorn can discover.
"""

import asyncio
import logging
import os
from contextlib import asynccontextmanager
from typing import AsyncGenerator

from fastapi import FastAPI

from tls_cert_monitor.cache import CacheManager
from tls_cert_monitor.config import load_config
from tls_cert_monitor.hot_reload import HotReloadManager
from tls_cert_monitor.logger import setup_logging
from tls_cert_monitor.metrics import MetricsCollector
from tls_cert_monitor.scanner import CertificateScanner

# Global application state
app_state = {
    "config": None,
    "scanner": None,
    "metrics": None,
    "cache": None,
    "hot_reload": None,
    "logger": None,
}


@asynccontextmanager
async def lifespan(app: FastAPI) -> AsyncGenerator[None, None]:
    """Manage application lifespan with proper async initialization."""
    logger = app_state["logger"]
    try:
        logger.info("Starting async component initialization")

        # Initialize cache
        await app_state["cache"].initialize()

        # Initialize hot reload if enabled
        if app_state["config"].hot_reload:
            config_path = os.getenv("TLS_CONFIG")
            app_state["hot_reload"] = HotReloadManager(
                config=app_state["config"], scanner=app_state["scanner"], config_path=config_path
            )
            await app_state["hot_reload"].start()

        # Start scanner
        await app_state["scanner"].start_scanning()

        logger.info("Development server ready")
        yield

    except asyncio.CancelledError:
        # Suppress CancelledError during shutdown
        pass
    finally:
        logger.info("Shutting down components")

        # Stop hot reload
        if app_state["hot_reload"]:
            await app_state["hot_reload"].stop()

        # Stop scanner
        if app_state["scanner"]:
            await app_state["scanner"].stop()

        # Close cache
        if app_state["cache"]:
            await app_state["cache"].close()


def create_dev_app() -> FastAPI:
    """Create the development FastAPI app with all components."""
    # Allow config path via ENV
    config_path = os.getenv("TLS_CONFIG")

    # Load configuration
    config = load_config(config_path)

    # Setup logging
    setup_logging(config)
    logger = logging.getLogger(__name__)
    logger.info("Initializing development server components")
    if config_path:
        logger.info(f"Using custom config: {config_path}")

    # Initialize components
    metrics = MetricsCollector()
    cache = CacheManager(config)
    scanner = CertificateScanner(config=config, cache=cache, metrics=metrics)

    # Store in global state for lifespan management
    app_state.update(
        {"config": config, "scanner": scanner, "metrics": metrics, "cache": cache, "logger": logger}
    )

    # Create FastAPI app with lifespan
    from tls_cert_monitor.api import create_app

    app = create_app(
        scanner=scanner, metrics=metrics, cache=cache, config=config, lifespan_override=lifespan
    )

    logger.info("Development server components initialized")
    return app


# Create app instance for uvicorn
app = create_dev_app()
