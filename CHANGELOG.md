# Changelog

All notable changes to this project will be documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.0.0/),
and this project adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

## [1.0.5] - 2026-01-15

### Fixed
- **Hot reload metrics refresh**: Fixed critical issue where metrics were not refreshing accurately when certificate files changed
  - Modified certificate files now trigger immediate re-scan and metric updates (previously waited for periodic scan interval)
  - Fixed cache invalidation logic that was using incorrect mtime keys, causing stale cache entries to persist
  - All certificate changes (created, modified, deleted, moved) now properly clear metrics and trigger immediate updates
  - Added scan lock to prevent concurrent scans from causing race conditions
- **Improved file change detection**: Enhanced debouncing logic to better handle rapid successive writes
  - Increased debounce period from 1s to 2s to catch rapid file operations
  - Added file stability check to ensure files are fully written before processing
  - Detects when files are still being written and waits appropriately

### Technical Details
- `scanner.py`: Added async lock (`_scan_lock`) to prevent concurrent scan operations
- `hot_reload.py`: Simplified cache invalidation to clear entire cache for any file change
- `hot_reload.py`: Modified certificate files now trigger full metric clear and immediate re-scan
- `hot_reload.py`: Improved file stability detection with mtime verification

### Impact
This fix ensures that Grafana dashboards and monitoring systems receive accurate, real-time certificate metrics when certificates are added, modified, renewed, or removed. Previously, metric updates could be delayed by up to the configured `scan_interval` (default 5 minutes).

## [1.0.4] - Prior Release
- Hot reload enhancements and bug fixes

## [1.0.3] - Prior Release
- Hot reload fix release

## [1.0.2] - Prior Release
- Previous bug fixes and improvements

## [1.0.1] - Prior Release
- Initial improvements

## [1.0.0] - Initial Release
- Initial release of TLS Certificate Monitor
