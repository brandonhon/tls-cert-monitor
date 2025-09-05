# ============================
# TLS Certificate Monitor Makefile
# ============================

# ----------------------------
# Shell & Environment Setup
# ----------------------------
SHELL := /bin/bash

# ----------------------------
# Build Variables
# ----------------------------
BINARY_NAME := tls-cert-monitor
# VERSION will eventually become a branch name
VERSION     := $(shell git describe --tags --always --dirty 2>/dev/null || echo "dev")
BUILD_TIME  := $(shell date -u '+%Y-%m-%d_%H:%M:%S')
GIT_COMMIT  := $(shell git rev-parse --short HEAD 2>/dev/null || echo "unknown")
GO_VERSION  := $(shell go version | cut -d' ' -f3)

# ----------------------------
# Docker Variables
# ----------------------------
DOCKER           ?= docker
DOCKERFILE       ?= ./Dockerfile

# Image naming: override these in CI or locally:
#   make docker-build REGISTRY=ghcr.io REPO=your-org IMAGE_NAME=tls-cert-monitor
REGISTRY         ?= ghcr.io         # or docker.io, ECR registry, etc.
REPO             ?= brandonhon        # org/user or ECR repo namespace
IMAGE_NAME       ?= $(BINARY_NAME)  # default to Go binary name

IMAGE            := $(strip $(REGISTRY))/$(strip $(REPO))/$(strip $(IMAGE_NAME)):$(strip $(VERSION))
LATEST_IMAGE     := $(strip $(REGISTRY))/$(strip $(REPO))/$(strip $(IMAGE_NAME)):latest

# Multi-arch buildx platforms
PLATFORMS        ?= linux/amd64,linux/arm64

# Container runtime defaults
CONTAINER_NAME   ?= $(IMAGE_NAME)
PORT             ?= 3200
ENV_FILE         ?= .env
BUILD_OPTS		 ?= --pull
RUN_OPTS     	 ?= --restart=unless-stopped

# ----------------------------
# Go Tools & Commands
# ----------------------------
GOCMD      := go
GOBUILD    := $(GOCMD) build
GOCLEAN    := $(GOCMD) clean
GOTEST     := $(GOCMD) test
GOMOD      := $(GOCMD) mod
GOFMT      := gofmt
GOLINT     := golangci-lint
GOSEC      := gosec

# ----------------------------
# Build Flags & Directories
# ----------------------------
LDFLAGS := -ldflags "-X main.version=$(VERSION) -X main.buildTime=$(BUILD_TIME) -X main.gitCommit=$(GIT_COMMIT)"
BUILD_DIR := build
DIST_DIR  := dist
COVERAGE_DIR := coverage
CACHE_DIR := cache
VENDOR := vendor
EXAMPLE_DIR := $(PWD)/test/fixtures

# ----------------------------
# PFX Generation Defaults
# ----------------------------
# Windows PFX generation defaults
CSP_NAME := Microsoft Enhanced RSA and AES Cryptographic Provider
MACALG := sha1
MACSALT := 20
KEYPBE := PBE-SHA1-3DES
CERTPBE := PBE-SHA1-3DES
ITERATIONS := 2000


# Default target
.PHONY: all
all: clean fmt lint test build

# ----------------------------
# Help Target
# ----------------------------
.PHONY: help
help: ## Show available commands
	@echo ""
	@printf "🔹 \033[1;36mTLS Certificate Monitor - Available Commands\033[0m 🔹\n\n"
	@grep -E '^[a-zA-Z0-9_-]+:.*?## .*$$' $(MAKEFILE_LIST) \
		| sort \
		| awk 'BEGIN {FS = ":.*?## "}; {printf "  \033[1;32m%-20s\033[0m %s\n", $$1, $$2}'
	@echo ""
	@printf "💡 Run \033[1;33mmake <target>\033[0m to execute a command.\n\n"

# ----------------------------
# Build Targets
# ----------------------------
.PHONY: build
build: deps ## Build the binary for current platform
	@echo "🔨 Building $(BINARY_NAME)..."
	@mkdir -p $(BUILD_DIR)
	$(GOBUILD) $(LDFLAGS) -o $(BUILD_DIR)/$(BINARY_NAME) .
	@echo "✅ Binary built: $(BUILD_DIR)/$(BINARY_NAME)"

