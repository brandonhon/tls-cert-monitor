# Dead Code and Outdated Documentation Audit

**Date**: 2026-01-15
**Version**: 1.0.5

## Summary

This audit identifies dead code, outdated documentation, unused scripts, and deprecated configurations in the TLS Certificate Monitor project.

---

## ✅ Good - No Issues Found

### Python Code
- **No TODO/FIXME comments**: Clean codebase with no pending work markers
- **No commented-out code blocks**: No large sections of disabled code
- **No unused imports detected**: All imports appear to be used
- **No dead functions**: All functions are referenced and used

### Test Coverage
- All 80 tests passing
- Good test coverage across all modules

---

## ⚠️ Issues Found

### 1. Missing Windows Service Installation Scripts

**Location**: `scripts/` directory
**Issue**: README.md references Windows installation scripts that don't exist

**README.md references (lines 453-454)**:
```
│   ├── install-windows-service.bat           # Windows service installer (legacy)
│   ├── install-windows-service-native.bat    # Windows native service installer
```

**Analysis**:
- These scripts are documented but missing from the repository
- Windows now uses Nuitka-winsvc for native service support built into the binary
- The scripts are LEGACY and no longer needed since the binary handles service installation

**Recommendation**:
✅ **Remove references from README.md** - Windows service installation is now built-in via Nuitka-winsvc (`.\tls-cert-monitor.exe install`)

---

### 2. Outdated Version in setup.py

**Location**: `setup.py:26`
**Issue**: Version hardcoded as "1.0.0" but actual version is 1.0.5

**Current**:
```python
version="1.0.0",
```

**Recommendation**:
✅ **Update to read version from `tls_cert_monitor/__init__.py`** to maintain single source of truth:
```python
# Read version from package
import re
def read_version():
    init_path = Path(__file__).parent / "tls_cert_monitor" / "__init__.py"
    with open(init_path, "r", encoding="utf-8") as f:
        content = f.read()
        match = re.search(r'__version__\s*=\s*["\']([^"\']+)["\']', content)
        if match:
            return match.group(1)
    return "0.0.0"

setup(
    version=read_version(),
    ...
)
```

---

### 3. Duplicate Ansible Documentation

**Location**: Root directory
**Issue**: `just_ansible.md` duplicates content from `ansible/README.md`

**Analysis**:
- `just_ansible.md` (279 lines) - Quick reference guide in root directory
- `ansible/README.md` - Comprehensive Ansible documentation in ansible directory
- Both cover similar Ansible deployment commands with significant overlap

**Resolution**: ✅ **IMPLEMENTED - Option A**
- Kept both files for different use cases
- Added reference note to `just_ansible.md` pointing to comprehensive documentation
- Quick reference remains easily accessible in root directory

---

### 4. Unused mypy Configuration

**Location**: `pyproject.toml:49-63`
**Issue**: mypy ignores imports for modules that are never used

**Current Configuration**:
```toml
[[tool.mypy.overrides]]
module = [
    "watchdog.*",
    "prometheus_client.*",
    "psutil.*",
    "OpenSSL.*",                    # ❌ NOT USED
    "win32service.*",                # ❌ NOT USED
    "win32serviceutil.*",            # ❌ NOT USED
    "win32event.*",                  # ❌ NOT USED
    "win32evtlog.*",                 # ❌ NOT USED
    "win32evtlogutil.*",             # ❌ NOT USED
    "win32api.*",                    # ❌ NOT USED
    "servicemanager.*",              # ❌ NOT USED
    "winreg.*",                      # ❌ NOT USED
]
```

**Analysis**:
- `OpenSSL.*` - No pyOpenSSL imports found in codebase (uses `cryptography` library instead)
- `win32*` and `servicemanager` - No Windows service imports (Nuitka-winsvc handles service functionality at compile time)

**Recommendation**:
✅ **Remove unused mypy overrides**:
```toml
[[tool.mypy.overrides]]
module = [
    "watchdog.*",
    "prometheus_client.*",
    "psutil.*",
]
ignore_missing_imports = true
```

---

### 5. Docker Cache and Logs Directories

**Location**: `docker/cache/` and `docker/logs/`
**Issue**: Empty directories committed to repository with root ownership

**Analysis**:
```
drwxr-xr-x  2 root       root       4096 Oct  7 13:30 cache
drwxr-xr-x  2 root       root       4096 Oct  7 13:30 logs
```

**Resolution**: ✅ **IMPLEMENTED - Option B**
- Removed empty directories from filesystem
- Added `docker/cache/` and `docker/logs/` to `.gitignore`
- Docker will automatically create these directories when needed
- Eliminates permission issues with root-owned directories

---

## 📋 Recommendations Summary

### ✅ All Items Resolved

1. ✅ **Updated setup.py version** to read from `__init__.py`
2. ✅ **Removed README.md references** to non-existent Windows scripts
3. ✅ **Cleaned up mypy config** to remove unused module overrides
4. ✅ **Kept just_ansible.md** as quick reference with note to comprehensive docs
5. ✅ **Removed docker directories** and added to `.gitignore` for auto-creation

### Low Priority (Optional)
- Consider adding a tool like `vulture` to CI/CD for automated dead code detection
- Add version consistency check to CI/CD to ensure setup.py and __init__.py match

---

## ✨ Overall Code Quality

**Excellent**: The codebase is very clean with:
- No TODOs or FIXMEs
- No commented-out code
- All tests passing (80/80)
- Good separation of concerns
- Comprehensive documentation

The issues found are primarily documentation and configuration maintenance items rather than code quality problems.
