# ============================
# TLS Certificate Monitor - Streamlined Makefile
# ============================

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
NUITKA := $(VENV_PYTHON) -m nuitka

# Nuitka build flags
NUITKA_FLAGS := --onefile --standalone --enable-plugin=pkg-resources --assume-yes-for-downloads

# Include package for your source code
INCLUDE_SRC := --include-package=tls_cert_monitor

# ----------------------------
# Colors
# ----------------------------
BLUE := \033[1;34m
GREEN := \033[1;32m
YELLOW := \033[1;33m
RED := \033[1;31m
NC := \033[0m

# ----------------------------
# Help
# ----------------------------
.PHONY: help
help: ## Show this help message
	@printf "\n$(BLUE)📋 TLS Certificate Monitor - Available Commands$(NC)\n\n"
	@grep -E '^[a-zA-Z_-]+:.*?## .*$$' $(MAKEFILE_LIST) | sort | awk 'BEGIN {FS = ":.*?## "}; {printf "  $(BLUE)%-15s$(NC) %s\n", $$1, $$2}'
	@printf "\n"

# ----------------------------
# Development Environment
# ----------------------------
.PHONY: setup
setup: ## Setup development environment (venv + deps + config)
	@printf "$(BLUE)🔧 Setting up development environment...$(NC)\n"
	@$(PYTHON) -m venv $(VENV_DIR)
	@$(VENV_PIP) install --upgrade pip setuptools wheel
	@$(VENV_PIP) install -r requirements.txt
	@$(VENV_PIP) install -r requirements-dev.txt
	@if [ ! -f config.yaml ]; then \
		./scripts/generate-config-dev.sh; \
	fi
	@./scripts/generate-test-certs.sh
	@printf "$(GREEN)✅ Development environment ready$(NC)\n"

.PHONY: venv
venv: ## Create virtual environment only
	@printf "$(BLUE)🐍 Creating virtual environment...$(NC)\n"
	@$(PYTHON) -m venv $(VENV_DIR)
	@$(VENV_PIP) install --upgrade pip setuptools wheel
	@$(VENV_PIP) install -r requirements.txt
	@$(VENV_PIP) install -r requirements-dev.txt
	@printf "$(GREEN)✅ Virtual environment created$(NC)\n"

# ----------------------------
# Code Quality
# ----------------------------
.PHONY: format
format: ## Format code with black and isort
	@printf "$(BLUE)🎨 Formatting code...$(NC)\n"
	@$(VENV_PYTHON) -m black .
	@$(VENV_PYTHON) -m isort .
	@printf "$(GREEN)✅ Code formatted$(NC)\n"

.PHONY: lint
lint: ## Run linters (flake8, pylint)
	@printf "$(BLUE)🔍 Running linters...$(NC)\n"
	@$(VENV_PYTHON) -m flake8 . --ignore=E501,W503 --exclude=.venv,build,dist,*.egg-info,.git,__pycache__,.pytest_cache,.mypy_cache
	@$(VENV_PYTHON) -m pylint tls_cert_monitor/ --disable=C,R,I,W1203,W0718,W0212 --msg-template='{path}:{line}: {msg_id}: {msg}'
	@printf "$(GREEN)✅ Linting completed$(NC)\n"

.PHONY: typecheck
typecheck: ## Run mypy type checking
	@printf "$(BLUE)🔍 Running type checker...$(NC)\n"
	@$(VENV_PYTHON) -m mypy tls_cert_monitor/
	@printf "$(GREEN)✅ Type checking completed$(NC)\n"

.PHONY: security
security: ## Run security checks with bandit
	@printf "$(BLUE)🔐 Running security checks...$(NC)\n"
	@$(VENV_PYTHON) -m bandit -r tls_cert_monitor/ -f json -o bandit-report.json --skip B104
	@$(VENV_PYTHON) -m bandit -r tls_cert_monitor/
	@printf "$(GREEN)✅ Security checks completed$(NC)\n"

.PHONY: check
check: format lint typecheck security ## Run all code quality checks

# ----------------------------
# Testing
# ----------------------------
.PHONY: test
test: ## Run tests
	@printf "$(BLUE)🧪 Running tests...$(NC)\n"
	@$(VENV_PYTHON) -m pytest tests/ -v
	@printf "$(GREEN)✅ Tests completed$(NC)\n"

.PHONY: test-cov
test-cov: ## Run tests with coverage
	@printf "$(BLUE)🧪 Running tests with coverage...$(NC)\n"
	@$(VENV_PYTHON) -m pytest tests/ --cov=tls_cert_monitor --cov-report=html --cov-report=xml --cov-report=term
	@printf "$(GREEN)✅ Coverage report generated$(NC)\n"

# ----------------------------
# Running
# ----------------------------
.PHONY: run
run: ## Run the application
	@printf "$(BLUE)🚀 Starting TLS Certificate Monitor...$(NC)\n"
	@printf "WARNING: Running with default config (config.py:188)"
	@$(VENV_PYTHON) main.py

.PHONY: dev
dev: certs config ## Run in development mode with uvicorn hot reload
	@printf "$(BLUE)🚀 Starting in development mode with uvicorn reload...$(NC)\n"
	@TLS_CONFIG=./tests/fixtures/configs/config.dev.yaml \
		$(VENV_PYTHON) -m uvicorn dev_server:app --reload --host 0.0.0.0 --port 3200

.PHONY: dev-no-reload
dev-no-reload: certs config ## Run in development mode with config hot reload only
	@printf "$(BLUE)🚀 Starting in development mode with config hot reload only...$(NC)\n"
	@TLS_CONFIG=./tests/fixtures/configs/config.dev.yaml \
		$(VENV_PYTHON) -m uvicorn dev_server:app --host 0.0.0.0 --port 3200

.PHONY: dry-run
dry-run: certs config ## Run in dry-run mode (scan only, no server)
	@printf "$(BLUE)🔍 Running in dry-run mode...$(NC)\n"
	@$(VENV_PYTHON) main.py --config tests/fixtures/configs/config.dev.yaml --dry-run

.PHONY: stop
stop: ## Stop the development server
	@printf "$(BLUE)🛑 Stopping TLS Certificate Monitor...$(NC)\n"
	@found=0; \
	for pid in $$(ps aux | grep -E "[u]vicorn dev_server:app|[p]ython.*main\.py" | awk '{print $$2}'); do \
	  if kill $$pid 2>/dev/null; then \
	    found=1; \
	  fi; \
	done; \
	if [ $$found -eq 1 ]; then \
	  printf "$(GREEN)✅ Server processes stopped$(NC)\n"; \
	else \
	  printf "$(YELLOW)⚠️  No running processes found$(NC)\n"; \
	fi

# ----------------------------
# Building
# ----------------------------
.PHONY: build
build: ## Build distribution packages
	@printf "$(BLUE)🔨 Building distribution packages...$(NC)\n"
	@$(VENV_PYTHON) -m build
	@printf "$(GREEN)✅ Build completed - packages in dist/$(NC)\n"

# ----------------------------
# Build Dependencies Check
# ----------------------------
.PHONY: check-build-deps
check-build-deps: ## Check if build dependencies are available
	@printf "$(BLUE)🔍 Checking build dependencies...$(NC)\n"
	@if ! $(VENV_PYTHON) -c "import nuitka" >/dev/null 2>&1; then \
		printf "$(RED)❌ Nuitka not found - installing...$(NC)\n"; \
		$(VENV_PIP) install nuitka; \
	else \
		printf "$(GREEN)✅ Nuitka available$(NC)\n"; \
	fi
	@if command -v clang >/dev/null 2>&1; then \
		printf "$(GREEN)✅ Clang compiler available$(NC)\n"; \
	elif command -v gcc >/dev/null 2>&1; then \
		printf "$(YELLOW)⚠️  GCC available (Clang recommended for better performance)$(NC)\n"; \
	else \
		printf "$(RED)❌ No C compiler found - install clang or gcc$(NC)\n"; \
		exit 1; \
	fi

# ----------------------------
# Native Nuitka Builds (Local Platform)
# ----------------------------
.PHONY: build-native
build-native: check-build-deps ## Build binary for current platform using local Nuitka
	@printf "$(BLUE)🔧 Building native binary for $$(uname -s)...$(NC)\n"
	@mkdir -p dist
	@$(NUITKA) $(NUITKA_FLAGS) $(INCLUDE_SRC) \
		--jobs=4 \
		--clang \
		--lto=no \
		--nofollow-import-to=numpy \
		--nofollow-import-to=matplotlib \
		main.py \
		--output-dir=dist \
		--output-filename=$(PROJECT_NAME)-$$(uname -s | tr '[:upper:]' '[:lower:]')
	@printf "$(GREEN)✅ Native binary: dist/$(PROJECT_NAME)-$$(uname -s | tr '[:upper:]' '[:lower:]')$(NC)\n"

.PHONY: build-linux
build-linux: ## Build Linux binary (Docker fallback if not on Linux)
	@if [ "$$(uname)" = "Linux" ]; then \
		printf "$(BLUE)🐧 Building Linux binary locally...$(NC)\n"; \
		mkdir -p dist; \
		$(NUITKA) $(NUITKA_FLAGS) $(INCLUDE_SRC) \
			--jobs=4 \
			--clang \
			--lto=no \
			--nofollow-import-to=numpy \
			--nofollow-import-to=matplotlib \
			main.py \
			--output-dir=dist \
			--output-filename=$(PROJECT_NAME)-linux; \
		printf "$(GREEN)✅ Linux binary: dist/$(PROJECT_NAME)-linux$(NC)\n"; \
	else \
		printf "$(YELLOW)⚠️  Not on Linux - attempting Docker build...$(NC)\n"; \
		if command -v docker >/dev/null 2>&1 && [ -f build/Dockerfile.linux ]; then \
			mkdir -p dist; \
			docker build -f build/Dockerfile.linux -t $(PROJECT_NAME)-builder-linux .; \
			docker run --rm -v $$(pwd)/dist:/app/dist $(PROJECT_NAME)-builder-linux; \
			printf "$(GREEN)✅ Linux binary: dist/$(PROJECT_NAME)-linux$(NC)\n"; \
		else \
			printf "$(RED)❌ Docker not available or Dockerfile.linux not found$(NC)\n"; \
			printf "$(YELLOW)💡 Run 'make build-native' to build for current platform$(NC)\n"; \
			exit 1; \
		fi \
	fi

.PHONY: build-windows
build-windows: ## Build Windows binary (Docker fallback if not on Windows)
	@if [ "$$(uname | grep -i cygwin\|mingw\|msys)" ] || [ "$$(uname)" = "MINGW64_NT-10.0" ]; then \
		printf "$(BLUE)🪟 Building Windows binary locally...$(NC)\n"; \
		mkdir -p dist; \
		$(NUITKA) $(NUITKA_FLAGS) $(INCLUDE_SRC) \
			--jobs=4 \
			--clang \
			--lto=no \
			--nofollow-import-to=numpy \
			--nofollow-import-to=matplotlib \
			main.py \
			--output-dir=dist \
			--output-filename=$(PROJECT_NAME)-windows.exe; \
		printf "$(GREEN)✅ Windows binary: dist/$(PROJECT_NAME)-windows.exe$(NC)\n"; \
	else \
		printf "$(YELLOW)⚠️  Not on Windows - attempting Docker build...$(NC)\n"; \
		if command -v docker >/dev/null 2>&1 && [ -f build/Dockerfile.windows ]; then \
			mkdir -p dist; \
			docker build -f build/Dockerfile.windows -t $(PROJECT_NAME)-builder-windows .; \
			docker run --rm -v $$(pwd)/dist:/app/dist $(PROJECT_NAME)-builder-windows; \
			printf "$(GREEN)✅ Windows binary: dist/$(PROJECT_NAME)-windows.exe$(NC)\n"; \
		else \
			printf "$(RED)❌ Docker not available or Dockerfile.windows not found$(NC)\n"; \
			printf "$(YELLOW)💡 Run 'make build-native' to build for current platform$(NC)\n"; \
			exit 1; \
		fi \
	fi

.PHONY: build-macos
build-macos: ## Build macOS binary (requires macOS)
	@if [ "$$(uname)" = "Darwin" ]; then \
		printf "$(BLUE)🍎 Building macOS binary locally...$(NC)\n"; \
		mkdir -p dist; \
		$(NUITKA) $(NUITKA_FLAGS) $(INCLUDE_SRC) \
			--jobs=4 \
			--clang \
			--lto=no \
			--nofollow-import-to=numpy \
			--nofollow-import-to=matplotlib \
			main.py \
			--output-dir=dist \
			--output-filename=$(PROJECT_NAME)-macos; \
		printf "$(GREEN)✅ macOS binary: dist/$(PROJECT_NAME)-macos$(NC)\n"; \
	else \
		printf "$(RED)❌ macOS builds require macOS platform$(NC)\n"; \
		printf "$(YELLOW)💡 Run 'make build-native' to build for current platform$(NC)\n"; \
		exit 1; \
	fi

.PHONY: build-all
build-all: ## Build for all platforms (tries native first, falls back to Docker)
	@printf "$(BLUE)🔨 Building for all supported platforms...$(NC)\n"
	@make build-native
	@if [ "$$(uname)" != "Linux" ]; then make build-linux || true; fi
	@if [ "$$(uname | grep -i cygwin\|mingw\|msys)" = "" ] && [ "$$(uname)" != "MINGW64_NT-10.0" ]; then make build-windows || true; fi
	@if [ "$$(uname)" != "Darwin" ]; then make build-macos || true; fi
	@printf "$(GREEN)✅ Multi-platform build completed$(NC)\n"

# Development build (faster, less optimized)
.PHONY: build-dev
build-dev: check-build-deps ## Build development binary (faster compilation, less optimized)
	@printf "$(BLUE)⚡ Building development binary (fast build)...$(NC)\n"
	@mkdir -p dist
	@$(NUITKA) --onefile --standalone \
		--assume-yes-for-downloads \
		--enable-plugin=pkg-resources \
		$(INCLUDE_SRC) \
		main.py \
		--output-dir=dist \
		--output-filename=$(PROJECT_NAME)-dev
	@printf "$(GREEN)✅ Development binary: dist/$(PROJECT_NAME)-dev$(NC)\n"

# Alias for backward compatibility
.PHONY: build-local
build-local: build-native ## Alias for build-native (backward compatibility)

# ----------------------------
# Installation
# ----------------------------
.PHONY: install
install: build ## Install the package locally
	@printf "$(BLUE)📦 Installing package locally...$(NC)\n"
	@$(VENV_PIP) install dist/*.whl --force-reinstall
	@printf "$(GREEN)✅ Package installed$(NC)\n"

# ----------------------------
# Docker
# ----------------------------
.PHONY: docker-build
docker-build: ## Build Docker image
	@printf "$(BLUE)🐳 Building Docker image...$(NC)\n"
	@docker build -t $(PROJECT_NAME) .
	@printf "$(GREEN)✅ Docker image built: $(PROJECT_NAME)$(NC)\n"

.PHONY: docker-run
docker-run: ## Run Docker container
	@printf "$(BLUE)🐳 Running Docker container...$(NC)\n"
	@docker run --rm -p 3200:3200 \
		-v $$(pwd)/certs:/app/certs:ro \
		-v $$(pwd)/config.yaml:/app/config.yaml:ro \
		$(PROJECT_NAME)

.PHONY: docker-compose
docker-compose: ## Run with docker-compose
	@printf "$(BLUE)🐳 Starting with docker-compose...$(NC)\n"
	@docker compose up --build

.PHONY: docker-compose-dev
docker-compose-dev: ## Run with docker-compose
	@printf "$(BLUE)🐳 Starting docker compose development mode...$(NC)\n"
	@docker compose -f docker-compose.dev.yml --profile monitoring up -d --build

# ----------------------------
# Configuration & Certificates
# ----------------------------
.PHONY: config
config: ## Generate development configuration
	@if [ -f tests/fixtures/configs/config.dev.yaml ]; then \
		printf "$(YELLOW)⚠️  Development config already exists, skipping generation$(NC)\n"; \
	else \
		printf "$(BLUE)📝 Generating development configuration...$(NC)\n"; \
		./scripts/generate-config-dev.sh; \
		printf "$(GREEN)✅ Development configuration generated$(NC)\n"; \
	fi

.PHONY: certs
certs: ## Generate test certificates
	@if [ -d tests/fixtures/certs ] && [ -n "$$(ls -A tests/fixtures/certs 2>/dev/null)" ]; then \
		printf "$(YELLOW)⚠️  Test certificates already exist, skipping generation$(NC)\n"; \
	else \
		printf "$(BLUE)🔐 Generating test certificates...$(NC)\n"; \
		./scripts/generate-test-certs.sh; \
		printf "$(GREEN)✅ Test certificates generated$(NC)\n"; \
	fi

# ----------------------------
# Cleanup
# ----------------------------
.PHONY: clean
clean: ## Clean development artifacts
	@printf "$(BLUE)🧹 Cleaning development artifacts...$(NC)\n"
	@rm -rf build/ dist/ *.egg-info/ .pytest_cache/ .coverage htmlcov/ coverage/ .mypy_cache/
	@find . -type d -name __pycache__ -exec rm -rf {} + 2>/dev/null || true
	@rm -f bandit-report.json .dev_server.pid
	@printf "$(GREEN)✅ Cleanup completed$(NC)\n"

.PHONY: clean-all
clean-all: clean ## Clean everything including venv, config, and certs
	@printf "$(BLUE)🧹 Deep cleaning everything...$(NC)\n"
	@rm -rf $(VENV_DIR)/ tests/fixtures/certs/ tests/fixtures/configs/ config.yaml config-dev.yaml
	@printf "$(GREEN)✅ Everything cleaned$(NC)\n"

# ----------------------------
# Info
# ----------------------------
.PHONY: info
info: ## Show project information
	@printf "$(BLUE)📊 Project Information$(NC)\n"
	@printf "  Project Name: $(PROJECT_NAME)\n"
	@printf "  Python: $$($(PYTHON) --version 2>&1)\n"
	@printf "  Virtual Environment: $(if $(wildcard $(VENV_DIR)),$(GREEN)Active$(NC),$(RED)Not created$(NC))\n"
	@printf "  Configuration: $(if $(wildcard config.yaml),$(GREEN)config.yaml$(NC),$(if $(wildcard tests/fixtures/configs/*.yaml),$(GREEN)tests/fixtures/configs/*.yaml$(NC),$(RED)Not found$(NC)))\n"
	@printf "  Test Certificates: $(if $(wildcard tests/fixtures/certs/),$(GREEN)Available$(NC),$(RED)Not generated$(NC))\n"
	@printf "\n"