.PHONY: build-race
build-race: deps ## Build binary with race detection enabled
	@echo "🔨 Building $(BINARY_NAME) with race detection..."
	@mkdir -p $(BUILD_DIR)
	$(GOBUILD) -race $(LDFLAGS) -o $(BUILD_DIR)/$(BINARY_NAME)-race .
	@echo "✅ Binary built: $(BUILD_DIR)/$(BINARY_NAME)-race"

.PHONY: build-all
build-all: deps ## Build binaries for all platforms
	@echo "🌎 Building for all supported platforms..."
	@$(GOBUILD) $(LDFLAGS) -o $(DIST_DIR)/$(BINARY_NAME) .

# ----------------------------
# Docker Targets
# ----------------------------
.PHONY: docker-info
docker-info: ## Show resolved Docker image information
	@echo "🐳 Docker info"
	@echo "  REGISTRY:       $(REGISTRY)"
	@echo "  REPO:           $(REPO)"
	@echo "  IMAGE_NAME:     $(IMAGE_NAME)"
	@echo "  IMAGE_TAG:      $(VERSION)"
	@echo "  IMAGE:          $(IMAGE)"
	@echo "  LATEST_IMAGE:   $(LATEST_IMAGE)"
	@echo "  PLATFORMS:      $(PLATFORMS)"

.PHONY: docker-login
docker-login: ## Login to REGISTRY (expects DOCKER_USERNAME/DOCKER_PASSWORD or GHCR_TOKEN)
	@if [ -n "$$GHCR_TOKEN" ]; then \
		echo "🔑 Logging in to $(REGISTRY) via GHCR_TOKEN..."; \
		echo "$$GHCR_TOKEN" | $(DOCKER) login $(REGISTRY) -u $$DOCKER_USERNAME --password-stdin; \
	elif [ -n "$$DOCKER_USERNAME" ] && [ -n "$$DOCKER_PASSWORD" ]; then \
		echo "🔑 Logging in to $(REGISTRY) as $$DOCKER_USERNAME..."; \
		echo "$$DOCKER_PASSWORD" | $(DOCKER) login $(REGISTRY) -u "$$DOCKER_USERNAME" --password-stdin; \
	else \
		echo "❌ Missing credentials. Provide GHCR_TOKEN or DOCKER_USERNAME/DOCKER_PASSWORD"; \
		exit 1; \
	fi

.PHONY: docker-build
docker-build: ## Build image for local arch
	@echo "🐳 Building image: $(IMAGE)"
	$(DOCKER) build $(BUILD_OPTS) \
		--file $(DOCKERFILE) \
		--tag $(IMAGE) \
		--label org.opencontainers.image.title="$(IMAGE_NAME)" \
		--label org.opencontainers.image.version="$(VERSION)" \
		--label org.opencontainers.image.revision="$(GIT_COMMIT)" \
		--label org.opencontainers.image.created="$(BUILD_TIME)" \
		--build-arg VERSION=$(VERSION) \
		--build-arg GIT_COMMIT=$(GIT_COMMIT) \
		--build-arg BUILD_TIME=$(BUILD_TIME) \
		.
	@echo "✅ Built $(IMAGE)"

.PHONY: docker-build-nocache
docker-build-nocache: ## Build image without cache
	$(DOCKER) build --no-cache $(BUILD_OPTS) -f $(DOCKERFILE) -t $(IMAGE) .

.PHONY: docker-tag
docker-tag: ## Tag image also as :latest
	@echo "🏷️  Tagging $(IMAGE) as $(LATEST_IMAGE)"
	$(DOCKER) tag $(IMAGE) $(LATEST_IMAGE)

.PHONY: docker-push
docker-push: ## Push image (and :latest if present)
	@echo "📤 Pushing $(IMAGE)"
	$(DOCKER) push $(IMAGE)
	-@$(DOCKER) image inspect $(LATEST_IMAGE) >/dev/null 2>&1 && { \
		echo "📤 Pushing $(LATEST_IMAGE)"; \
		$(DOCKER) push $(LATEST_IMAGE); \
	} || true

