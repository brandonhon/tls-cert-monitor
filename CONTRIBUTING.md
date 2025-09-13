# Contributing to TLS Certificate Monitor

Thank you for your interest in contributing! This document provides guidelines for contributing to the project.

## 🚀 Getting Started

### Prerequisites
- Python 3.11+ 
- Docker (for containerized builds)
- Git

### Development Setup
1. Fork the repository
2. Clone your fork: `git clone https://github.com/YOUR_USERNAME/tls-cert-monitor.git`
3. Set up development environment: `make setup`
4. Verify everything works: `make check test`

### Development Workflow
1. Create a feature branch: `git checkout -b feature/amazing-feature`
2. Make your changes following our guidelines
3. Run tests and quality checks: `make check test`
4. Commit your changes: `git commit -m 'feat: add amazing feature'`
5. Push to your fork: `git push origin feature/amazing-feature`
6. Open a Pull Request

## 📝 Development Guidelines

### Code Style
- Follow PEP 8 style guidelines
- Use type hints for all function signatures
- Write docstrings for public APIs
- Run `make format` before committing

### Testing
- Write tests for new features and bug fixes
- Maintain or improve test coverage
- Run `make test` to ensure all tests pass
- Test on multiple platforms when possible

### Commit Messages
Follow [Conventional Commits](https://conventionalcommits.org/):
- `feat:` new features
- `fix:` bug fixes  
- `docs:` documentation updates
- `style:` code style changes
- `refactor:` code refactoring
- `test:` adding tests
- `chore:` maintenance tasks

### Build and Release
- All builds are automated via GitHub Actions
- Binaries are built for Linux, Windows, and macOS
- Docker images are published automatically
- Use semantic versioning for releases

## 🎯 What We're Looking For

### High Priority
- Platform-specific bug fixes
- Performance improvements
- Security enhancements
- Documentation improvements

### Medium Priority
- New certificate formats support
- Additional metrics and monitoring features
- UI/UX improvements
- Integration with external systems

### Examples of Good First Issues
- Fix typos or improve documentation
- Add unit tests for existing code
- Improve error messages
- Add configuration validation

## 🔍 Reporting Issues

### Bug Reports
Use the bug report template and include:
- Steps to reproduce
- Expected vs actual behavior
- Environment details (OS, Python version, etc.)
- Relevant logs or error messages

### Feature Requests
Use the feature request template and include:
- Problem description
- Proposed solution
- Use cases and benefits
- Potential alternatives

### Security Issues
**Do not report security issues publicly.** Use [GitHub Security Advisories](https://github.com/brandonhon/tls-cert-monitor/security/advisories/new) instead.

## 🏗️ Architecture Overview

### Key Components
- **Scanner**: Certificate discovery and parsing
- **Cache**: LRU cache with disk persistence  
- **Metrics**: Prometheus metrics collection
- **API**: FastAPI-based REST endpoints
- **Config**: YAML-based configuration with hot reload

### Build System
- **Nuitka**: Python-to-binary compilation
- **Docker**: Containerized cross-platform builds
- **GitHub Actions**: Automated CI/CD pipeline

## ✅ Code Review Process

### What We Look For
- Code quality and clarity
- Test coverage and correctness
- Performance considerations
- Security implications
- Documentation completeness

### Review Timeline
- Initial feedback within 2-3 business days
- Follow-up reviews within 1-2 business days
- Maintainer availability may vary

## 🤝 Code of Conduct

By participating in this project, you agree to:
- Be respectful in discussions
- Focus on constructive feedback
- Follow professional standards
- Report disruptive behavior to maintainers

## 📞 Getting Help

- **Questions**: Open a [Discussion](https://github.com/brandonhon/tls-cert-monitor/discussions)
- **Bugs**: Use the bug report template
- **Features**: Use the feature request template
- **Security**: Use [Security Advisories](https://github.com/brandonhon/tls-cert-monitor/security/advisories/new)

## 🙏 Recognition

Contributors are recognized in:
- Release notes for significant contributions
- README contributor section
- Git commit history

Thank you for helping make TLS Certificate Monitor better! 🔒