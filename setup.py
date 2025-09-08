"""
Setup script for TLS Certificate Monitor.
"""

from setuptools import setup, find_packages
from pathlib import Path

# Read requirements
def read_requirements(filename):
    """Read requirements from file."""
    requirements_path = Path(__file__).parent / filename
    if requirements_path.exists():
        with open(requirements_path, 'r', encoding='utf-8') as f:
            return [line.strip() for line in f if line.strip() and not line.startswith('#')]
    return []

# Read long description from README
readme_path = Path(__file__).parent / 'README.md'
long_description = readme_path.read_text(encoding='utf-8') if readme_path.exists() else ""

setup(
    name="tls-cert-monitor",
    version="1.0.0",
    description="Cross-platform TLS certificate monitoring application",
    long_description=long_description,
    long_description_content_type="text/markdown",
    author="TLS Certificate Monitor Team",
    author_email="",
    url="https://github.com/your-org/tls-cert-monitor",
    packages=find_packages(),
    include_package_data=True,
    install_requires=read_requirements('requirements.txt'),
    extras_require={
        'dev': read_requirements('requirements-dev.txt'),
    },
    entry_points={
        'console_scripts': [
            'tls-cert-monitor=main:main',
        ],
    },
    classifiers=[
        "Development Status :: 4 - Beta",
        "Intended Audience :: System Administrators",
        "Intended Audience :: Developers",
        "License :: OSI Approved :: MIT License",
        "Operating System :: OS Independent",
        "Programming Language :: Python :: 3",
        "Programming Language :: Python :: 3.8",
        "Programming Language :: Python :: 3.9",
        "Programming Language :: Python :: 3.10",
        "Programming Language :: Python :: 3.11",
        "Programming Language :: Python :: 3.12",
        "Topic :: System :: Monitoring",
        "Topic :: System :: Systems Administration",
        "Topic :: Security :: Cryptography",
    ],
    python_requires=">=3.8",
    keywords="tls ssl certificates monitoring prometheus metrics security",
    project_urls={
        "Bug Reports": "https://github.com/your-org/tls-cert-monitor/issues",
        "Source": "https://github.com/your-org/tls-cert-monitor",
        "Documentation": "https://github.com/your-org/tls-cert-monitor/wiki",
    },
)