.PHONY: docker-buildx
docker-buildx: ## Multi-arch build (buildx) without pushing
	@echo "🌐 Building multi-arch image (no push): $(IMAGE)"
	$(DOCKER) buildx create --name tls-monitor-builder --use >/dev/null 2>&1 || true
	$(DOCKER) buildx build \
		--platform $(PLATFORMS) \
		--file $(DOCKERFILE) \
		--tag $(IMAGE) \
		--label org.opencontainers.image.version="$(VERSION)" \
		--label org.opencontainers.image.revision="$(GIT_COMMIT)" \
		--label org.opencontainers.image.created="$(BUILD_TIME)" \
		--build-arg VERSION=$(VERSION) \
		--build-arg GIT_COMMIT=$(GIT_COMMIT) \
		--build-arg BUILD_TIME=$(BUILD_TIME) \
		--output type=docker \
		.

.PHONY: docker-buildx-push
docker-buildx-push: ## Multi-arch buildx and push (CI-friendly)
	@echo "🌐 Building + pushing multi-arch image: $(IMAGE)"
	$(DOCKER) buildx create --name tls-monitor-builder --use >/dev/null 2>&1 || true
	$(DOCKER) buildx build \
		--platform $(PLATFORMS) \
		--file $(DOCKERFILE) \
		--tag $(IMAGE) \
		--push \
		--label org.opencontainers.image.version="$(VERSION)" \
		--label org.opencontainers.image.revision="$(GIT_COMMIT)" \
		--label org.opencontainers.image.created="$(BUILD_TIME)" \
		--build-arg VERSION=$(VERSION) \
		--build-arg GIT_COMMIT=$(GIT_COMMIT) \
		--build-arg BUILD_TIME=$(BUILD_TIME) \
		.

.PHONY: docker-run
docker-run: ## Run container locally (maps PORT, optional .env)
	@echo "🚀 Running $(CONTAINER_NAME) on port $(PORT)"
	-@$(DOCKER) rm -f $(CONTAINER_NAME) >/dev/null 2>&1 || true
	$(DOCKER) run -d --name $(CONTAINER_NAME) \
		-p $(PORT):$(PORT) \
		-v $(EXAMPLE_DIR)/certs:/app/certs:ro \
		$$( [ -f $(ENV_FILE) ] && echo "--env-file $(ENV_FILE)" ) \
		$(IMAGE)
# 	@$(DOCKER) ps --filter "name=$(CONTAINER_NAME)"
	@echo ""
	@echo "tls-cert-monitor available at: http://localhost:3200/"

.PHONY: docker-logs
docker-logs: ## Tail container logs
	$(DOCKER) logs -f $(CONTAINER_NAME)

.PHONY: docker-stop
docker-stop: ## Stop container
	-$(DOCKER) stop $(CONTAINER_NAME) || true

.PHONY: docker-rm
docker-rm: docker-stop ## Remove container
	-$(DOCKER) rm $(CONTAINER_NAME) || true

.PHONY: docker-rmi
docker-rmi: ## Remove built image(s)
	-$(DOCKER) rmi $(IMAGE) || true
	-$(DOCKER) rmi $(LATEST_IMAGE) || true

.PHONY: docker-clean
docker-clean: docker-rm docker-rmi ## Remove container and images
	@echo "🧹 Docker artifacts removed"

# ----------------------------
# Docker Compose
# ----------------------------
.PHONY: compose-up
compose-up: ## docker compose up -d (uses docker-compose.dev.yaml w/profile monitoring)
	@if [ -f docker-compose.dev.yml ] || [ -f compose.dev.yml ]; then \
		echo "📦 docker compose -f docker-compose.dev.yml --profile monitoring up -d"; \
		$(DOCKER) compose -f docker-compose.dev.yml --profile monitoring up -d; \
		echo "tls-cert-monitor available at: http://localhost:3200/"; \
		echo "Prometheus available at: http://localhost:9090/"; \
		echo "Grafana available at: http://localhost:3000/"; \
	else \
		echo "❌ No docker-compose.dev.yml or compose.dev.yml found"; \
		exit 1; \
	fi

.PHONY: compose-down
compose-down: ## docker compose down
	@if [ -f docker-compose.dev.yml ] || [ -f compose.dev.yml ]; then \
		echo "📦 docker compose -f docker-compose.dev.yml --profile monitoring down"; \
		$(DOCKER) compose -f docker-compose.dev.yml --profile monitoring down; \
	else \
		echo "❌ No docker-compose.dev.yml or compose.dev.yml found"; \
		exit 1; \
	fi

