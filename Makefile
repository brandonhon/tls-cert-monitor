# ============================
# TLS Certificate Monitor Makefile
# ============================

# ----------------------------
# Shell & Environment Setup
# ----------------------------
SHELL := /bin/bash
.DEFAULT_GOAL := help

# ----------------------------
# Project Variables
# ----------------------------
PROJECT_NAME := tls-cert-monitor
PYTHON := python3
VENV_DIR := .venv
VENV_PYTHON := $(VENV_DIR)/bin/python
VENV_PIP := $(VENV_DIR)/bin/pip
REQUIREMENTS := requirements.txt
DEV_REQUIREMENTS := requirements-dev.txt

# Source directories
SRC_DIR := tls_cert_monitor
TESTS_DIR := tests
SCRIPTS_DIR := scripts

# Build and distribution
BUILD_DIR := build
DIST_DIR := dist
COVERAGE_DIR := coverage

# Configuration
CONFIG_FILE := config.yaml
EXAMPLE_CONFIG := config.example.yaml

# ----------------------------
# Color Output
# ----------------------------
BLUE := \033[1;34m
GREEN := \033[1;32m
YELLOW := \033[1;33m
RED := \033[1;31m
NC := \033[0m # No Color

# ----------------------------
# Help Target
# ----------------------------
.PHONY: help
help: ## Show this help message
	@echo ""
	@printf "$(BLUE)🔹 TLS Certificate Monitor - Available Commands 🔹$(NC)\n\n"
	@grep -E '^[a-zA-Z0-9_-]+:.*?## .*$$' $(MAKEFILE_LIST) \
		| sort \
		| awk 'BEGIN {FS = ":.*?## "}; {printf "  $(GREEN)%-20s$(NC) %s\n", $$1, $$2}'
	@echo ""
	@printf "$(YELLOW)💡 Run 'make <target>' to execute a command.$(NC)\n\n"

# ----------------------------
# Virtual Environment
# ----------------------------
.PHONY: venv
venv: $(VENV_DIR)/pyvenv.cfg ## Create virtual environment

$(VENV_DIR)/pyvenv.cfg:
	@echo "$(BLUE)🐍 Creating virtual environment...$(NC)"
	$(PYTHON) -m venv $(VENV_DIR)
	$(VENV_PIP) install --upgrade pip setuptools wheel
	@echo "$(GREEN)✅ Virtual environment created$(NC)"

.PHONY: venv-clean
venv-clean: ## Remove virtual environment
	@echo "$(BLUE)🧹 Removing virtual environment...$(NC)"
	rm -rf $(VENV_DIR)
	@echo "$(GREEN)✅ Virtual environment removed$(NC)"

# ----------------------------
# Dependencies
# ----------------------------
.PHONY: install
install: venv ## Install dependencies in virtual environment
	@echo "$(BLUE)📦 Installing dependencies...$(NC)"
	$(VENV_PIP) install -r $(REQUIREMENTS)
	@echo "$(GREEN)✅ Dependencies installed$(NC)"

.PHONY: install-dev
install-dev: venv ## Install development dependencies
	@echo "$(BLUE)📦 Installing development dependencies...$(NC)"
	$(VENV_PIP) install -r $(REQUIREMENTS)
	$(VENV_PIP) install -r $(DEV_REQUIREMENTS)
	@echo "$(GREEN)✅ Development dependencies installed$(NC)"

.PHONY: install-system
install-system: ## Install dependencies system-wide (no venv)
	@echo "$(BLUE)📦 Installing dependencies system-wide...$(NC)"
	$(PYTHON) -m pip install -r $(REQUIREMENTS)
	@echo "$(GREEN)✅ Dependencies installed system-wide$(NC)"

.PHONY: install-dev-system
install-dev-system: ## Install development dependencies system-wide
	@echo "$(BLUE)📦 Installing development dependencies system-wide...$(NC)"
	$(PYTHON) -m pip install -r $(REQUIREMENTS)
	$(PYTHON) -m pip install -r $(DEV_REQUIREMENTS)
	@echo "$(GREEN)✅ Development dependencies installed system-wide$(NC)"

.PHONY: freeze
freeze: ## Freeze current dependencies to requirements.txt
	@if [ -d "$(VENV_DIR)" ]; then \
		echo "$(BLUE)❄️  Freezing venv dependencies...$(NC)"; \
		$(VENV_PIP) freeze > $(REQUIREMENTS); \
	else \
		echo "$(BLUE)❄️  Freezing system dependencies...$(NC)"; \
		$(PYTHON) -m pip freeze > $(REQUIREMENTS); \
	fi
	@echo "$(GREEN)✅ Dependencies frozen to $(REQUIREMENTS)$(NC)"

# ----------------------------
# Code Quality
# ----------------------------
.PHONY: format
format: ## Format code with black and isort
	@echo "$(BLUE)🎨 Formatting code...$(NC)"
	@if [ -d "$(VENV_DIR)" ]; then \
		$(VENV_PYTHON) -m black $(SRC_DIR) $(TESTS_DIR) main.py; \
		$(VENV_PYTHON) -m isort $(SRC_DIR) $(TESTS_DIR) main.py; \
	else \
		$(PYTHON) -m black $(SRC_DIR) $(TESTS_DIR) main.py; \
		$(PYTHON) -m isort $(SRC_DIR) $(TESTS_DIR) main.py; \
	fi
	@echo "$(GREEN)✅ Code formatted$(NC)"

.PHONY: lint
lint: ## Run linting with flake8 and pylint
	@echo "$(BLUE)🔍 Running linters...$(NC)"
	@if [ -d "$(VENV_DIR)" ]; then \
		$(VENV_PYTHON) -m flake8 $(SRC_DIR) $(TESTS_DIR) main.py; \
		$(VENV_PYTHON) -m pylint $(SRC_DIR) main.py; \
	else \
		$(PYTHON) -m flake8 $(SRC_DIR) $(TESTS_DIR) main.py; \
		$(PYTHON) -m pylint $(SRC_DIR) main.py; \
	fi
	@echo "$(GREEN)✅ Linting completed$(NC)"

.PHONY: type-check
type-check: ## Run type checking with mypy
	@echo "$(BLUE)🔍 Running type checker...$(NC)"
	@if [ -d "$(VENV_DIR)" ]; then \
		$(VENV_PYTHON) -m mypy $(SRC_DIR) main.py; \
	else \
		$(PYTHON) -m mypy $(SRC_DIR) main.py; \
	fi
	@echo "$(GREEN)✅ Type checking completed$(NC)"

.PHONY: security
security: ## Run security checks with bandit
	@echo "$(BLUE)🔐 Running security checks...$(NC)"
	@if [ -d "$(VENV_DIR)" ]; then \
		$(VENV_PYTHON) -m bandit -r $(SRC_DIR) main.py; \
	else \
		$(PYTHON) -m bandit -r $(SRC_DIR) main.py; \
	fi
	@echo "$(GREEN)✅ Security checks completed$(NC)"

.PHONY: check
check: format lint type-check security ## Run all code quality checks

# ----------------------------
# Testing
# ----------------------------
.PHONY: test
test: ## Run tests with pytest
	@echo "$(BLUE)🧪 Running tests...$(NC)"
	@if [ -d "$(VENV_DIR)" ]; then \
		$(VENV_PYTHON) -m pytest $(TESTS_DIR) -v; \
	else \
		$(PYTHON) -m pytest $(TESTS_DIR) -v; \
	fi
	@echo "$(GREEN)✅ Tests completed$(NC)"

.PHONY: test-coverage
test-coverage: ## Run tests with coverage report
	@echo "$(BLUE)🧪 Running tests with coverage...$(NC)"
	@mkdir -p $(COVERAGE_DIR)
	@if [ -d "$(VENV_DIR)" ]; then \
		$(VENV_PYTHON) -m pytest $(TESTS_DIR) \
			--cov=$(SRC_DIR) \
			--cov-report=html:$(COVERAGE_DIR)/html \
			--cov-report=xml:$(COVERAGE_DIR)/coverage.xml \
			--cov-report=term-missing; \
	else \
		$(PYTHON) -m pytest $(TESTS_DIR) \
			--cov=$(SRC_DIR) \
			--cov-report=html:$(COVERAGE_DIR)/html \
			--cov-report=xml:$(COVERAGE_DIR)/coverage.xml \
			--cov-report=term-missing; \
	fi
	@echo "$(GREEN)✅ Coverage report generated in $(COVERAGE_DIR)/$(NC)"

.PHONY: test-watch
test-watch: ## Run tests in watch mode
	@echo "$(BLUE)👀 Running tests in watch mode...$(NC)"
	@if [ -d "$(VENV_DIR)" ]; then \
		$(VENV_PYTHON) -m pytest-watch $(TESTS_DIR) -- -v; \
	else \
		$(PYTHON) -m pytest-watch $(TESTS_DIR) -- -v; \
	fi

# ----------------------------
# Running the Application
# ----------------------------
.PHONY: run
run: ## Run the application with virtual environment
	@echo "$(BLUE)🚀 Starting TLS Certificate Monitor (venv)...$(NC)"
	@if [ ! -d "$(VENV_DIR)" ]; then \
		echo "$(RED)❌ Virtual environment not found. Run 'make install' first.$(NC)"; \
		exit 1; \
	fi
	$(VENV_PYTHON) main.py $(ARGS)

.PHONY: run-system
run-system: ## Run the application with system Python
	@echo "$(BLUE)🚀 Starting TLS Certificate Monitor (system)...$(NC)"
	$(PYTHON) main.py $(ARGS)

.PHONY: run-config
run-config: $(CONFIG_FILE) ## Run with configuration file
	@echo "$(BLUE)🚀 Starting with config file...$(NC)"
	@if [ -d "$(VENV_DIR)" ]; then \
		$(VENV_PYTHON) main.py --config $(CONFIG_FILE); \
	else \
		$(PYTHON) main.py --config $(CONFIG_FILE); \
	fi

.PHONY: run-dev
run-dev: ## Run in development mode with hot reload
	@echo "$(BLUE)🚀 Starting in development mode...$(NC)"
	@if [ -d "$(VENV_DIR)" ]; then \
		$(VENV_PYTHON) -m uvicorn main:app --reload --host 0.0.0.0 --port 3200; \
	else \
		$(PYTHON) -m uvicorn main:app --reload --host 0.0.0.0 --port 3200; \
	fi

# ----------------------------
# Configuration
# ----------------------------
$(CONFIG_FILE):
	@if [ ! -f "$(CONFIG_FILE)" ] && [ -f "$(EXAMPLE_CONFIG)" ]; then \
		echo "$(BLUE)📝 Creating config file from example...$(NC)"; \
		cp $(EXAMPLE_CONFIG) $(CONFIG_FILE); \
		echo "$(GREEN)✅ Config file created: $(CONFIG_FILE)$(NC)"; \
	fi

.PHONY: config
config: $(CONFIG_FILE) ## Create configuration file from example

# ----------------------------
# Build and Distribution
# ----------------------------
.PHONY: build
build: clean ## Build distribution packages
	@echo "$(BLUE)🔨 Building distribution packages...$(NC)"
	@if [ -d "$(VENV_DIR)" ]; then \
		$(VENV_PYTHON) setup.py sdist bdist_wheel; \
	else \
		$(PYTHON) setup.py sdist bdist_wheel; \
	fi
	@echo "$(GREEN)✅ Build completed$(NC)"

.PHONY: install-local
install-local: build ## Install package locally
	@echo "$(BLUE)📦 Installing package locally...$(NC)"
	@if [ -d "$(VENV_DIR)" ]; then \
		$(VENV_PIP) install -e .; \
	else \
		$(PYTHON) -m pip install -e .; \
	fi
	@echo "$(GREEN)✅ Package installed locally$(NC)"

# ----------------------------
# Docker Support
# ----------------------------
.PHONY: docker-build
docker-build: ## Build Docker image
	@echo "$(BLUE)🐳 Building Docker image...$(NC)"
	docker build -t $(PROJECT_NAME):latest .
	@echo "$(GREEN)✅ Docker image built$(NC)"

.PHONY: docker-run
docker-run: ## Run Docker container
	@echo "$(BLUE)🐳 Running Docker container...$(NC)"
	docker run --rm -p 3200:3200 \
		-v $(PWD)/certs:/app/certs:ro \
		-v $(PWD)/config.yaml:/app/config.yaml:ro \
		$(PROJECT_NAME):latest

# ----------------------------
# Utilities
# ----------------------------
.PHONY: clean
clean: ## Clean build artifacts and cache
	@echo "$(BLUE)🧹 Cleaning build artifacts...$(NC)"
	rm -rf $(BUILD_DIR) $(DIST_DIR) $(COVERAGE_DIR)
	rm -rf *.egg-info
	find . -type d -name __pycache__ -exec rm -rf {} + 2>/dev/null || true
	find . -type f -name "*.pyc" -delete
	find . -type f -name "*.pyo" -delete
	find . -type f -name "*.pyd" -delete
	find . -type f -name ".coverage" -delete
	@echo "$(GREEN)✅ Cleanup completed$(NC)"

.PHONY: clean-all
clean-all: clean venv-clean ## Clean everything including virtual environment
	@echo "$(GREEN)✅ Full cleanup completed$(NC)"

.PHONY: deps-update
deps-update: ## Update all dependencies to latest versions
	@echo "$(BLUE)⬆️  Updating dependencies...$(NC)"
	@if [ -d "$(VENV_DIR)" ]; then \
		$(VENV_PIP) install --upgrade pip; \
		$(VENV_PIP) list --outdated --format=freeze | grep -v '^\-e' | cut -d = -f 1 | xargs -n1 $(VENV_PIP) install --upgrade; \
	else \
		$(PYTHON) -m pip install --upgrade pip; \
		$(PYTHON) -m pip list --outdated --format=freeze | grep -v '^\-e' | cut -d = -f 1 | xargs -n1 $(PYTHON) -m pip install --upgrade; \
	fi
	@echo "$(GREEN)✅ Dependencies updated$(NC)"

.PHONY: check-deps
check-deps: ## Check for dependency vulnerabilities
	@echo "$(BLUE)🔍 Checking dependencies for vulnerabilities...$(NC)"
	@if [ -d "$(VENV_DIR)" ]; then \
		$(VENV_PIP) install safety; \
		$(VENV_PYTHON) -m safety check; \
	else \
		$(PYTHON) -m pip install safety; \
		$(PYTHON) -m safety check; \
	fi
	@echo "$(GREEN)✅ Dependency check completed$(NC)"

# ----------------------------
# Development Setup
# ----------------------------
.PHONY: setup-dev
setup-dev: install-dev config ## Setup complete development environment
	@echo "$(GREEN)✅ Development environment setup completed$(NC)"
	@echo "$(YELLOW)💡 You can now run 'make run' to start the application$(NC)"

.PHONY: setup-dev-system
setup-dev-system: install-dev-system config ## Setup development environment with system Python
	@echo "$(GREEN)✅ Development environment setup completed (system Python)$(NC)"
	@echo "$(YELLOW)💡 You can now run 'make run-system' to start the application$(NC)"

# ----------------------------
# Information
# ----------------------------
.PHONY: info
info: ## Show project information
	@echo "$(BLUE)📊 Project Information$(NC)"
	@echo "  Project Name: $(PROJECT_NAME)"
	@echo "  Python: $(shell $(PYTHON) --version 2>&1)"
	@echo "  Virtual Environment: $(if $(wildcard $(VENV_DIR)),$(GREEN)Active$(NC),$(RED)Not created$(NC))"
	@echo "  Source Directory: $(SRC_DIR)"
	@echo "  Tests Directory: $(TESTS_DIR)"
	@echo "  Configuration: $(if $(wildcard $(CONFIG_FILE)),$(GREEN)$(CONFIG_FILE)$(NC),$(RED)Not found$(NC))"
	@echo ""

# Prevent make from treating files as targets
.PHONY: $(REQUIREMENTS) $(DEV_REQUIREMENTS)