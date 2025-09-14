"""
FastAPI application for TLS Certificate Monitor.
"""

import asyncio
import ipaddress
import os
import shutil
from contextlib import asynccontextmanager
from typing import Any, AsyncGenerator, Awaitable, Callable, Dict, Optional, Union

from fastapi import FastAPI, HTTPException, Request, Response
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse, PlainTextResponse

from tls_cert_monitor import __version__
from tls_cert_monitor.cache import CacheManager
from tls_cert_monitor.config import Config
from tls_cert_monitor.logger import get_logger
from tls_cert_monitor.metrics import MetricsCollector
from tls_cert_monitor.scanner import CertificateScanner


@asynccontextmanager
async def lifespan(_app: FastAPI) -> AsyncGenerator[None, None]:
    """Lifespan handler that suppresses CancelledError during shutdown."""
    try:
        # Startup
        yield
    except asyncio.CancelledError:
        # Suppress CancelledError during shutdown - this is expected behavior
        pass
    finally:
        # Cleanup - suppress any cancellation errors here too
        try:
            pass  # Any cleanup code would go here
        except asyncio.CancelledError:
            pass


def create_app(
    scanner: CertificateScanner,
    metrics: MetricsCollector,
    cache: CacheManager,
    config: Config,
    lifespan_override: Optional[Any] = None,
) -> FastAPI:
    """
    Create and configure FastAPI application.

    Args:
        scanner: Certificate scanner instance
        metrics: Metrics collector instance
        cache: Cache manager instance
        config: Configuration instance

    Returns:
        Configured FastAPI application
    """
    app = FastAPI(
        title="TLS Certificate Monitor",
        description="Cross-platform TLS certificate monitoring application",
        version=__version__,
        docs_url="/docs" if not config.dry_run else None,
        redoc_url="/redoc" if not config.dry_run else None,
        lifespan=lifespan_override or lifespan,
    )

    app.add_middleware(
        CORSMiddleware,
        allow_origins=["*"],
        allow_credentials=True,
        allow_methods=["*"],
        allow_headers=["*"],
    )

    logger = get_logger("api")

    @app.middleware("http")
    async def ip_whitelist_middleware(
        request: Request, call_next: Callable[[Request], Awaitable[Response]]
    ) -> Response:
        """Middleware to enforce IP whitelisting."""
        if not config.enable_ip_whitelist:
            # IP whitelisting is disabled, allow all requests
            response = await call_next(request)
            return response

        # Get client IP address
        client_ip = request.client.host if request.client else None

        # Handle case where client IP is not available (e.g., in tests)
        if not client_ip:
            logger.warning("Unable to determine client IP address, allowing request")
            response = await call_next(request)
            return response

        # Check if client IP is in allowed list
        is_allowed = False
        for allowed_ip in config.allowed_ips:
            try:
                if "/" in allowed_ip:
                    # CIDR notation - check if client IP is in network
                    network = ipaddress.ip_network(allowed_ip, strict=False)
                    if ipaddress.ip_address(client_ip) in network:
                        is_allowed = True
                        break
                else:
                    # Single IP address
                    if client_ip == allowed_ip:
                        is_allowed = True
                        break
            except (ipaddress.AddressValueError, ValueError) as e:
                logger.warning(f"Invalid IP configuration '{allowed_ip}': {e}")
                continue

        if not is_allowed:
            logger.warning(f"Access denied for IP address: {client_ip}")
            return JSONResponse(
                status_code=403,
                content={
                    "error": "Access forbidden",
                    "message": "Your IP address is not allowed to access this service",
                    "client_ip": client_ip,
                },
            )

        # IP is allowed, proceed with request
        logger.debug(f"Access granted for IP address: {client_ip}")
        response = await call_next(request)
        return response

    @app.get("/metrics", response_class=PlainTextResponse)
    async def get_metrics() -> PlainTextResponse:
        try:
            metrics_data: str = metrics.get_metrics()
            return PlainTextResponse(content=metrics_data, media_type=metrics.get_content_type())
        except Exception as e:
            logger.error(f"Failed to generate metrics: {e}")
            raise HTTPException(status_code=500, detail="Failed to generate metrics") from e

    @app.get("/healthz", response_class=JSONResponse)
    async def get_health() -> JSONResponse:
        try:
            scanner_health = await scanner.get_health_status()
            cache_health = await cache.get_health_status()
            metrics_health = metrics.get_registry_status()
            system_health = await _get_system_health(scanner.config)

            health_status = {
                **scanner_health,
                **cache_health,
                **metrics_health,
                **system_health,
                "status": "healthy",
                "version": __version__,
            }

            return JSONResponse(content=health_status)
        except Exception as e:
            logger.error(f"Failed to get health status: {e}")
            return JSONResponse(content={"status": "error", "error": str(e)}, status_code=500)

    @app.get("/scan", response_class=JSONResponse)
    async def trigger_scan() -> JSONResponse:
        if scanner.config.dry_run:
            return JSONResponse(
                content={"message": "Scan not performed - dry run mode enabled"}, status_code=200
            )
        try:
            logger.info("Manual scan triggered via API")
            scan_results = await scanner.scan_once()
            return JSONResponse(content=scan_results)
        except Exception as e:
            logger.error(f"Manual scan failed: {e}")
            raise HTTPException(status_code=500, detail=f"Scan failed: {e}") from e

    @app.get("/config", response_class=JSONResponse)
    async def get_config() -> JSONResponse:
        try:
            # Use current config from scanner (updated by hot reload)
            current_config = scanner.config
            config_dict: Dict[str, Any] = current_config.dict()

            # Always redact sensitive information
            sensitive_keys = ["p12_passwords", "tls_key", "allowed_ips"]
            for key in sensitive_keys:
                if key in config_dict:
                    if key == "p12_passwords":
                        config_dict[key] = [f"***REDACTED*** ({len(config_dict[key])} passwords)"]
                    elif key == "allowed_ips":
                        config_dict[key] = [
                            f"***REDACTED*** ({len(config_dict[key])} IPs/networks)"
                        ]
                    else:
                        config_dict[key] = "***REDACTED***"

            # Mask certificate directory paths to prevent information disclosure
            if "certificate_directories" in config_dict:
                masked_dirs = []
                for dir_path in config_dict["certificate_directories"]:
                    # Show only the basename, not full paths
                    from pathlib import Path

                    masked_dirs.append(f"***/{Path(dir_path).name}")
                config_dict["certificate_directories"] = masked_dirs

            return JSONResponse(content=config_dict)
        except Exception as e:
            logger.error(f"Failed to get configuration: {e}")
            raise HTTPException(status_code=500, detail="Failed to get configuration") from e

    @app.get("/cache/stats", response_class=JSONResponse)
    async def get_cache_stats() -> JSONResponse:
        try:
            stats = await cache.get_stats()
            return JSONResponse(content=stats)
        except Exception as e:
            logger.error(f"Failed to get cache stats: {e}")
            raise HTTPException(status_code=500, detail="Failed to get cache stats") from e

    @app.post("/cache/clear", response_class=JSONResponse)
    async def clear_cache() -> JSONResponse:
        if scanner.config.dry_run:
            return JSONResponse(
                content={"message": "Cache not cleared - dry run mode enabled"}, status_code=200
            )
        try:
            await cache.clear()
            logger.info("Cache cleared via API")
            return JSONResponse(content={"message": "Cache cleared successfully"})
        except Exception as e:
            logger.error(f"Failed to clear cache: {e}")
            raise HTTPException(status_code=500, detail="Failed to clear cache") from e

    @app.get("/favicon.ico")
    async def get_favicon() -> Response:
        """Serve favicon."""
        # Simple SVG lock icon
        favicon_svg = """<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 32 32" width="32" height="32">
        <defs>
            <linearGradient id="lg" x1="0%" y1="0%" x2="100%" y2="100%">
                <stop offset="0%" style="stop-color:#ffd700"/>
                <stop offset="100%" style="stop-color:#ffb347"/>
            </linearGradient>
        </defs>
        <!-- Padlock body with golden color like 🔒 emoji -->
        <rect x="8" y="15" width="16" height="14" rx="2" fill="url(#lg)" stroke="#d4911a" stroke-width="1.5"/>
        <!-- Padlock shackle -->
        <path d="M 12 15 L 12 10 Q 12 5 16 5 Q 20 5 20 10 L 20 15"
              fill="none" stroke="#d4911a" stroke-width="2.5" stroke-linecap="round"/>
        <!-- Keyhole -->
        <circle cx="16" cy="21" r="2" fill="#d4911a"/>
        <rect x="15" y="21" width="2" height="4" fill="#d4911a" rx="1"/>
        <!-- Highlight for 3D effect -->
        <rect x="10" y="17" width="4" height="1.5" rx="0.75" fill="#ffffff" opacity="0.6"/>
        </svg>"""
        return Response(content=favicon_svg, media_type="image/svg+xml")

    @app.get("/", response_class=Response)
    async def root() -> Response:
        # Get current config from scanner to reflect hot reload changes
        current_config = scanner.config
        protocol = "https" if current_config.tls_cert and current_config.tls_key else "http"
        server_url = f"{protocol}://{current_config.bind_address}:{current_config.port}"
        html_content = f"""
        <!DOCTYPE html>
<html>
<head>
    <title>TLS Certificate Monitor</title>
    <meta charset="utf-8">
    <meta name="viewport" content="width=device-width, initial-scale=1">
    <style>
        body {{
            font-family: -apple-system, BlinkMacSystemFont, "Segoe UI", Roboto, "Helvetica Neue", Arial, sans-serif;
            max-width: 1000px;
            margin: 50px auto;
            padding: 20px;
            background: #f5f5f5;
            line-height: 1.6;
        }}
        h1 {{
            color: #333;
            border-bottom: 3px solid #4CAF50;
            padding-bottom: 15px;
            margin-bottom: 30px;
        }}
        h2 {{
            color: #555;
            margin-top: 30px;
            margin-bottom: 15px;
        }}
        .container {{
            background: white;
            border-radius: 12px;
            padding: 30px;
            box-shadow: 0 4px 6px rgba(0,0,0,0.1);
            margin-bottom: 20px;
        }}
        .endpoint {{
            margin: 20px 0;
            padding: 15px;
            background: #f9f9f9;
            border-left: 5px solid #4CAF50;
            border-radius: 0 8px 8px 0;
            transition: background-color 0.3s ease;
        }}
        .endpoint:hover {{
            background: #f0f8f0;
        }}
        .endpoint-title {{
            font-size: 18px;
            font-weight: bold;
            margin-bottom: 8px;
        }}
        .endpoint-description {{
            color: #666;
            margin-bottom: 10px;
        }}
        .endpoint-method {{
            display: inline-block;
            background: #4CAF50;
            color: white;
            padding: 3px 8px;
            border-radius: 4px;
            font-size: 12px;
            font-weight: bold;
            margin-right: 10px;
        }}
        .endpoint-method.post {{
            background: #FF9800;
        }}
        a {{
            color: #4CAF50;
            text-decoration: none;
            font-weight: 500;
        }}
        a:hover {{
            text-decoration: underline;
        }}
        code {{
            background: #e8e8e8;
            padding: 3px 8px;
            border-radius: 4px;
            font-family: "Monaco", "Menlo", "Ubuntu Mono", monospace;
            font-size: 14px;
        }}
        .config-grid {{
            display: grid;
            grid-template-columns: repeat(auto-fit, minmax(250px, 1fr));
            gap: 15px;
            margin-top: 15px;
        }}
        .config-item {{
            background: #f9f9f9;
            padding: 12px;
            border-radius: 6px;
            border-left: 3px solid #4CAF50;
        }}
        .config-label {{
            font-weight: bold;
            color: #333;
            margin-bottom: 5px;
        }}
        .config-value {{
            font-family: "Monaco", "Menlo", "Ubuntu Mono", monospace;
            background: #fff;
            padding: 6px;
            border-radius: 3px;
            border: 1px solid #ddd;
        }}
        .status-indicator {{
            display: inline-block;
            width: 12px;
            height: 12px;
            border-radius: 50%;
            margin-right: 8px;
        }}
        .status-running {{
            background: #4CAF50;
        }}
        .status-warning {{
            background: #FF9800;
        }}
        .footer {{
            text-align: center;
            margin-top: 30px;
            color: #666;
            font-size: 14px;
        }}
    </style>
</head>
<body>
    <h1>🔒 TLS Certificate Monitor v{__version__}</h1>

    <div class="container">
        <h2>📊 Monitoring Endpoints</h2>

        <div class="endpoint">
            <div class="endpoint-title">
                <span class="endpoint-method">GET</span>
                <a href="/metrics" target="_blank">/metrics</a>
            </div>
            <div class="endpoint-description">
                Prometheus metrics endpoint for certificate monitoring, security analysis, and application performance
            </div>
            <small>Content-Type: text/plain; version=0.0.4; charset=utf-8</small>
        </div>

        <div class="endpoint">
            <div class="endpoint-title">
                <span class="endpoint-method">GET</span>
                <a href="/healthz" target="_blank">/healthz</a>
            </div>
            <div class="endpoint-description">
                Health check endpoint with detailed system status, cache information, and disk usage
            </div>
            <small>Content-Type: application/json</small>
        </div>
    </div>

    <div class="container">
        <h2>🔧 Management Endpoints</h2>

        <div class="endpoint">
            <div class="endpoint-title">
                <span class="endpoint-method">GET</span>
                <a href="/scan" target="_blank">/scan</a>
            </div>
            <div class="endpoint-description">
                Trigger a manual certificate scan and get detailed results
            </div>
            <small>Returns scan results including parsed certificates, errors, and timing</small>
        </div>

        <div class="endpoint">
            <div class="endpoint-title">
                <span class="endpoint-method">GET</span>
                <a href="/config" target="_blank">/config</a>
            </div>
            <div class="endpoint-description">
                View current configuration (sensitive data redacted)
            </div>
            <small>Shows all configuration settings except passwords and keys</small>
        </div>

        <div class="endpoint">
            <div class="endpoint-title">
                <span class="endpoint-method">GET</span>
                <a href="/cache/stats" target="_blank">/cache/stats</a>
            </div>
            <div class="endpoint-description">
                Cache performance statistics and hit rates
            </div>
            <small>Includes hit rate, entry count, and memory usage</small>
        </div>

        <div class="endpoint">
            <div class="endpoint-title">
                <span class="endpoint-method post">POST</span>
                <a href="#" onclick="clearCache(); return false;">/cache/clear</a>
            </div>
            <div class="endpoint-description">
                Clear the application cache (requires POST request)
            </div>
            <small>Click to clear cache via JavaScript POST request</small>
        </div>
    </div>

    <div class="container">
        <h2>⚙️ Current Configuration</h2>
        <div class="config-grid">
            <div class="config-item">
                <div class="config-label">Server Status</div>
                <div class="config-value">
                    <span class="status-indicator status-running"></span>Running
                </div>
            </div>
            <div class="config-item">
                <div class="config-label">Server Address</div>
                <div class="config-value">{server_url}</div>
            </div>
            <div class="config-item">
                <div class="config-label">TLS Enabled</div>
                <div class="config-value">{'Yes' if current_config.tls_cert and current_config.tls_key else 'No'}</div>
            </div>
            <div class="config-item">
                <div class="config-label">Workers</div>
                <div class="config-value">{current_config.workers}</div>
            </div>
            <div class="config-item">
                <div class="config-label">Scan Interval</div>
                <div class="config-value">{current_config.scan_interval}</div>
            </div>
            <div class="config-item">
                <div class="config-label">Hot Reload</div>
                <div class="config-value">{'Enabled' if current_config.hot_reload else 'Disabled'}</div>
            </div>
            <div class="config-item">
                <div class="config-label">Cache Type</div>
                <div class="config-value">{current_config.cache_type.title()}</div>
            </div>
            <div class="config-item">
                <div class="config-label">Cache Directory</div>
                <div class="config-value">{current_config.cache_dir if current_config.cache_type in ('file', 'both') else 'N/A (memory only)'}</div>
            </div>
            <div class="config-item">
                <div class="config-label">Cache TTL</div>
                <div class="config-value">{current_config.cache_ttl}</div>
            </div>
            <div class="config-item">
                <div class="config-label">Cache Max Size</div>
                <div class="config-value">{current_config.cache_max_size // 1024 // 1024}MB</div>
            </div>
            <div class="config-item">
                <div class="config-label">Log Level</div>
                <div class="config-value">{current_config.log_level}</div>
            </div>
        </div>

        <h3>📂 Monitored Directories</h3>
        <div style="margin-top: 15px;">
            {"".join(f'<div style="background: #f0f8f0; padding: 10px; margin: 5px 0; border-radius: 5px; border-left: 3px solid #4CAF50;"><code>{directory}</code></div>' for directory in current_config.certificate_directories)}
        </div>

        {f'''
        <h3>🚫 Excluded Directories</h3>
        <div style="margin-top: 15px;">
            {"".join(f'<div style="background: #fef2f2; padding: 10px; margin: 5px 0; border-radius: 5px; border-left: 3px solid #ef4444;"><code>{directory}</code></div>' for directory in current_config.exclude_directories)}
        </div>
        ''' if current_config.exclude_directories else ''}

        {f'''
        <h3>🔍 Excluded File Patterns</h3>
        <div style="margin-top: 15px;">
            {"".join(f'<div style="background: #fff4e6; padding: 10px; margin: 5px 0; border-radius: 5px; border-left: 3px solid #ff8c00;"><code>{pattern}</code></div>' for pattern in current_config.exclude_file_patterns)}
        </div>
        ''' if current_config.exclude_file_patterns else ''}
    </div>

    <div class="footer">
        <p>TLS Certificate Monitor v{__version__} |
           <a href="/docs" target="_blank">API Documentation</a> |
           <a href="https://github.com/brandonhon/tls-cert-monitor" target="_blank">GitHub</a>
        </p>
    </div>

    <script>
        async function clearCache() {{
            if (confirm('Are you sure you want to clear the cache?')) {{
                try {{
                    const response = await fetch('/cache/clear', {{
                        method: 'POST',
                        headers: {{
                            'Content-Type': 'application/json'
                        }}
                    }});
                    const result = await response.json();
                    alert('Cache cleared: ' + result.message);
                }} catch (error) {{
                    alert('Error clearing cache: ' + error.message);
                }}
            }}
        }}

        // Auto-refresh page every 5 minutes to show updated status
        setTimeout(() => {{
            location.reload();
        }}, 300000);
    </script>
</body>
</html>
        """
        return Response(content=html_content, media_type="text/html")

    @app.on_event("startup")
    async def startup_event() -> None:
        logger.info("TLS Certificate Monitor API started")

    @app.on_event("shutdown")
    async def shutdown_event() -> None:
        logger.info("TLS Certificate Monitor API shutting down")

    return app