.PHONY: compose-clean
compose-clean: ## docker compose down --volumes --remove-orphans --rmi all
	@if [ -f docker-compose.dev.yml ] || [ -f compose.dev.yml ]; then \
		echo "🧹 Cleaning up Docker environment..."; \
		echo "📦 docker compose -f docker-compose.dev.yml --profile monitoring down --volumes --remove-orphans --rmi all"; \
		$(DOCKER) compose -f docker-compose.dev.yml --profile monitoring down --volumes --remove-orphans --rmi all; \
		rm -rf ./docker/cache ./docker/logs; \
		echo "✅ Docker environment cleaned up successfully!"; \
	else \
		echo "❌ No docker-compose.dev.yml or compose.dev.yml found"; \
		exit 1; \
	fi


# ----------------------------
# Development Helpers
# ----------------------------
.PHONY: certs
certs: ## Generate example certificates for testing
	@EXAMPLE_DIR="$(EXAMPLE_DIR)" bash ./scripts/generate-test-certs.sh

.PHONY: config-dev
config-dev: ## Create development configuration file
	@EXAMPLE_DIR="$(EXAMPLE_DIR)" bash ./scripts/generate-config-dev.sh

# ----------------------------
# Linting Targets
# ----------------------------
.PHONY: fmt
fmt: ## Format code
	@echo "📄 Formatting all code..."
	go fmt ./...

.PHONY: lint
lint: ## Run linters (warnings won't fail)
	@echo "🔍 Running linters..."
	@command -v $(GOLINT) >/dev/null 2>&1 || { \
		echo "❌ $(GOLINT) not found. Install it using:"; \
		echo "   go install github.com/golangci/golangci-lint/cmd/golangci-lint@latest"; \
		exit 1; \
	}
	@$(GOLINT) run --config=./.golangci.yml ./...

.PHONY: lint-ci
lint-ci: ## Run strict linting for CI (warnings fail build)
	@echo "🔍 Running strict linting (CI mode)..."
	@$(GOLINT) run --config ./.golangci.yml ./...

.PHONY: lint-fix
lint-fix: ## Automatically fix common linting issues
	@echo "🛠️  Auto-fixing lint issues..."
	$(GOLINT) run --fix --config ./.golangci.yml ./...
	@echo "✅ Auto-fix completed!"

# ----------------------------
# Testing Targets
# ----------------------------
.PHONY: test
test: ## Run integration tests 
	@echo "🧪 Running integration tests..."
	$(GOTEST) -tags=integration ./test/... 
	@echo "✅ Tests completed."

.PHONY: test-verbose
test-verbose: ## Run tests with verbose
	@echo "🧪 Running tests with verbose..."
	$(GOTEST) -v -tags=integration ./test/... 
	@echo "✅ Tests completed."

.PHONY: test-coverage
test-coverage: ## Run tests with coverage
	@echo "🧪 Running tests..."
	$(GOTEST) -tags=integration ./test/... -coverprofile=$(COVERAGE_DIR)/coverage.out
	@echo "✅ Tests completed. Coverage report at $(COVERAGE_DIR)/coverage.out"

.PHONY: test-race
test-race: ## Run tests with race detector
	$(GOTEST) -tags=integration -race ./test/...

# ----------------------------
# Security Targets
# ----------------------------
.PHONY: sec
sec: ## Run security checks using gosec
	@if ! command -v $(GOSEC) >/dev/null 2>&1; then \
		echo "❌ gosec not found. Install it using:"; \
		echo "   go install github.com/securego/gosec/v2/cmd/gosec@latest"; \
		exit 1; \
	fi
	$(GOSEC) ./...

# ----------------------------
# Dependency Management
# ----------------------------
.PHONY: deps
deps: ## Download Go module dependencies
	@echo "📦 Downloading dependencies..."
	$(GOMOD) tidy
	$(GOMOD) vendor
	@echo "✅ Dependencies ready!"

# ----------------------------
# Cleanup Targets
# ----------------------------
.PHONY: clean
clean: ## Clean build artifacts
	@echo "🧹 Cleaning up..."
	@rm -rf $(BUILD_DIR) $(DIST_DIR) $(COVERAGE_DIR) $(CACHE_DIR) 
	@echo "✅ Cleanup complete!"

.PHONY: clean-all
clean-all: ## Clean build artifacts + example files
	@echo "🧹 Deep cleaning project (build, dist, cache, coverage, and example files)..."
	@rm -rf $(BUILD_DIR) $(DIST_DIR) $(COVERAGE_DIR) $(CACHE_DIR) $(EXAMPLE_DIR)/* $(VENDOR)
	@echo "✅ Full cleanup complete!"