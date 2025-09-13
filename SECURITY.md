# Security Policy

## Supported Versions

We provide security updates for the following versions:

| Version | Supported          |
| ------- | ------------------ |
| main    | :white_check_mark: |
| Latest release | :white_check_mark: |
| < 1.0   | :x:                |

## Reporting a Vulnerability

**Please do not report security vulnerabilities through public GitHub issues.**

Instead, please report them using [GitHub Security Advisories](https://github.com/brandonhon/tls-cert-monitor/security/advisories/new).

### What to Include

When reporting a vulnerability, please include:

- **Description**: Clear description of the vulnerability
- **Impact**: What could an attacker accomplish?
- **Reproduction**: Steps to reproduce the issue
- **Environment**: Affected versions, platforms, configurations
- **Proof of Concept**: Code, screenshots, or logs (if safe to share)

### Response Timeline

- **Acknowledgment**: Within 48 hours
- **Initial Assessment**: Within 5 business days  
- **Status Updates**: Weekly until resolved
- **Resolution**: Varies by severity (1-30 days)

### Disclosure Policy

- We follow coordinated disclosure principles
- Security fixes are released as soon as possible
- Public disclosure after fix is available (typically 90 days)
- Credit given to reporters (unless they prefer anonymity)

## Security Features

### Current Security Measures
- Input validation and sanitization
- Secure certificate parsing
- No execution of untrusted code
- Minimal privilege requirements
- Comprehensive error handling

### Planned Security Enhancements
- Certificate chain validation
- CRL/OCSP checking
- Enhanced logging for security events
- Rate limiting for API endpoints

## Security Best Practices

### For Users
- Keep TLS Certificate Monitor updated
- Use strong file permissions on configuration files
- Monitor logs for suspicious activity
- Run with minimal required privileges
- Use HTTPS when exposing the web interface

### For Contributors
- Follow secure coding practices
- Validate all inputs
- Handle errors gracefully
- Avoid hardcoded secrets
- Use type hints for better code safety
- Write security-focused tests

## Vulnerability Categories

### High Priority
- Remote code execution
- Authentication bypass
- Information disclosure
- Privilege escalation

### Medium Priority  
- Denial of service
- Configuration vulnerabilities
- Dependency vulnerabilities
- Logic flaws

### Low Priority
- Information leakage
- Minor input validation issues
- Documentation security issues

## Contact

For security concerns that don't warrant a security advisory:
- Email: [Security contact to be added]
- GitHub Discussions: For general security questions

Thank you for helping keep TLS Certificate Monitor secure! 🔒