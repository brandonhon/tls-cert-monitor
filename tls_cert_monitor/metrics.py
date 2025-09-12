"""
Prometheus metrics collection for TLS Certificate Monitor.
"""

import socket
import time
from collections import defaultdict
from typing import Any, Dict, List

import psutil
from prometheus_client import (
    CONTENT_TYPE_LATEST,
    CollectorRegistry,
    Gauge,
    Histogram,
    Info,
    generate_latest,
)

from tls_cert_monitor.logger import get_logger, log_metrics_collection


class MetricsCollector:
    """Prometheus metrics collector for TLS certificates and application metrics."""

    def __init__(self) -> None:
        self.logger = get_logger("metrics")
        self.registry = CollectorRegistry()

        # Certificate metrics
        self.ssl_cert_expiration_timestamp = Gauge(
            "ssl_cert_expiration_timestamp",
            "Certificate expiration time (Unix timestamp)",
            ["common_name", "issuer", "path", "serial"],
            registry=self.registry,
        )

        self.ssl_cert_san_count = Gauge(
            "ssl_cert_san_count",
            "Number of Subject Alternative Names",
            ["common_name", "path"],
            registry=self.registry,
        )

        self.ssl_cert_info = Info(
            "ssl_cert_info",
            "Certificate information with labels",
            ["path", "common_name", "issuer", "serial", "subject"],
            registry=self.registry,
        )

        self.ssl_cert_duplicate_count = Gauge(
            "ssl_cert_duplicate_count", "Number of duplicate certificates", registry=self.registry
        )

        # Fixed: Simplified duplicate names metric to avoid label conflicts
        self.ssl_cert_duplicate_names = Info(
            "ssl_cert_duplicate_names",
            "Names of certificates that are duplicates",
            ["serial_number"],  # Changed from 'serial' and removed 'paths'
            registry=self.registry,
        )

        self.ssl_cert_issuer_code = Gauge(
            "ssl_cert_issuer_code",
            "Numeric issuer classification",
            ["common_name", "issuer", "path"],
            registry=self.registry,
        )

        # Cryptographic security metrics
        self.ssl_cert_weak_key_total = Gauge(
            "ssl_cert_weak_key_total",
            "Current count of certificates with weak cryptographic keys",
            registry=self.registry,
        )

        self.ssl_cert_deprecated_sigalg_total = Gauge(
            "ssl_cert_deprecated_sigalg_total",
            "Current count of certificates using deprecated signature algorithms",
            registry=self.registry,
        )

        # Operational metrics
        self.ssl_cert_files_total = Gauge(
            "ssl_cert_files_total",
            "Total certificate files processed",
            ["directory"],
            registry=self.registry,
        )

        self.ssl_certs_parsed_total = Gauge(
            "ssl_certs_parsed_total", "Successfully parsed certificates", registry=self.registry
        )

        self.ssl_cert_parse_errors_total = Gauge(
            "ssl_cert_parse_errors_total",
            "Current count of certificate parsing errors",
            registry=self.registry,
        )

        self.ssl_cert_parse_error_names = Info(
            "ssl_cert_parse_error_names",
            "Names of certificates that have parsing errors",
            ["filename", "error_type", "error_message"],
            registry=self.registry,
        )

        self.ssl_cert_scan_duration_seconds = Histogram(
            "ssl_cert_scan_duration_seconds",
            "Directory scan duration",
            ["directory"],
            registry=self.registry,
        )

        self.ssl_cert_last_scan_timestamp = Gauge(
            "ssl_cert_last_scan_timestamp",
            "Last successful scan time",
            ["directory"],
            registry=self.registry,
        )

        # Application metrics
        self.app_memory_bytes = Gauge(
            "app_memory_bytes",
            "Application memory usage in bytes",
            ["type"],  # rss, vms, shared, etc.
            registry=self.registry,
        )

        self.app_cpu_percent = Gauge(
            "app_cpu_percent", "Application CPU usage percentage", registry=self.registry
        )

        self.app_thread_count = Gauge(
            "app_thread_count", "Number of application threads", registry=self.registry
        )

        self.app_info = Info(
            "app_info",
            "Application information",
            ["hostname", "version", "python_version"],
            registry=self.registry,
        )

        # Internal tracking
        self._duplicate_certificates: Dict[str, List[str]] = defaultdict(list)
        self._current_scan_parse_errors = 0  # Count of parse errors in current scan
        self._current_scan_weak_keys = 0  # Count of weak keys in current scan
        self._current_scan_deprecated_sigalgs = (
            0  # Count of deprecated signature algorithms in current scan
        )
        self._last_system_update = 0.0
        self._system_update_interval = 30  # Update system metrics every 30 seconds

        self.logger.info("Metrics collector initialized")

    def update_certificate_metrics(self, cert_data: Dict[str, Any]) -> None:
        """
        Update certificate-related metrics.

        Args:
            cert_data: Certificate data dictionary
        """
        try:
            common_name = cert_data.get("common_name", "unknown")
            issuer = cert_data.get("issuer", "unknown")
            path = cert_data.get("path", "unknown")
            serial = cert_data.get("serial", "unknown")

            # Expiration timestamp
            if "expiration_timestamp" in cert_data:
                self.ssl_cert_expiration_timestamp.labels(
                    common_name=common_name, issuer=issuer, path=path, serial=serial
                ).set(float(cert_data["expiration_timestamp"]))

            # SAN count
            if "san_count" in cert_data:
                self.ssl_cert_san_count.labels(common_name=common_name, path=path).set(
                    int(cert_data["san_count"])
                )

            # Certificate info
            self.ssl_cert_info.labels(
                path=path,
                common_name=common_name,
                issuer=issuer,
                serial=serial,
                subject=cert_data.get("subject", "unknown"),
            ).info({})

            # Issuer code
            issuer_code = self._get_issuer_code(issuer)
            self.ssl_cert_issuer_code.labels(common_name=common_name, issuer=issuer, path=path).set(
                issuer_code
            )

            # Track duplicates by serial number
            if serial != "unknown":
                self._duplicate_certificates[serial].append(path)

            # Check for weak keys
            if cert_data.get("is_weak_key", False):
                self._current_scan_weak_keys += 1

            # Check for deprecated signature algorithms
            if cert_data.get("is_deprecated_algorithm", False):
                self._current_scan_deprecated_sigalgs += 1

            log_metrics_collection(
                self.logger,
                "certificate_processed",
                1.0,
                {"common_name": common_name, "path": path},
            )

        except Exception as e:
            self.logger.error(f"Failed to update certificate metrics: {e}")

    def update_scan_metrics(
        self,
        directory: str,
        duration: float,
        files_total: int,
        parsed_total: int,
        errors_total: int,
    ) -> None:
        """
        Update scan-related metrics.

        Args:
            directory: Scanned directory
            duration: Scan duration in seconds
            files_total: Total files processed
            parsed_total: Successfully parsed certificates
            errors_total: Number of parsing errors
        """
        try:
            self.ssl_cert_files_total.labels(directory=directory).set(int(files_total))
            self.ssl_cert_scan_duration_seconds.labels(directory=directory).observe(duration)
            self.ssl_cert_last_scan_timestamp.labels(directory=directory).set(int(time.time()))

            # Set current counts (not cumulative)
            self.ssl_certs_parsed_total.set(parsed_total)
            self.ssl_cert_parse_errors_total.set(self._current_scan_parse_errors)
            self.ssl_cert_weak_key_total.set(self._current_scan_weak_keys)
            self.ssl_cert_deprecated_sigalg_total.set(self._current_scan_deprecated_sigalgs)

            log_metrics_collection(
                self.logger,
                "scan_completed",
                duration,
                {
                    "directory": directory,
                    "files_total": files_total,
                    "parsed_total": parsed_total,
                    "errors_total": errors_total,
                },
            )

        except Exception as e:
            self.logger.error(f"Failed to update scan metrics: {e}")

    def record_parse_error(self, filename: str, error_type: str, error_message: str) -> None:
        """
        Record a certificate parsing error.

        Args:
            filename: Name of the file that failed to parse
            error_type: Type of error
            error_message: Error message
        """
        try:
            # Increment our internal counter for current scan
            self._current_scan_parse_errors += 1

            self.ssl_cert_parse_error_names.labels(
                filename=filename,
                error_type=error_type,
                error_message=error_message[:100],  # Truncate long messages
            ).info({"full_error": error_message, "timestamp": str(time.time())})

            log_metrics_collection(
                self.logger, "parse_error", 1.0, {"filename": filename, "error_type": error_type}
            )

        except Exception as e:
            self.logger.error(f"Failed to record parse error: {e}")

    def update_duplicate_metrics(self) -> None:
        """Update duplicate certificate metrics."""
        try:
            # Count duplicates (serials with more than one path)
            duplicates = {
                serial: paths
                for serial, paths in self._duplicate_certificates.items()
                if len(paths) > 1
            }

            self.ssl_cert_duplicate_count.set(int(len(duplicates)))

            # Record duplicate information with fixed labels
            for serial, paths in duplicates.items():
                self.ssl_cert_duplicate_names.labels(serial_number=serial).info(
                    {
                        "duplicate_count": str(len(paths)),
                        "certificate_paths": ",".join(paths),
                        "path_count": str(len(paths)),
                    }
                )

            if duplicates:
                log_metrics_collection(self.logger, "duplicates_found", len(duplicates))

        except Exception as e:
            self.logger.error(f"Failed to update duplicate metrics: {e}")

    def update_system_metrics(self) -> None:
        """Update system and application metrics."""
        current_time = time.time()

        # Only update system metrics every N seconds to reduce overhead
        if current_time - self._last_system_update < self._system_update_interval:
            return

        try:
            # Get current process
            process = psutil.Process()

            # Memory metrics
            memory_info = process.memory_info()
            self.app_memory_bytes.labels(type="rss").set(int(memory_info.rss))
            self.app_memory_bytes.labels(type="vms").set(int(memory_info.vms))

            # CPU metrics
            cpu_percent = process.cpu_percent()
            self.app_cpu_percent.set(cpu_percent)

            # Thread count
            thread_count = process.num_threads()
            self.app_thread_count.set(int(thread_count))

            # Application info (only set once)
            import sys

            from tls_cert_monitor import __version__

            self.app_info.labels(
                hostname=socket.gethostname(),
                version=__version__,
                python_version=f"{sys.version_info.major}.{sys.version_info.minor}.{sys.version_info.micro}",
            ).info({"platform": sys.platform, "process_id": str(process.pid)})

            self._last_system_update = current_time

            log_metrics_collection(
                self.logger,
                "system_metrics_updated",
                1.0,
                {
                    "memory_rss": memory_info.rss,
                    "cpu_percent": cpu_percent,
                    "thread_count": thread_count,
                },
            )

        except Exception as e:
            self.logger.error(f"Failed to update system metrics: {e}")

    def reset_scan_metrics(self) -> None:
        """Reset scan-specific metrics for a new scan. Resets current counts but preserves historical data."""
        self._duplicate_certificates.clear()
        self._current_scan_parse_errors = 0
        self._current_scan_weak_keys = 0
        self._current_scan_deprecated_sigalgs = 0

        # Immediately reset the gauge metrics to zero for instant feedback
        self.ssl_certs_parsed_total.set(0)
        self.ssl_cert_parse_errors_total.set(0)
        self.ssl_cert_weak_key_total.set(0)
        self.ssl_cert_deprecated_sigalg_total.set(0)
        self.ssl_cert_duplicate_count.set(0)

        self.logger.debug("Scan metrics reset (current counts cleared and gauges zeroed)")

    def clear_all_certificate_metrics(self) -> None:
        """Clear all labeled certificate metrics. Used when exclude patterns change."""
        try:
            # Clear all labeled metrics by recreating them
            # This is necessary because Prometheus labeled metrics can't be selectively cleared

            # Store the registry reference
            registry = self.registry

            # Unregister all labeled certificate metrics
            labeled_metrics = [
                self.ssl_cert_expiration_timestamp,
                self.ssl_cert_san_count,
                self.ssl_cert_info,
                self.ssl_cert_duplicate_names,
                self.ssl_cert_issuer_code,
            ]

            for metric in labeled_metrics:
                try:
                    registry.unregister(metric)
                except KeyError:
                    # Metric might not be registered yet
                    pass

            # Recreate all labeled metrics
            self.ssl_cert_expiration_timestamp = Gauge(
                "ssl_cert_expiration_timestamp",
                "Certificate expiration time (Unix timestamp)",
                ["common_name", "issuer", "path", "serial"],
                registry=registry,
            )

            self.ssl_cert_san_count = Gauge(
                "ssl_cert_san_count",
                "Number of Subject Alternative Names",
                ["common_name", "path"],
                registry=registry,
            )

            self.ssl_cert_info = Info(
                "ssl_cert_info",
                "Certificate information with labels",
                ["path", "common_name", "issuer", "serial", "subject"],
                registry=registry,
            )

            self.ssl_cert_duplicate_names = Info(
                "ssl_cert_duplicate_names",
                "Names of certificates that are duplicates",
                ["serial_number"],
                registry=registry,
            )

            self.ssl_cert_issuer_code = Gauge(
                "ssl_cert_issuer_code",
                "Numeric issuer classification",
                ["common_name", "issuer", "path"],
                registry=registry,
            )

            self.logger.debug("All labeled certificate metrics cleared and recreated")

        except Exception as e:
            self.logger.error(f"Failed to clear certificate metrics: {e}")

    def reset_parse_error_metrics(self) -> None:
        """Reset parse error metrics - useful after configuration changes like new passwords."""
        # Reset the current scan error count and gauge
        self._current_scan_parse_errors = 0
        self.ssl_cert_parse_errors_total.set(0)

        # Clear individual error details
        try:
            self.registry.unregister(self.ssl_cert_parse_error_names)
        except KeyError:
            # Metric might not be registered yet
            pass

        self.ssl_cert_parse_error_names = Info(
            "ssl_cert_parse_error_names",
            "Names of certificates that have parsing errors",
            ["filename", "error_type", "error_message"],
            registry=self.registry,
        )

        self.logger.debug("Parse error metrics recreated")

    def get_metrics(self) -> str:
        """
        Get Prometheus metrics in text format.

        Returns:
            Metrics in Prometheus text format
        """
        # Update system metrics before generating output
        self.update_system_metrics()

        # Update duplicate metrics
        self.update_duplicate_metrics()

        # Get raw metrics
        raw_metrics = generate_latest(self.registry).decode("utf-8")

        # Format numeric values to remove scientific notation and unnecessary decimals
        formatted_metrics = self._format_numeric_values(raw_metrics)

        return formatted_metrics

    def _format_numeric_values(self, metrics_text: str) -> str:
        """
        Format numeric values in metrics to use integers where appropriate.

        Args:
            metrics_text: Raw Prometheus metrics text

        Returns:
            Formatted metrics text with integers instead of scientific notation/decimals
        """
        import re

        lines = metrics_text.split("\n")
        formatted_lines = []

        for line in lines:
            if line.startswith("#") or not line.strip():
                # Keep comments and empty lines unchanged
                formatted_lines.append(line)
                continue

            # Match lines with metric values (with or without labels)
            match = re.match(r"^([^}]+})\s+(.+)$", line) or re.match(r"^([^\s]+)\s+(.+)$", line)
            if match:
                metric_name = match.group(1)
                value = match.group(2)

                # Convert scientific notation and decimals to integers for specific metrics
                if any(
                    metric in metric_name
                    for metric in [
                        "ssl_cert_last_scan_timestamp",
                        "ssl_cert_san_count",
                        "ssl_cert_files_total",
                        "ssl_cert_duplicate_count",
                        "app_memory_bytes",
                        "app_thread_count",
                        "ssl_cert_issuer_code",
                    ]
                ):
                    try:
                        # Convert scientific notation and float to integer
                        if "e+" in value:
                            int_value = int(float(value))
                        elif value.endswith(".0"):
                            int_value = int(float(value))
                        else:
                            # Try to convert, fallback to original if not numeric
                            try:
                                float_value = float(value)
                                if float_value.is_integer():
                                    int_value = int(float_value)
                                else:
                                    int_value = None
                            except ValueError:
                                int_value = None

                        if int_value is not None:
                            formatted_lines.append(f"{metric_name} {int_value}")
                        else:
                            formatted_lines.append(line)
                    except (ValueError, OverflowError):
                        # If conversion fails, keep original
                        formatted_lines.append(line)
                else:
                    # Keep other metrics unchanged (like CPU percentages)
                    formatted_lines.append(line)
            else:
                formatted_lines.append(line)

        return "\n".join(formatted_lines)

    def get_content_type(self) -> str:
        """Get content type for metrics endpoint."""
        return CONTENT_TYPE_LATEST

    def _get_issuer_code(self, issuer: str) -> int:
        """
        Get numeric issuer classification.

        Args:
            issuer: Certificate issuer string

        Returns:
            Numeric issuer code
        """
        issuer_lower = issuer.lower()

        # DigiCert
        if "digicert" in issuer_lower:
            return 30

        # Amazon
        if any(keyword in issuer_lower for keyword in ["amazon", "aws"]):
            return 31

        # Self-signed
        if any(keyword in issuer_lower for keyword in ["self-signed", "localhost", "127.0.0.1"]):
            return 33

        # Other/Unknown
        return 32

    def get_registry_status(self) -> Dict[str, Any]:
        """Get Prometheus registry status for health checks."""
        try:
            # Count metrics by type
            metrics_count = len(list(self.registry._collector_to_names.keys()))

            return {
                "prometheus_registry": {
                    "status": "healthy",
                    "metrics_count": metrics_count,
                    "last_update": self._last_system_update,
                }
            }
        except Exception as e:
            return {"prometheus_registry": {"status": "error", "error": str(e)}}


# Utility functions for metric helpers
def is_weak_key(key_size: int, algorithm: str) -> bool:
    """
    Check if a key is considered weak.

    Args:
        key_size: Key size in bits
        algorithm: Key algorithm

    Returns:
        True if key is weak
    """
    algorithm_lower = algorithm.lower()

    # Check ECDSA first (before RSA) since "ecdsa" contains "rsa"
    if "ec" in algorithm_lower or "ecdsa" in algorithm_lower:
        # ECDSA: P-256 (256 bits) is considered secure, anything below is weak
        return key_size < 256
    elif "rsa" in algorithm_lower:
        return key_size < 2048
    elif "dsa" in algorithm_lower:
        return key_size < 2048

    # Unknown algorithm, be conservative
    return key_size < 2048


def is_deprecated_signature_algorithm(algorithm: str) -> bool:
    """
    Check if a signature algorithm is deprecated.

    Args:
        algorithm: Signature algorithm

    Returns:
        True if algorithm is deprecated
    """
    algorithm_lower = algorithm.lower()

    deprecated_algorithms = ["md5", "sha1", "md2", "md4"]

    return any(alg in algorithm_lower for alg in deprecated_algorithms)
