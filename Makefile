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
NUITKA_WINSVC := $(VENV_PYTHON) -m nuitka

# Nuitka build flags (--onefile for single executable deployment)
NUITKA_FLAGS := --onefile --enable-plugin=pkg-resources --assume-yes-for-downloads

# Windows-specific Nuitka-winsvc flags for native Windows service support
NUITKA_WIN_FLAGS := --windows-service --windows-service-name=TLSCertMonitor --windows-service-display-name="TLS Certificate Monitor" --windows-service-description="Monitor TLS/SSL certificates for expiration and security issues" --windows-service-install="install" --windows-service-uninstall="uninstall"

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
	@$(VENV_PYTHON) -m flake8 . --ignore=E501,W503 --exclude=.venv,build,dist,*.egg-info,.git,__pycache__,.pytest_cache,.mypy_cache,YOYO
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
	@$(VENV_PYTHON) -m bandit -r tls_cert_monitor/ -f json -o bandit-report.json --skip B104,B110
	@$(VENV_PYTHON) -m bandit -r tls_cert_monitor/ --skip B110
	@printf "$(GREEN)✅ Security checks completed$(NC)\n"

.PHONY: deadcode
deadcode: ## Detect dead code with vulture
	@printf "$(BLUE)🦅 Running dead code detection...$(NC)\n"
	@# Note: || true makes findings informational only (doesn't fail build)
	@# Some false positives expected (e.g., cls in Pydantic validators)
	@$(VENV_PYTHON) -m vulture tls_cert_monitor/ --min-confidence 80 --exclude=.venv,build,dist || true
	@printf "$(GREEN)✅ Dead code check completed (findings are informational)$(NC)\n"

.PHONY: format-system
format-system: ## Format code with black and isort (system-wide)
	@printf "$(BLUE)🎨 Formatting code (system-wide)...$(NC)\n"
	@$(PYTHON) -m black .
	@$(PYTHON) -m isort .
	@printf "$(GREEN)✅ Code formatted$(NC)\n"

.PHONY: lint-system
lint-system: ## Run linters (system-wide)
	@printf "$(BLUE)🔍 Running linters (system-wide)...$(NC)\n"
	@$(PYTHON) -m flake8 . --ignore=E501,W503 --exclude=.venv,build,dist,*.egg-info,.git,__pycache__,.pytest_cache,.mypy_cache,YOYO
	@$(PYTHON) -m pylint tls_cert_monitor/ --disable=C,R,I,W1203,W0718,W0212 --msg-template='{path}:{line}: {msg_id}: {msg}'
	@printf "$(GREEN)✅ Linting completed$(NC)\n"

.PHONY: typecheck-system
typecheck-system: ## Run mypy type checking (system-wide)
	@printf "$(BLUE)🔍 Running type checker (system-wide)...$(NC)\n"
	@$(PYTHON) -m mypy tls_cert_monitor/
	@printf "$(GREEN)✅ Type checking completed$(NC)\n"

.PHONY: security-system
security-system: ## Run security checks with bandit (system-wide)
	@printf "$(BLUE)🔐 Running security checks (system-wide)...$(NC)\n"
	@$(PYTHON) -m bandit -r tls_cert_monitor/ -f json -o bandit-report.json --skip B104,B110
	@$(PYTHON) -m bandit -r tls_cert_monitor/ --skip B110
	@printf "$(GREEN)✅ Security checks completed$(NC)\n"

.PHONY: deadcode-system
deadcode-system: ## Detect dead code with vulture (system-wide)
	@printf "$(BLUE)🦅 Running dead code detection (system-wide)...$(NC)\n"
	@# Note: || true makes findings informational only (doesn't fail build)
	@# Some false positives expected (e.g., cls in Pydantic validators)
	@$(PYTHON) -m vulture tls_cert_monitor/ --min-confidence 80 --exclude=.venv,build,dist || true
	@printf "$(GREEN)✅ Dead code check completed (findings are informational)$(NC)\n"

