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
EXAMPLE_DIR := $(PWD)/test/fixtures

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
	@echo "🔐 Generating example certificates..."
	@mkdir -p $(EXAMPLE_DIR)/certs
	@command -v openssl >/dev/null 2>&1 || { \
		echo "❌ OpenSSL not found. Please install OpenSSL."; \
		exit 1; \
	}

	@echo "🔧 Generating Root CA..."
	@openssl genrsa -out $(EXAMPLE_DIR)/certs/ca.key 2048 2>/dev/null
	@openssl req -new -x509 -key $(EXAMPLE_DIR)/certs/ca.key -out $(EXAMPLE_DIR)/certs/ca-cert.pem -days 365 -subj "/CN=Test CA" 2>/dev/null

	@echo "🔧 Generating 1-year valid certificates..."
	@for i in 1 2 3; do \
		openssl genrsa -out $(EXAMPLE_DIR)/certs/1yr_valid_$$i.key 2048 2>/dev/null && \
		openssl req -new -key $(EXAMPLE_DIR)/certs/1yr_valid_$$i.key -out $(EXAMPLE_DIR)/certs/1yr_valid_$$i.csr -subj "/CN=valid$$i.example.com" 2>/dev/null && \
		openssl x509 -req -in $(EXAMPLE_DIR)/certs/1yr_valid_$$i.csr -CA $(EXAMPLE_DIR)/certs/ca-cert.pem -CAkey $(EXAMPLE_DIR)/certs/ca.key -out $(EXAMPLE_DIR)/certs/1yr_valid_$$i.pem -days 365 -CAcreateserial 2>/dev/null && \
		rm -f $(EXAMPLE_DIR)/certs/1yr_valid_$$i.csr || { echo "❌ Failed to generate 1yr_valid_$$i"; exit 1; }; \
	done

	@echo "🔧 Creating duplicate certificates..."
	@cp $(EXAMPLE_DIR)/certs/1yr_valid_1.pem $(EXAMPLE_DIR)/certs/1yr_valid_dup_1.pem
	@cp $(EXAMPLE_DIR)/certs/1yr_valid_1.pem $(EXAMPLE_DIR)/certs/1yr_valid_dup_2.pem
	@cp $(EXAMPLE_DIR)/certs/1yr_valid_1.key $(EXAMPLE_DIR)/certs/1yr_valid_dup_1.key
	@cp $(EXAMPLE_DIR)/certs/1yr_valid_1.key $(EXAMPLE_DIR)/certs/1yr_valid_dup_2.key

	@echo "🔧 Generating short expiration certificates..."
	@openssl genrsa -out $(EXAMPLE_DIR)/certs/valid_short_1.key 2048 2>/dev/null && \
	openssl req -new -key $(EXAMPLE_DIR)/certs/valid_short_1.key -out $(EXAMPLE_DIR)/certs/valid_short_1.csr -subj "/CN=short1.example.com" 2>/dev/null && \
	openssl x509 -req -in $(EXAMPLE_DIR)/certs/valid_short_1.csr -CA $(EXAMPLE_DIR)/certs/ca-cert.pem -CAkey $(EXAMPLE_DIR)/certs/ca.key -out $(EXAMPLE_DIR)/certs/valid_short_1.pem -days 5 -CAcreateserial 2>/dev/null && \
	rm -f $(EXAMPLE_DIR)/certs/valid_short_1.csr || { echo "❌ Failed to generate valid_short_1"; exit 1; }

	@openssl genrsa -out $(EXAMPLE_DIR)/certs/valid_short_2.key 2048 2>/dev/null && \
	openssl req -new -key $(EXAMPLE_DIR)/certs/valid_short_2.key -out $(EXAMPLE_DIR)/certs/valid_short_2.csr -subj "/CN=short2.example.com" 2>/dev/null && \
	openssl x509 -req -in $(EXAMPLE_DIR)/certs/valid_short_2.csr -CA $(EXAMPLE_DIR)/certs/ca-cert.pem -CAkey $(EXAMPLE_DIR)/certs/ca.key -out $(EXAMPLE_DIR)/certs/valid_short_2.pem -days 180 -CAcreateserial 2>/dev/null && \
	rm -f $(EXAMPLE_DIR)/certs/valid_short_2.csr || { echo "❌ Failed to generate valid_short_2"; exit 1; }

	@echo "🔧 Generating weak key certificates..."
	@for i in 1 2; do \
		openssl genrsa -out $(EXAMPLE_DIR)/certs/1yr_weak_key_$$i.key 512 2>/dev/null && \
		openssl req -new -key $(EXAMPLE_DIR)/certs/1yr_weak_key_$$i.key -out $(EXAMPLE_DIR)/certs/1yr_weak_key_$$i.csr -subj "/CN=weakkey$$i.example.com" 2>/dev/null && \
		openssl x509 -req -in $(EXAMPLE_DIR)/certs/1yr_weak_key_$$i.csr -CA $(EXAMPLE_DIR)/certs/ca-cert.pem -CAkey $(EXAMPLE_DIR)/certs/ca.key -out $(EXAMPLE_DIR)/certs/1yr_weak_key_$$i.pem -days 365 -CAcreateserial 2>/dev/null && \
		rm -f $(EXAMPLE_DIR)/certs/1yr_weak_key_$$i.csr || { echo "❌ Failed to generate 1yr_weak_key_$$i"; exit 1; }; \
	done

	@echo "🔧 Generating weak algorithm certificates..."
	@for i in 1 2; do \
		openssl genrsa -out $(EXAMPLE_DIR)/certs/1yr_weak_algo_$$i.key 2048 2>/dev/null && \
		openssl req -new -md5 -key $(EXAMPLE_DIR)/certs/1yr_weak_algo_$$i.key -out $(EXAMPLE_DIR)/certs/1yr_weak_algo_$$i.csr -subj "/CN=weakalgo$$i.example.com" 2>/dev/null && \
		openssl x509 -req -md5 -in $(EXAMPLE_DIR)/certs/1yr_weak_algo_$$i.csr -CA $(EXAMPLE_DIR)/certs/ca-cert.pem -CAkey $(EXAMPLE_DIR)/certs/ca.key -out $(EXAMPLE_DIR)/certs/1yr_weak_algo_$$i.pem -days 365 -CAcreateserial 2>/dev/null && \
		rm -f $(EXAMPLE_DIR)/certs/1yr_weak_algo_$$i.csr || { echo "❌ Failed to generate 1yr_weak_algo_$$i"; exit 1; }; \
	done

	@echo "🔧 Generating fake DigiCert CA and certificate..."
	@openssl genrsa -out $(EXAMPLE_DIR)/certs/fake_digicert_ca.key 2048 2>/dev/null && \
	openssl req -new -x509 -key $(EXAMPLE_DIR)/certs/fake_digicert_ca.key -out $(EXAMPLE_DIR)/certs/fake_digicert_ca.pem -days 365 -subj "/O=DigiCert Inc/CN=DigiCert Root CA" 2>/dev/null && \
	openssl genrsa -out $(EXAMPLE_DIR)/certs/digicert.key 2048 2>/dev/null && \
	openssl req -new -key $(EXAMPLE_DIR)/certs/digicert.key -out $(EXAMPLE_DIR)/certs/digicert.csr -subj "/CN=digicert.example.com" 2>/dev/null && \
	openssl x509 -req -in $(EXAMPLE_DIR)/certs/digicert.csr -CA $(EXAMPLE_DIR)/certs/fake_digicert_ca.pem -CAkey $(EXAMPLE_DIR)/certs/fake_digicert_ca.key -out $(EXAMPLE_DIR)/certs/digicert.pem -days 365 -CAcreateserial 2>/dev/null && \
	rm -f $(EXAMPLE_DIR)/certs/digicert.csr || { echo "❌ Failed to generate fake DigiCert"; exit 1; }

	@echo "🔧 Generating fake Amazon CA and certificate..."
	@openssl genrsa -out $(EXAMPLE_DIR)/certs/fake_amazon_ca.key 2048 2>/dev/null && \
	openssl req -new -x509 -key $(EXAMPLE_DIR)/certs/fake_amazon_ca.key -out $(EXAMPLE_DIR)/certs/fake_amazon_ca.pem -days 365 -subj "/O=Amazon Trust Services/CN=Amazon Root CA" 2>/dev/null && \
	openssl genrsa -out $(EXAMPLE_DIR)/certs/amazon.key 2048 2>/dev/null && \
	openssl req -new -key $(EXAMPLE_DIR)/certs/amazon.key -out $(EXAMPLE_DIR)/certs/amazon.csr -subj "/CN=amazon.example.com" 2>/dev/null && \
	openssl x509 -req -in $(EXAMPLE_DIR)/certs/amazon.csr -CA $(EXAMPLE_DIR)/certs/fake_amazon_ca.pem -CAkey $(EXAMPLE_DIR)/certs/fake_amazon_ca.key -out $(EXAMPLE_DIR)/certs/amazon.pem -days 365 -CAcreateserial 2>/dev/null && \
	rm -f $(EXAMPLE_DIR)/certs/amazon.csr || { echo "❌ Failed to generate fake Amazon"; exit 1; }

	@echo "🔧 Generating certificates with SANs..."
	@openssl genrsa -out $(EXAMPLE_DIR)/certs/san_1.key 2048 2>/dev/null && \
	openssl req -new -key $(EXAMPLE_DIR)/certs/san_1.key -out $(EXAMPLE_DIR)/certs/san_1.csr -subj "/CN=san1.example.com" -addext "subjectAltName=DNS:san1.example.com,DNS:www.san1.example.com,DNS:alt1.example.com" 2>/dev/null && \
	openssl x509 -req -in $(EXAMPLE_DIR)/certs/san_1.csr -CA $(EXAMPLE_DIR)/certs/ca-cert.pem -CAkey $(EXAMPLE_DIR)/certs/ca.key -out $(EXAMPLE_DIR)/certs/san_1.pem -days 365 -extfile <(echo "subjectAltName=DNS:san1.example.com,DNS:www.san1.example.com,DNS:alt1.example.com") -CAcreateserial 2>/dev/null && \
	rm -f $(EXAMPLE_DIR)/certs/san_1.csr || { echo "❌ Failed to generate san_1"; exit 1; }

	@openssl genrsa -out $(EXAMPLE_DIR)/certs/san_2.key 2048 2>/dev/null && \
	openssl req -new -key $(EXAMPLE_DIR)/certs/san_2.key -out $(EXAMPLE_DIR)/certs/san_2.csr -subj "/CN=san2.example.com" -addext "subjectAltName=DNS:san2.example.com,DNS:alt2.example.com,DNS:www.alt2.example.com,DNS:dev.alt2.example.com,DNS:test.alt2.example.com,DNS:x.alt2.example.com,DNS:y.alt2.example.com,DNS:z.alt2.example.com" 2>/dev/null && \
	openssl x509 -req -in $(EXAMPLE_DIR)/certs/san_2.csr -CA $(EXAMPLE_DIR)/certs/ca-cert.pem -CAkey $(EXAMPLE_DIR)/certs/ca.key -out $(EXAMPLE_DIR)/certs/san_2.pem -days 365 -extfile <(echo "subjectAltName=DNS:san2.example.com,DNS:alt2.example.com,DNS:www.alt2.example.com,DNS:dev.alt2.example.com,DNS:test.alt2.example.com,DNS:x.alt2.example.com,DNS:y.alt2.example.com,DNS:z.alt2.example.com") -CAcreateserial 2>/dev/null && \
	rm -f $(EXAMPLE_DIR)/certs/san_2.csr || { echo "❌ Failed to generate san_2"; exit 1; }

	@echo "🔧 Generating P12 certificates..."
	@for i in 1 2; do \
		openssl genrsa -out $(EXAMPLE_DIR)/certs/p12_cert_$$i.key 2048 2>/dev/null && \
		openssl req -new -key $(EXAMPLE_DIR)/certs/p12_cert_$$i.key -out $(EXAMPLE_DIR)/certs/p12_cert_$$i.csr -subj "/CN=p12cert$$i.example.com" 2>/dev/null && \
		openssl x509 -req -in $(EXAMPLE_DIR)/certs/p12_cert_$$i.csr -CA $(EXAMPLE_DIR)/certs/ca-cert.pem -CAkey $(EXAMPLE_DIR)/certs/ca.key -out $(EXAMPLE_DIR)/certs/p12_cert_$$i.pem -days 365 -CAcreateserial 2>/dev/null && \
		openssl pkcs12 -export -out $(EXAMPLE_DIR)/certs/p12_cert_$$i.p12 -inkey $(EXAMPLE_DIR)/certs/p12_cert_$$i.key -in $(EXAMPLE_DIR)/certs/p12_cert_$$i.pem -passout pass:changeit 2>/dev/null && \
		rm -f $(EXAMPLE_DIR)/certs/p12_cert_$$i.csr || { echo "❌ Failed to generate p12_cert_$$i"; exit 1; }; \
	done

	@echo "✅ Example certificates generated in $(EXAMPLE_DIR)/certs/"

