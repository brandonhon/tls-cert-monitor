"""
Standardized logging configuration for TLS Certificate Monitor.
"""

import logging
import logging.handlers
import sys
from pathlib import Path
from typing import Optional

from tls_cert_monitor.config import Config


class CustomFormatter(logging.Formatter):
    """Custom formatter with colored output for console."""

    # Color codes
    COLORS = {
        "DEBUG": "\033[36m",  # Cyan
        "INFO": "\033[32m",  # Green
        "WARNING": "\033[33m",  # Yellow
        "ERROR": "\033[31m",  # Red
        "CRITICAL": "\033[35m",  # Magenta
        "RESET": "\033[0m",  # Reset
    }

    def __init__(self, use_color: bool = True) -> None:
        self.use_color = use_color
        super().__init__()

    def format(self, record: logging.LogRecord) -> str:
        """Format log record with optional colors."""
        # Create format string
        if self.use_color and record.levelname in self.COLORS:
            color = self.COLORS[record.levelname]
            reset = self.COLORS["RESET"]
            level_name = f"{color}{record.levelname:<8}{reset}"
        else:
            level_name = f"{record.levelname:<8}"

        # Format timestamp
        timestamp = self.formatTime(record, "%Y-%m-%d %H:%M:%S")

        # Format message
        message = record.getMessage()

        # Add exception info if present
        if record.exc_info:
            if not message.endswith("\n"):
                message += "\n"
            message += self.formatException(record.exc_info)

        # Construct final log line
        log_line = f"{timestamp} | {level_name} | {record.name:<20} | {message}"

        return log_line


class StructuredFormatter(logging.Formatter):
    """JSON formatter for structured logging."""

    def format(self, record: logging.LogRecord) -> str:
        """Format log record as JSON."""
        import json
        from datetime import datetime

        log_data = {
            "timestamp": datetime.fromtimestamp(record.created).isoformat(),
            "level": record.levelname,
            "logger": record.name,
            "message": record.getMessage(),
            "module": record.module,
            "function": record.funcName,
            "line": record.lineno,
        }

        # Add extra fields
        if hasattr(record, "cert_path"):
            log_data["cert_path"] = record.cert_path
        if hasattr(record, "scan_duration"):
            log_data["scan_duration"] = record.scan_duration
        if hasattr(record, "error_type"):
            log_data["error_type"] = record.error_type

        # Add exception info
        if record.exc_info:
            log_data["exception"] = self.formatException(record.exc_info)

        return json.dumps(log_data, ensure_ascii=False)


def setup_logging(config: Config) -> None:
    """
    Setup logging configuration.

    Args:
        config: Configuration object
    """
    # Get root logger
    root_logger = logging.getLogger()
    root_logger.setLevel(getattr(logging, config.log_level))

    # Clear existing handlers
    root_logger.handlers.clear()

    # Console handler
    console_handler = logging.StreamHandler(sys.stdout)
    console_handler.setLevel(getattr(logging, config.log_level))

    # Use colored formatter for console if output is a TTY
    use_color = hasattr(sys.stdout, "isatty") and sys.stdout.isatty()
    console_formatter = CustomFormatter(use_color=use_color)
    console_handler.setFormatter(console_formatter)
    root_logger.addHandler(console_handler)

    # File handler if log file is specified
    if config.log_file:
        log_path = Path(config.log_file)
        log_path.parent.mkdir(parents=True, exist_ok=True)

        # Rotating file handler (10MB max, 5 backups)
        file_handler = logging.handlers.RotatingFileHandler(
            config.log_file, maxBytes=10 * 1024 * 1024, backupCount=5, encoding="utf-8"  # 10MB
        )
        file_handler.setLevel(getattr(logging, config.log_level))

        # Use structured formatter for file logging
        file_formatter = StructuredFormatter()
        file_handler.setFormatter(file_formatter)
        root_logger.addHandler(file_handler)

    # Set specific logger levels
    logging.getLogger("uvicorn").setLevel(logging.WARNING)
    logging.getLogger("watchdog").setLevel(logging.WARNING)

    # Create application logger
    app_logger = logging.getLogger("tls_cert_monitor")
    app_logger.info(f"Logging initialized - Level: {config.log_level}")

    if config.log_file:
        app_logger.info(f"Log file: {config.log_file}")


def get_logger(name: str) -> logging.Logger:
    """
    Get a logger instance.

    Args:
        name: Logger name

    Returns:
        Logger instance
    """
    return logging.getLogger(f"tls_cert_monitor.{name}")


# Logging helpers for certificate operations
def log_cert_scan_start(logger: logging.Logger, directory: str, file_count: int) -> None:
    """Log certificate scan start."""
    logger.info(
        "Starting certificate scan", extra={"directory": directory, "file_count": file_count}
    )


def log_cert_parsed(
    logger: logging.Logger, cert_path: str, common_name: str, expires_in_days: int
) -> None:
    """Log successful certificate parsing."""
    logger.debug(
        "Certificate parsed successfully",
        extra={
            "cert_path": cert_path,
            "common_name": common_name,
            "expires_in_days": expires_in_days,
        },
    )


def log_cert_error(
    logger: logging.Logger, cert_path: str, error: Exception, error_type: str = "parse_error"
) -> None:
    """Log certificate processing error."""
    logger.error(
        f"Certificate processing failed: {error}",
        extra={"cert_path": cert_path, "error_type": error_type},
    )


def log_cert_scan_complete(
    logger: logging.Logger, directory: str, duration: float, parsed: int, errors: int
) -> None:
    """Log certificate scan completion."""
    logger.info(
        "Certificate scan completed",
        extra={
            "directory": directory,
            "scan_duration": duration,
            "certificates_parsed": parsed,
            "parse_errors": errors,
        },
    )


def log_cache_operation(
    logger: logging.Logger, operation: str, key: str, hit: Optional[bool] = None
) -> None:
    """Log cache operations."""
    extra: dict = {"cache_operation": operation, "cache_key": key}
    if hit is not None:
        extra["cache_hit"] = hit

    if operation == "hit":
        logger.debug(f"Cache hit for key: {key}", extra=extra)
    elif operation == "miss":
        logger.debug(f"Cache miss for key: {key}", extra=extra)
    elif operation == "set":
        logger.debug(f"Cache set for key: {key}", extra=extra)
    elif operation == "invalidate":
        logger.debug(f"Cache invalidated for key: {key}", extra=extra)


def log_hot_reload(logger: logging.Logger, file_path: str, event_type: str) -> None:
    """Log hot reload events."""
    logger.debug(
        f"Hot reload triggered: {event_type}",
        extra={"file_path": file_path, "reload_event": event_type},
    )


def log_metrics_collection(
    logger: logging.Logger, metric_name: str, value: float, labels: Optional[dict] = None
) -> None:
    """Log metrics collection."""
    extra = {"metric_name": metric_name, "metric_value": value}
    if labels:
        extra["metric_labels"] = labels

    logger.debug(f"Metric collected: {metric_name}={value}", extra=extra)