.PHONY: test-system
test-system: ## Run tests (system-wide)
	@printf "$(BLUE)🧪 Running tests (system-wide)...$(NC)\n"
	@$(PYTHON) -m pytest tests/ -v
	@printf "$(GREEN)✅ Tests completed$(NC)\n"

.PHONY: check-system
check-system: format-system lint-system typecheck-system security-system deadcode-system ## Run all code quality checks (system-wide)

.PHONY: check
check: format lint typecheck security deadcode ## Run all code quality checks

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

.PHONY: test-unit
test-unit: ## Run unit tests only (exclude integration tests)
	@printf "$(BLUE)🧪 Running unit tests...$(NC)\n"
	@$(VENV_PYTHON) -m pytest tests/ -v -m "not integration"
	@printf "$(GREEN)✅ Unit tests completed$(NC)\n"

.PHONY: test-integration
test-integration: ## Run integration tests only
	@printf "$(BLUE)🚀 Running integration tests...$(NC)\n"
	@printf "$(YELLOW)⚠️  Integration tests start the full application$(NC)\n"
	@$(VENV_PYTHON) -m pytest tests/test_integration.py -v -m integration
	@printf "$(GREEN)✅ Integration tests completed$(NC)\n"

.PHONY: test-all
test-all: test-unit test-integration ## Run all tests (unit + integration)
	@printf "$(GREEN)✅ All tests completed successfully$(NC)\n"

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
		printf "$(BLUE)🪟 Building Windows service binary with Nuitka-winsvc...$(NC)\n"; \
		mkdir -p dist; \
		$(NUITKA_WINSVC) $(NUITKA_FLAGS) $(NUITKA_WIN_FLAGS) $(INCLUDE_SRC) \
			--jobs=4 \
			--clang \
			--lto=no \
			--nofollow-import-to=numpy \
			--nofollow-import-to=matplotlib \
			main.py \
			--output-dir=dist \
			--output-filename=$(PROJECT_NAME)-windows.exe; \
		printf "$(GREEN)✅ Windows service binary: dist/$(PROJECT_NAME)-windows.exe$(NC)\n"; \
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
# Ansible Deployment
# ----------------------------
.PHONY: ansible-setup-info
ansible-setup-info: ## Show Ansible setup information and SSH requirements
	@printf "$(BLUE)📋 Ansible Setup Information$(NC)\n\n"
	@printf "$(YELLOW)📂 Configuration Files:$(NC)\n"
	@printf "  • ansible/inventory/hosts.yml - Define your hosts with SSH connection details\n"
	@printf "  • ansible/group_vars/ - Configure defaults for Linux/Windows hosts\n"
	@printf "  • ansible/group_vars/all/vault.yml - Store encrypted passwords (optional)\n\n"
	@printf "$(YELLOW)🔑 SSH Authentication Methods:$(NC)\n"
	@printf "  • SSH Key (recommended): ansible_ssh_private_key_file: ~/.ssh/id_rsa\n"
	@printf "  • Password: ansible_password: \"{{ vault_password }}\"\n\n"
	@printf "$(YELLOW)🪟 Windows Connection Options:$(NC)\n"
	@printf "  • SSH (recommended): ansible_connection: ssh, ansible_shell_type: powershell\n"
	@printf "  • WinRM (traditional): ansible_connection: winrm\n\n"
	@printf "$(YELLOW)🧪 Testing Commands:$(NC)\n"
	@printf "  • make ansible-ping - Test SSH connectivity\n"
	@printf "  • make ansible-win-ping - Test Windows connectivity\n"
	@printf "  • make ansible-inventory - Show parsed inventory\n\n"
	@printf "$(YELLOW)📚 Documentation:$(NC)\n"
	@printf "  • See ansible/README.md for complete SSH configuration guide\n\n"