async def _get_system_health(config: Config) -> Dict[str, Any]:
    health_data: Dict[str, Any] = {}
    try:
        config_file_exists = False
        config_file_writable = False
        if hasattr(config, "_config_file_path") and config._config_file_path:
            config_file_path = config._config_file_path
            config_file_exists = os.path.exists(config_file_path)
            if config_file_exists:
                config_file_writable = os.access(config_file_path, os.W_OK)

        health_data.update(
            {
                "config_file": getattr(config, "_config_file_path", "default"),
                "config_file_exists": config_file_exists,
                "config_file_writable": config_file_writable,
                "hot_reload_enabled": config.hot_reload,
            }
        )

        log_file_writable = True
        if config.log_file:
            log_dir = os.path.dirname(config.log_file)
            log_file_writable = os.access(log_dir if log_dir else ".", os.W_OK)
        health_data["log_file_writable"] = log_file_writable

        for directory in config.certificate_directories:
            try:
                if os.path.exists(directory):
                    usage = shutil.disk_usage(directory)
                    dir_key = directory.replace("/", "_").replace("\\", "_")
                    health_data[f"diskspace_{dir_key}"] = {
                        "total": usage.total,
                        "used": usage.used,
                        "free": usage.free,
                        "percent_used": round((usage.used / usage.total) * 100, 2),
                    }
            except Exception as e:
                dir_key = directory.replace("/", "_").replace("\\", "_")
                health_data[f"diskspace_{dir_key}_error"] = str(e)

        total_disk_usage: list[dict[str, Union[str, int]]] = []
        for directory in config.certificate_directories:
            if os.path.exists(directory):
                usage = shutil.disk_usage(directory)
                total_disk_usage.append(
                    {
                        "directory": directory,
                        "free": int(usage.free),
                        "total": int(usage.total),
                    }
                )

        if total_disk_usage:
            min_free: int = min(int(usage["free"]) for usage in total_disk_usage)
            health_data["diskspace"] = {
                "status": "ok" if min_free > 1024**3 else "warning",
                "min_free_bytes": min_free,
                "directories_checked": len(total_disk_usage),
            }
    except Exception as e:
        health_data["system_health_error"] = str(e)

    return health_data
