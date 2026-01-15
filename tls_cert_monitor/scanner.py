"""
Certificate scanner for TLS Certificate Monitor.
"""

import asyncio
import os
import re
import shutil
import time
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, List, Optional

from cryptography import x509
from cryptography.hazmat.primitives.serialization import pkcs12

from tls_cert_monitor.cache import CacheManager
from tls_cert_monitor.config import Config
from tls_cert_monitor.logger import (
    get_logger,
    log_cert_error,
    log_cert_parsed,
    log_cert_scan_complete,
    log_cert_scan_start,
)
from tls_cert_monitor.metrics import (
    MetricsCollector,
    is_deprecated_signature_algorithm,
    is_weak_key,
)


class CertificateScanner:
    """
    Scanner for SSL/TLS certificates in specified directories.

    Supports multiple certificate formats:
    - PEM (.pem, .crt, .cer, .cert)
    - DER (.der)
    - PKCS#12/PFX (.p12, .pfx)
    """

    SUPPORTED_EXTENSIONS = {".pem", ".crt", ".cer", ".cert", ".der", ".p12", ".pfx"}

    def __init__(self, config: Config, cache: CacheManager, metrics: MetricsCollector):
        self.config = config
        self.cache = cache
        self.metrics = metrics
        self.logger = get_logger("scanner")

        self._scanning = False
        self._scan_task: Optional[asyncio.Task] = None
        self._executor = ThreadPoolExecutor(max_workers=config.workers)
        self._scan_lock: Optional[asyncio.Lock] = None  # Initialize lock lazily in async context

        self.logger.info(f"Certificate scanner initialized - Workers: {config.workers}")

    async def start_scanning(self) -> None:
        """Start the periodic certificate scanning."""
        if self._scanning:
            self.logger.warning("Scanner is already running")
            return

        self._scanning = True
        self._scan_task = asyncio.create_task(self._scan_loop())
        self.logger.info(f"Started certificate scanning - Interval: {self.config.scan_interval}")

    async def stop(self) -> None:
        """Stop the certificate scanning."""
        self._scanning = False

        if self._scan_task:
            self._scan_task.cancel()
            try:
                await self._scan_task
            except asyncio.CancelledError:
                pass

        self._executor.shutdown(wait=True)
        self.logger.info("Certificate scanner stopped")

    async def scan_once(self) -> Dict[str, Any]:
        """
        Perform a single scan of all configured directories.

        Returns:
            Scan results summary
        """
        # Initialize lock lazily if needed
        if self._scan_lock is None:
            self._scan_lock = asyncio.Lock()

        # Prevent concurrent scans
        async with self._scan_lock:
            start_time = time.time()
            total_files = 0
            total_parsed = 0
            total_errors = 0

            # Reset metrics for new scan
            self.metrics.reset_scan_metrics()

            scan_results: Dict[str, Any] = {"directories": {}, "summary": {}, "timestamp": start_time}

            for directory in self.config.certificate_directories:
                dir_start_time = time.time()

                try:
                    result = await self._scan_directory(directory)

                    dir_duration = time.time() - dir_start_time
                    total_files += result["files_processed"]
                    total_parsed += result["certificates_parsed"]
                    total_errors += result["parse_errors"]

                    # Update metrics
                    self.metrics.update_scan_metrics(
                        directory=directory,
                        duration=dir_duration,
                        files_total=result["files_processed"],
                        parsed_total=result["certificates_parsed"],
                        errors_total=result["parse_errors"],
                    )

                    scan_results["directories"][directory] = result

                    log_cert_scan_complete(
                        self.logger,
                        directory,
                        dir_duration,
                        result["certificates_parsed"],
                        result["parse_errors"],
                    )

                except Exception as e:
                    self.logger.error(f"Failed to scan directory {directory}: {e}")
                    scan_results["directories"][directory] = {
                        "error": str(e),
                        "files_processed": 0,
                        "certificates_parsed": 0,
                        "parse_errors": 1,
                    }
                    total_errors += 1

            total_duration = time.time() - start_time

            scan_results["summary"] = {
                "total_duration": total_duration,
                "total_files": total_files,
                "total_parsed": total_parsed,
                "total_errors": total_errors,
                "directories_scanned": len(self.config.certificate_directories),
            }

            self.logger.info(
                f"Scan completed - Duration: {total_duration:.2f}s, "
                f"Files: {total_files}, Parsed: {total_parsed}, Errors: {total_errors}"
            )

            return scan_results

    async def _scan_loop(self) -> None:
        """Main scanning loop."""
        while self._scanning:
            try:
                await self.scan_once()
                await asyncio.sleep(self.config.scan_interval_seconds)
            except asyncio.CancelledError:
                break
            except Exception as e:
                self.logger.error(f"Error in scan loop: {e}")
                await asyncio.sleep(60)  # Wait before retrying

    async def _scan_directory(self, directory: str) -> Dict[str, Any]:
        """
        Scan a single directory for certificates.

        Args:
            directory: Directory path to scan

        Returns:
            Scan results for the directory
        """
        directory_path = Path(directory)

        if not directory_path.exists():
            raise FileNotFoundError(f"Directory does not exist: {directory}")

        if not directory_path.is_dir():
            raise NotADirectoryError(f"Path is not a directory: {directory}")

        # Find certificate files
        cert_files = self._find_certificate_files(directory_path)

        log_cert_scan_start(self.logger, directory, len(cert_files))

        files_processed = 0
        certificates_parsed = 0
        parse_errors = 0
        certificates = []

        # Process files in parallel
        semaphore = asyncio.Semaphore(self.config.workers)
        tasks = []

        for cert_file in cert_files:
            task = asyncio.create_task(self._process_certificate_file(cert_file, semaphore))
            tasks.append(task)

        # Wait for all tasks to complete
        results = await asyncio.gather(*tasks, return_exceptions=True)

        for result in results:
            files_processed += 1

            if isinstance(result, Exception):
                parse_errors += 1
                self.logger.error(f"Task failed: {result}")
            elif result is None:
                parse_errors += 1
            else:
                certificates_parsed += 1
                cert_result: Dict[str, Any] = result  # type: ignore[assignment]
                certificates.append(cert_result)

                # Update certificate metrics
                self.metrics.update_certificate_metrics(cert_result)

        return {
            "directory": directory,
            "files_processed": files_processed,
            "certificates_parsed": certificates_parsed,
            "parse_errors": parse_errors,
            "certificates": certificates,
            "disk_usage": self._get_disk_usage(directory_path),
        }

    def _find_certificate_files(self, directory: Path) -> List[Path]:
        """
        Find all certificate files in a directory.

        Args:
            directory: Directory to search

        Returns:
            List of certificate file paths
        """
        cert_files = []
        exclude_paths = {
            Path(exclude_dir).resolve() for exclude_dir in self.config.exclude_directories
        }

        try:
            for root, _, files in os.walk(directory):
                root_path = Path(root).resolve()

                # Skip excluded directories
                if any(
                    root_path == exclude_path or root_path.is_relative_to(exclude_path)
                    for exclude_path in exclude_paths
                ):
                    continue

                for file in files:
                    file_path = Path(root) / file

                    # Check file extension
                    if file_path.suffix.lower() in self.SUPPORTED_EXTENSIONS:
                        # Check if file matches any exclude patterns
                        exclude_file = False
                        for pattern in self.config.exclude_file_patterns:
                            try:
                                if re.search(pattern, file_path.name, re.IGNORECASE):
                                    self.logger.debug(
                                        f"Excluding file {file_path.name} (matches pattern: {pattern})"
                                    )
                                    exclude_file = True
                                    break
                            except re.error as e:
                                self.logger.warning(f"Invalid regex pattern '{pattern}': {e}")

                        if not exclude_file:
                            cert_files.append(file_path)

        except Exception as e:
            self.logger.error(f"Error walking directory {directory}: {e}")

        return cert_files

    async def _process_certificate_file(
        self, file_path: Path, semaphore: asyncio.Semaphore
    ) -> Optional[Dict[str, Any]]:
        """
        Process a single certificate file.

        Args:
            file_path: Path to certificate file
            semaphore: Semaphore for concurrency control

        Returns:
            Certificate data or None if failed
        """
        async with semaphore:
            # Check cache first
            cache_key = self.cache.make_key("cert", str(file_path), file_path.stat().st_mtime)
            cached_result = await self.cache.get(cache_key)

            if cached_result is not None:
                return cached_result  # type: ignore[no-any-return]

            # Process in thread pool
            try:
                loop = asyncio.get_event_loop()
                result = await loop.run_in_executor(
                    self._executor, self._parse_certificate_file, file_path
                )

                if result:
                    # Cache successful result
                    await self.cache.set(cache_key, result)

                return result

            except Exception as e:
                error_type = type(e).__name__
                self.metrics.record_parse_error(file_path.name, error_type, str(e))
                log_cert_error(self.logger, str(file_path), e, error_type)
                return None

    def _parse_certificate_file(self, file_path: Path) -> Optional[Dict[str, Any]]:
        """
        Parse a certificate file and extract information.

        Args:
            file_path: Path to certificate file

        Returns:
            Certificate data dictionary or None if failed
        """
        try:
            cert_data = None

            # Try different parsing methods based on file extension
            if file_path.suffix.lower() in {".p12", ".pfx"}:
                cert_data = self._parse_pkcs12_file(file_path)
            else:
                cert_data = self._parse_pem_der_file(file_path)

            if cert_data:
                # Add file metadata
                stat = file_path.stat()
                cert_data.update(
                    {
                        "path": str(file_path),
                        "filename": file_path.name,
                        "file_size": stat.st_size,
                        "file_mtime": stat.st_mtime,
                    }
                )

                log_cert_parsed(
                    self.logger,
                    str(file_path),
                    cert_data.get("common_name", "unknown"),
                    cert_data.get("days_until_expiry", 0),
                )

            return cert_data

        except Exception as e:
            raise RuntimeError(f"Failed to parse {file_path}: {e}") from e

    def _parse_pem_der_file(self, file_path: Path) -> Optional[Dict[str, Any]]:
        """Parse PEM or DER certificate file."""
        with open(file_path, "rb") as f:
            cert_data = f.read()

        # Try PEM first
        try:
            cert = x509.load_pem_x509_certificate(cert_data)
        except ValueError:
            # Try DER
            try:
                cert = x509.load_der_x509_certificate(cert_data)
            except ValueError as e:
                raise ValueError(f"Could not parse as PEM or DER: {e}") from e

        return self._extract_certificate_info(cert)

    def _parse_pkcs12_file(self, file_path: Path) -> Optional[Dict[str, Any]]:
        """Parse PKCS#12/PFX certificate file."""
        with open(file_path, "rb") as f:
            p12_data = f.read()

        # Try different passwords with constant-time approach to prevent timing attacks
        last_exception = None
        successful_cert = None

        for password in self.config.p12_passwords:
            try:
                password_bytes = password.encode("utf-8") if password else None

                # Use cryptography library for PKCS#12 parsing
                _, cert, _ = pkcs12.load_key_and_certificates(p12_data, password_bytes)
                if cert and successful_cert is None:
                    # Store first successful result but continue processing all passwords
                    # to maintain constant timing
                    successful_cert = cert

            except Exception as e:
                # Always store the last exception for error reporting
                last_exception = e
                # Continue processing all passwords to maintain constant timing
                continue

        # Return successful result if found
        if successful_cert:
            return self._extract_certificate_info(successful_cert)

        # All passwords failed
        if last_exception:
            self.logger.debug(f"All password attempts failed for PKCS#12 file: {last_exception}")

        raise ValueError("Could not decrypt PKCS#12 file with any provided password")

    def _extract_certificate_info(self, cert: x509.Certificate) -> Dict[str, Any]:
        """
        Extract information from a certificate object.

        Args:
            cert: Certificate object

        Returns:
            Certificate information dictionary
        """
        # Basic certificate info
        common_name = self._get_common_name(cert)
        issuer = self._get_issuer_name(cert)
        subject = cert.subject.rfc4514_string()
        serial = str(cert.serial_number)

        # Dates
        not_before = cert.not_valid_before
        not_after = cert.not_valid_after
        now = datetime.utcnow()

        expiration_timestamp = not_after.timestamp()
        days_until_expiry = (not_after - now).days

        # Key information
        public_key = cert.public_key()
        key_algorithm = type(public_key).__name__

        # Get key size - not all key types have key_size attribute
        try:
            key_size = getattr(public_key, "key_size", 0)
        except AttributeError:
            key_size = 0

        # Signature algorithm
        signature_algorithm = cert.signature_algorithm_oid._name

        # Subject Alternative Names
        san_list = self._get_san_list(cert)
        san_count = len(san_list)

        # Security analysis
        is_weak_key_flag = is_weak_key(key_size, key_algorithm)
        is_deprecated_alg = is_deprecated_signature_algorithm(signature_algorithm)

        return {
            "common_name": common_name,
            "issuer": issuer,
            "subject": subject,
            "serial": serial,
            "not_before": not_before.isoformat(),
            "not_after": not_after.isoformat(),
            "expiration_timestamp": expiration_timestamp,
            "days_until_expiry": days_until_expiry,
            "key_size": key_size,
            "key_algorithm": key_algorithm,
            "signature_algorithm": signature_algorithm,
            "san_list": san_list,
            "san_count": san_count,
            "is_weak_key": is_weak_key_flag,
            "is_deprecated_algorithm": is_deprecated_alg,
            "version": cert.version.value,
        }

    def _get_common_name(self, cert: x509.Certificate) -> str:
        """Extract common name from certificate."""
        try:
            cn_attrs = cert.subject.get_attributes_for_oid(x509.NameOID.COMMON_NAME)
            if cn_attrs:
                value = cn_attrs[0].value
                return value if isinstance(value, str) else value.decode("utf-8")
        except Exception as e:
            self.logger.debug(f"Could not extract common name from certificate: {e}")
        return "unknown"

    def _get_issuer_name(self, cert: x509.Certificate) -> str:
        """Extract issuer name from certificate."""
        try:
            cn_attrs = cert.issuer.get_attributes_for_oid(x509.NameOID.COMMON_NAME)
            if cn_attrs:
                value = cn_attrs[0].value
                return value if isinstance(value, str) else value.decode("utf-8")
            # Fallback to organization
            org_attrs = cert.issuer.get_attributes_for_oid(x509.NameOID.ORGANIZATION_NAME)
            if org_attrs:
                value = org_attrs[0].value
                return value if isinstance(value, str) else value.decode("utf-8")
        except Exception as e:
            self.logger.debug(f"Could not extract issuer name from certificate: {e}")
        return "unknown"

    def _get_san_list(self, cert: x509.Certificate) -> List[str]:
        """Extract Subject Alternative Names from certificate."""
        try:
            san_ext = cert.extensions.get_extension_for_oid(
                x509.ExtensionOID.SUBJECT_ALTERNATIVE_NAME
            )
            return [str(name) for name in san_ext.value]  # type: ignore[attr-defined]
        except x509.ExtensionNotFound:
            return []
        except Exception:
            return []

    def _get_disk_usage(self, directory: Path) -> Dict[str, int]:
        """Get disk usage information for a directory."""
        try:
            usage = shutil.disk_usage(directory)
            return {"total": usage.total, "used": usage.used, "free": usage.free}
        except Exception as e:
            self.logger.warning(f"Could not get disk usage for {directory}: {e}")
            return {"total": 0, "used": 0, "free": 0}

    async def get_health_status(self) -> Dict[str, Any]:
        """Get scanner health status."""
        return {
            "cert_scan_status": "running" if self._scanning else "stopped",
            "certificate_directories": self.config.certificate_directories,
            "worker_pool_size": self.config.workers,
        }