.PHONY: ansible-install
ansible-install: ## Deploy tls-cert-monitor using Ansible (configure SSH in inventory first)
	@printf "$(BLUE)🚀 Deploying tls-cert-monitor with Ansible...$(NC)\n"
	@if [ ! -f ansible/inventory/hosts.yml ]; then \
		printf "$(RED)❌ No inventory file found at ansible/inventory/hosts.yml$(NC)\n"; \
		printf "$(YELLOW)💡 Edit ansible/inventory/hosts.yml with your SSH connection details$(NC)\n"; \
		printf "$(YELLOW)💡 Run 'make ansible-setup-info' for configuration help$(NC)\n"; \
		exit 1; \
	fi
	@cd ansible && ansible-playbook playbooks/site.yml
	@printf "$(GREEN)✅ Deployment completed$(NC)\n"

.PHONY: ansible-install-pass
ansible-install-pass: ## Deploy using interactive password authentication (-kbK)
	@printf "$(BLUE)🚀 Deploying tls-cert-monitor with password authentication...$(NC)\n"
	@printf "$(YELLOW)💡 You will be prompted for SSH and sudo passwords$(NC)\n"
	@cd ansible && ansible-playbook playbooks/site.yml -kbK
	@printf "$(GREEN)✅ Deployment completed$(NC)\n"

.PHONY: ansible-uninstall
ansible-uninstall: ## Uninstall tls-cert-monitor using Ansible
	@printf "$(BLUE)🗑️  Uninstalling tls-cert-monitor with Ansible...$(NC)\n"
	@if [ ! -f ansible/inventory/hosts.yml ]; then \
		printf "$(RED)❌ No inventory file found at ansible/inventory/hosts.yml$(NC)\n"; \
		printf "$(YELLOW)💡 Edit ansible/inventory/hosts.yml with your SSH connection details$(NC)\n"; \
		exit 1; \
	fi
	@cd ansible && ansible-playbook playbooks/uninstall.yml
	@printf "$(GREEN)✅ Uninstallation completed$(NC)\n"

.PHONY: ansible-uninstall-pass
ansible-uninstall-pass: ## Uninstall using interactive password authentication (-kbK)
	@printf "$(BLUE)🗑️  Uninstalling tls-cert-monitor with password authentication...$(NC)\n"
	@printf "$(YELLOW)💡 You will be prompted for SSH and sudo passwords$(NC)\n"
	@cd ansible && ansible-playbook playbooks/uninstall.yml -kbK
	@printf "$(GREEN)✅ Uninstallation completed$(NC)\n"

.PHONY: ansible-install-dry
ansible-install-dry: ## Dry-run Ansible deployment (check mode)
	@printf "$(BLUE)🔍 Running Ansible deployment in check mode...$(NC)\n"
	@cd ansible && ansible-playbook playbooks/site.yml --check --skip-tags=download
	@printf "$(GREEN)✅ Dry-run completed$(NC)\n"

.PHONY: ansible-uninstall-dry
ansible-uninstall-dry: ## Dry-run Ansible uninstall (check mode)
	@printf "$(BLUE)🔍 Running Ansible uninstall in check mode...$(NC)\n"
	@cd ansible && ansible-playbook playbooks/uninstall.yml --check
	@printf "$(GREEN)✅ Dry-run completed$(NC)\n"

.PHONY: ansible-uninstall-purge
ansible-uninstall-purge: ## Uninstall and remove all data (config, logs, user)
	@printf "$(BLUE)🗑️  Purging tls-cert-monitor with Ansible...$(NC)\n"
	@printf "$(RED)⚠️  WARNING: This will remove all configuration, logs, and the service user!$(NC)\n"
	@cd ansible && ansible-playbook playbooks/uninstall.yml -e "remove_config=true remove_logs=true remove_user=true"
	@printf "$(GREEN)✅ Purge completed$(NC)\n"

