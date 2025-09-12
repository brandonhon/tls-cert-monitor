# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Development Commands

### Environment Setup
- `make setup-dev` - Complete development setup (venv + dependencies + config)
- `make install-dev` - Install development dependencies in virtual environment
- `make install-dev-system` - Install development dependencies system-wide

### Code Quality & Testing
- `make check` - Run all code quality checks (format, lint, type-check, security)
- `make test` - Run tests with pytest
- `make test-coverage` - Run tests with coverage report
- `make format` - Format code with black and isort
- `make lint` - Run flake8 and pylint
- `make type-check` - Run mypy type checking
- `make security` - Run bandit security checks

### Running the Application
- `make run` - Run with virtual environment (recommended)
- `make run-system` - Run with system Python
- `make run-dev` - Run in development mode with uvicorn hot reload
- `make config` - Create config.yaml from example

### Single Test Execution
- `python -m pytest tests/test_config.py -v` - Run specific test file
- `python -m pytest -k "test_cache" -v` - Run tests matching pattern

### Docker Development
- `make docker-build` - Build Docker image locally
- `make docker-run` - Run Docker container locally
- `make compose-up` - Start with docker-compose
- `make compose-down` - Stop docker-compose
- `make docker-compose` - Run using production docker-compose

### Release and Distribution
- Releases are automatically created on every push to main branch
- Multi-platform binaries are built via GitHub Actions
- Docker images are published to GitHub Container Registry
- Binary artifacts are packaged as `platform-arch.tar.gz` (e.g., `linux-amd64.tar.gz`)

## Architecture Overview

This is a Python-based TLS certificate monitoring application with the following key architectural components:

### Core Components
- **main.py**: Application entry point with TLSCertMonitor class orchestrating all components
- **config.py**: YAML-based configuration management with environment variable overrides
- **scanner.py**: Multi-threaded certificate scanner for PEM, DER, and PKCS#12 formats
- **metrics.py**: Prometheus metrics collector for certificate and operational metrics
- **cache.py**: LRU cache manager with disk persistence for certificate data
- **api.py**: FastAPI-based REST API providing `/metrics`, `/healthz`, `/scan`, and `/config` endpoints
- **hot_reload.py**: File system watcher for configuration and certificate changes
- **logger.py**: Centralized logging configuration

### Key Patterns
- **Async/await**: Application uses asyncio throughout for concurrent operations
- **Dependency injection**: Components are injected into the main TLSCertMonitor class
- **Configuration-driven**: All behavior controlled via YAML config with env var overrides
- **Metrics-first**: Comprehensive Prometheus metrics for monitoring and alerting
- **Graceful shutdown**: Signal handlers for clean resource management

### Certificate Processing Flow
1. Scanner discovers certificates in configured directories
2. Multi-worker parsing of different certificate formats
3. Security analysis (weak keys, deprecated algorithms, expiration)
4. Caching of parsed certificate data
5. Metrics collection and exposure via `/metrics` endpoint

### Technology Stack
- **FastAPI**: Web framework for API endpoints
- **cryptography**: Certificate parsing and analysis
- **prometheus_client**: Metrics collection and export
- **watchdog**: File system monitoring for hot reload
- **pydantic**: Configuration validation
- **psutil**: System resource monitoring

### Configuration Structure
The application uses YAML configuration with these key sections:
- Certificate directories and exclusions
- P12/PFX password lists
- Scan intervals and worker counts
- Server settings (port, bind address, TLS)
- Cache and logging configuration
- Feature toggles (hot_reload, dry_run)

### Testing Framework
- **pytest**: Test framework with coverage reporting
- **Test structure**: Tests mirror source structure in `tests/` directory
- **Coverage**: HTML and XML coverage reports generated in `coverage/` directory

### Build and Release System
- **Multi-platform binaries**: Automated builds for Linux, Windows, and macOS (AMD64 + ARM64 where supported)
- **Docker images**: Multi-architecture container images published to GitHub Container Registry
- **Automated releases**: GitHub Actions workflow creates releases on every push to main branch
- **Binary packaging**: Platform-specific tar.gz archives (e.g., `linux-amd64.tar.gz`)
- **Nuitka compilation**: Python-to-binary compilation for standalone executables
- **Cross-compilation**: Docker buildx for ARM64 Linux builds, native compilation for other platforms