.PHONY: config-dev
config-dev: certs ## Create development configuration file
	@echo "🛠️ Creating development configuration..."
	@mkdir -p $(EXAMPLE_DIR)/configs
	@echo "port: 3200" > $(EXAMPLE_DIR)/configs/config.dev.yaml
	@echo 'bind_address: "0.0.0.0"' >> $(EXAMPLE_DIR)/configs/config.dev.yaml
	@echo "certificate_directories:" >> $(EXAMPLE_DIR)/configs/config.dev.yaml
	@echo "  - \"$(EXAMPLE_DIR)/certs\"" >> $(EXAMPLE_DIR)/configs/config.dev.yaml
	@echo "exclude_directories:" >> $(EXAMPLE_DIR)/configs/config.dev.yaml
	@echo "  - \"$(EXAMPLE_DIR)/certs/booger\"" >> $(EXAMPLE_DIR)/configs/config.dev.yaml
	@echo 'scan_interval: "1m"' >> $(EXAMPLE_DIR)/configs/config.dev.yaml
	@echo "workers: 4" >> $(EXAMPLE_DIR)/configs/config.dev.yaml
	@echo 'log_level: "info"    # debug, info, warn, error' >> $(EXAMPLE_DIR)/configs/config.dev.yaml
	@echo "dry_run: false" >> $(EXAMPLE_DIR)/configs/config.dev.yaml
	@echo "hot_reload: true" >> $(EXAMPLE_DIR)/configs/config.dev.yaml
	@echo 'cache_dir: "./cache"' >> $(EXAMPLE_DIR)/configs/config.dev.yaml
	@echo 'cache_ttl: "1h"' >> $(EXAMPLE_DIR)/configs/config.dev.yaml
	@echo "cache_max_size: 104857600  # 100MB" >> $(EXAMPLE_DIR)/configs/config.dev.yaml
	@echo "✅ Development configuration created: $(EXAMPLE_DIR)/configs/config.dev.yaml"
	@echo "📝 Use with: ./build/$(BINARY_NAME) -config=$(EXAMPLE_DIR)/configs/config.dev.yaml"

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
	@rm -rf $(BUILD_DIR) $(DIST_DIR) $(COVERAGE_DIR) $(CACHE_DIR) $(EXAMPLE_DIR)/*
	@echo "✅ Full cleanup complete!"