.PHONY: ansible-uninstall-purge-pass
ansible-uninstall-purge-pass: ## Uninstall using interactive password authentication (-kbK)
	@printf "$(BLUE)🗑️  Purging tls-cert-monitor with password authentication...$(NC)\n"
	@printf "$(RED)⚠️  WARNING: This will remove all configuration, logs, and the service user!$(NC)\n"
	@printf "$(YELLOW)💡 You will be prompted for SSH and sudo passwords$(NC)\n"
	@cd ansible && ansible-playbook playbooks/uninstall.yml -e "remove_config=true remove_logs=true remove_user=true" -kbK
	@printf "$(GREEN)✅ Purge completed$(NC)\n"

.PHONY: ansible-ping
ansible-ping: ## Test SSH connectivity to all hosts
	@printf "$(BLUE)🏓 Testing SSH connectivity to all hosts...$(NC)\n"
	@if [ ! -f ansible/inventory/hosts.yml ]; then \
		printf "$(RED)❌ No inventory file found at ansible/inventory/hosts.yml$(NC)\n"; \
		printf "$(YELLOW)💡 Edit ansible/inventory/hosts.yml with your SSH connection details$(NC)\n"; \
		exit 1; \
	fi
	@cd ansible && ansible all -m ping
	@printf "$(GREEN)✅ SSH connectivity test completed$(NC)\n"

.PHONY: ansible-win-ping
ansible-win-ping: ## Test Windows connectivity (both SSH and WinRM)
	@printf "$(BLUE)🪟 Testing Windows connectivity...$(NC)\n"
	@if [ ! -f ansible/inventory/hosts.yml ]; then \
		printf "$(RED)❌ No inventory file found at ansible/inventory/hosts.yml$(NC)\n"; \
		exit 1; \
	fi
	@cd ansible && ansible windows_servers -m win_ping 2>/dev/null || ansible windows_servers -m ping
	@printf "$(GREEN)✅ Windows connectivity test completed$(NC)\n"

.PHONY: ansible-inventory
ansible-inventory: ## Show parsed inventory information
	@printf "$(BLUE)📋 Displaying inventory information...$(NC)\n"
	@if [ ! -f ansible/inventory/hosts.yml ]; then \
		printf "$(RED)❌ No inventory file found at ansible/inventory/hosts.yml$(NC)\n"; \
		exit 1; \
	fi
	@cd ansible && ansible-inventory --list --yaml

.PHONY: ansible-vault-create
ansible-vault-create: ## Create encrypted vault file for passwords
	@printf "$(BLUE)🔐 Creating Ansible vault file...$(NC)\n"
	@cd ansible && ansible-vault create group_vars/all/vault.yml
	@printf "$(GREEN)✅ Vault file created at ansible/group_vars/all/vault.yml$(NC)\n"

.PHONY: ansible-vault-edit
ansible-vault-edit: ## Edit encrypted vault file
	@printf "$(BLUE)🔐 Editing Ansible vault file...$(NC)\n"
	@if [ ! -f ansible/group_vars/all/vault.yml ]; then \
		printf "$(RED)❌ Vault file not found. Run 'make ansible-vault-create' first$(NC)\n"; \
		exit 1; \
	fi
	@cd ansible && ansible-vault edit group_vars/all/vault.yml

# ----------------------------
# Cleanup
# ----------------------------
.PHONY: clean
clean: ## Clean development artifacts
	@printf "$(BLUE)🧹 Cleaning development artifacts...$(NC)\n"
	@rm -rf dist/ *.egg-info/ .pytest_cache/ .coverage htmlcov/ coverage/ .mypy_cache/ coverage.xml
	@find . -type d -name __pycache__ -exec rm -rf {} + 2>/dev/null || true
	@rm -f bandit-report.json .dev_server.pid
	@printf "$(GREEN)✅ Cleanup completed$(NC)\n"

.PHONY: clean-all
clean-all: clean ## Clean everything including venv, config, and certs
	@printf "$(BLUE)🧹 Deep cleaning everything...$(NC)\n"
	@rm -rf $(VENV_DIR)/ tests/fixtures/certs/ tests/fixtures/configs/ config.yaml config-dev.yaml logs cache
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