### Distribution Channels
- **GitHub Releases**: Pre-compiled binaries for direct download
- **GitHub Container Registry**: Docker images at `ghcr.io/brandonhon/tls-cert-monitor`
- **Source installation**: Python package installable via pip from source

# Development Guidelines

## Philosophy

### Core Beliefs

- **Incremental progress over big bangs** - Small changes that compile and pass tests
- **Learning from existing code** - Study and plan before implementing
- **Pragmatic over dogmatic** - Adapt to project reality
- **Clear intent over clever code** - Be boring and obvious

### Simplicity Means

- Single responsibility per function/class
- Avoid premature abstractions
- No clever tricks - choose the boring solution
- If you need to explain it, it's too complex

## Process

### 1. Planning & Staging

Break complex work into 3-5 stages. Document in `IMPLEMENTATION_PLAN.md`:

```markdown
## Stage N: [Name]
**Goal**: [Specific deliverable]
**Success Criteria**: [Testable outcomes]
**Tests**: [Specific test cases]
**Status**: [Not Started|In Progress|Complete]
```
- Update status as you progress
- Remove file when all stages are done

### 2. Implementation Flow

1. **Understand** - Study existing patterns in codebase
2. **Test** - Write test first (red)
3. **Implement** - Minimal code to pass (green)
4. **Refactor** - Clean up with tests passing
5. **Commit** - With clear message linking to plan

### 3. When Stuck (After 3 Attempts)

**CRITICAL**: Maximum 3 attempts per issue, then STOP.

1. **Document what failed**:
   - What you tried
   - Specific error messages
   - Why you think it failed

2. **Research alternatives**:
   - Find 2-3 similar implementations
   - Note different approaches used

3. **Question fundamentals**:
   - Is this the right abstraction level?
   - Can this be split into smaller problems?
   - Is there a simpler approach entirely?

4. **Try different angle**:
   - Different library/framework feature?
   - Different architectural pattern?
   - Remove abstraction instead of adding?

## Technical Standards

### Architecture Principles

- **Composition over inheritance** - Use dependency injection
- **Interfaces over singletons** - Enable testing and flexibility
- **Explicit over implicit** - Clear data flow and dependencies
- **Test-driven when possible** - Never disable tests, fix them

### Code Quality

- **Every commit must**:
  - Compile successfully
  - Pass all existing tests
  - Include tests for new functionality
  - Follow project formatting/linting

- **Before committing**:
  - Run formatters/linters
  - Self-review changes
  - Ensure commit message explains "why"

### Error Handling

- Fail fast with descriptive messages
- Include context for debugging
- Handle errors at appropriate level
- Never silently swallow exceptions

## Decision Framework

When multiple valid approaches exist, choose based on:

1. **Testability** - Can I easily test this?
2. **Readability** - Will someone understand this in 6 months?
3. **Consistency** - Does this match project patterns?
4. **Simplicity** - Is this the simplest solution that works?
5. **Reversibility** - How hard to change later?

## Project Integration

### Learning the Codebase

- Find 3 similar features/components
- Identify common patterns and conventions
- Use same libraries/utilities when possible
- Follow existing test patterns

### Tooling

- Use project's existing build system
- Use project's test framework
- Use project's formatter/linter settings
- Don't introduce new tools without strong justification

## Quality Gates

### Definition of Done

- [ ] Tests written and passing
- [ ] Code follows project conventions
- [ ] No linter/formatter warnings
- [ ] Commit messages are clear
- [ ] Implementation matches plan
- [ ] No TODOs without issue numbers

### Test Guidelines

- Test behavior, not implementation
- One assertion per test when possible
- Clear test names describing scenario
- Use existing test utilities/helpers
- Tests should be deterministic

## Important Reminders

**NEVER**:
- Use `--no-verify` to bypass commit hooks
- Disable tests instead of fixing them
- Commit code that doesn't compile
- Make assumptions - verify with existing code

**ALWAYS**:
- Commit working code incrementally
- Update plan documentation as you go
- Learn from existing implementations
- Stop after 3 failed attempts and reassess
- Make sure to alway increment the version appropriately using git tags