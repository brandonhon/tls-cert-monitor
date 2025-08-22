# TLS Certificate Monitor Makefile

# Shell setup
SHELL := /bin/bash

# Build variables
BINARY_NAME=tls-cert-monitor
VERSION ?= $(shell git describe --tags --always --dirty 2>/dev/null || echo "dev")
BUILD_TIME ?= $(shell date -u '+%Y-%m-%d_%H:%M:%S')
GIT_COMMIT ?= $(shell git rev-parse --short HEAD 2>/dev/null || echo "unknown")
GO_VERSION := $(shell go version | cut -d' ' -f3)

# Go variables
GOCMD=go
GOBUILD=$(GOCMD) build
GOCLEAN=$(GOCMD) clean
GOTEST=$(GOCMD) test
GOGET=$(GOCMD) get
GOMOD=$(GOCMD) mod
GOTOOL=$(GOCMD) tool
GOFMT=gofmt
GOLINT=golangci-lint
GOSEC=gosec

# Build flags
LDFLAGS=-ldflags "-X main.version=$(VERSION) -X main.buildTime=$(BUILD_TIME) -X main.gitCommit=$(GIT_COMMIT)"

# Directories
BUILD_DIR=build
DIST_DIR=dist
COVERAGE_DIR=coverage
CACHE_DIR=cache
EXAMPLE_DIR=$(PWD)/test/fixtures

# Default target
.PHONY: all
all: clean fmt lint test build

# Help target
.PHONY: help
help: ## Show available commands
	@echo ""
	@printf "🔹 \033[1;36mTLS Certificate Monitor - Available Commands\033[0m 🔹\n\n"
	@awk 'BEGIN {FS = ":.*## "} \
		/^[a-zA-Z0-9_-]+:.*## / { \
			printf "  \033[1;32m%-22s\033[0m %s\n", $$1, $$2 \
		}' $(MAKEFILE_LIST)
	@echo ""
	@printf "💡 Run \033[1;33mmake <target>\033[0m to execute a command.\n\n"

# Build targets
.PHONY: build
build: deps ## Build the binary for current platform
	@echo "Building $(BINARY_NAME)..."
	@mkdir -p $(BUILD_DIR)
	$(GOBUILD) $(LDFLAGS) -o $(BUILD_DIR)/$(BINARY_NAME) .
	@echo "✅ Binary built: $(BUILD_DIR)/$(BINARY_NAME)"

.PHONY: build-race
build-race: deps ## Build the binary for current platform with race detection
	@echo "Building $(BINARY_NAME) with race detection..."
	@mkdir -p $(BUILD_DIR)
	$(GOBUILD) -race $(LDFLAGS) -o $(BUILD_DIR)/$(BINARY_NAME)-race .
	@echo "✅ Binary built: $(BUILD_DIR)/$(BINARY_NAME)-race"

.PHONY: build-all
build-all: deps ## Build binaries for all platforms
	@echo "🔨 Building for all platforms..."
	@$(MAKE) build-linux
	@$(MAKE) build-darwin
	@$(MAKE) build-windows
	@echo "✅ All platform binaries built"

.PHONY: build-linux
build-linux: deps  ## Build Linux binary
	@echo "🐧 Building for Linux..."
	GOOS=linux GOARCH=amd64 go build $(BUILD_FLAGS) -o $(BUILD_DIR)/linux/$(BINARY_NAME) .
	GOOS=linux GOARCH=arm64 go build $(BUILD_FLAGS) -o $(BUILD_DIR)/linux/$(BINARY_NAME)-arm64 .

.PHONY: build-darwin
build-darwin: deps  ## Build macOS binary
	@echo "🍎 Building for macOS..."
	GOOS=darwin GOARCH=amd64 go build $(BUILD_FLAGS) -o $(BUILD_DIR)/darwin/$(BINARY_NAME) .
	GOOS=darwin GOARCH=arm64 go build $(BUILD_FLAGS) -o $(BUILD_DIR)/darwin/$(BINARY_NAME)-arm64 .

.PHONY: build-windows
build-windows: deps  ## Build Windows binary
	@echo "🪟 Building for Windows..."
	GOOS=windows GOARCH=amd64 go build $(BUILD_FLAGS) -o $(BUILD_DIR)/windows/$(BINARY_NAME).exe .

# Test targets
.PHONY: test
test: deps ## Run all tests
	@echo "🧪 Running tests..."
	@mkdir -p $(COVERAGE_DIR)
	$(GOTEST) -v -race -coverprofile=$(COVERAGE_DIR)/coverage.out ./...
	$(GOCMD) tool cover -html=$(COVERAGE_DIR)/coverage.out -o $(COVERAGE_DIR)/coverage.html
	@echo "✅ Tests completed. Coverage report: coverage.html"

.PHONY: test-short
test-short: ## Run short tests only
	@echo "🧪 Running short tests..."
	$(GOTEST) -short -v ./...

.PHONY: benchmark
benchmark: ## Run benchmarks
	@echo "📊 Running benchmarks..."
	$(GOTEST) -bench=. -benchmem ./...

# Code quality targets
.PHONY: fmt
fmt: ## Format Go code
	@echo "🎨 Formatting code..."
	$(GOFMT) -s -w .
	$(GOCMD) mod tidy
	@echo "✅ Code formatted"

.PHONY: lint
lint: ## Run linters
	@echo "🔍 Running linters..."
	@which $(GOLINT) > /dev/null 2>&1 || (echo "golangci-lint not found. Install with: go install github.com/golangci/golangci-lint/cmd/golangci-lint@latest"; exit 1)
	$(GOLINT) run ./...
	@echo "✅ Linting completed"

.PHONY: vet
vet: deps ## Run go vet
	@echo "🔍 Running go vet..."
	$(GOCMD) vet ./...
	@echo "✅ Vet completed"

.PHONY: security
security: ## Run security checks
	@echo "🔒 Running security scans..."
	@which $(GOSEC) >/dev/null 2>&1 || (echo "golangci-lint not found. Install with: go install github.com/securecodewarrior/gosec/v2/cmd/gosec@latest"; exit 1)
	gosec ./...
	@echo "✅ Security scan completed"

# Dependency targets
.PHONY: deps
deps: ## Install dependencies
	@echo "📦 Downloading dependencies..."
	$(GOMOD) download
	@echo "✅ Dependencies downloaded"

.PHONY: tidy
tidy: ## Remove unused dependencies
	@echo "🔧 Tidying dependencies..."
	$(GOMOD) tidy
	$(GOMOD) verify
	@echo "✅ Tidying completed"

.PHONY: vendor
vendor: deps ## Vendor dependencies for offline use
	@echo "📦 Vendoring dependencies..."
	$(GOMOD) vendor
	@echo "✅ Vendoring completed"

# Clean targets
.PHONY: clean
clean: ## Clean build artifacts
	@echo "🧹 Cleaning build artifacts..."
# 	$(GOCLEAN)
	@rm -rf $(BUILD_DIR)
	@rm -rf $(DIST_DIR)
	@rm -rf $(COVERAGE_DIR)
	@rm -rf vendor/
	@echo "✅ Build artifacts cleaned"

.PHONY: clean-all
clean-all: clean clean-cache ## Clean everything including configs, examples and cache
	@echo "🧹 Cleaning all generated files..."
	@rm -rf $(CACHE_DIR)
	@rm -rf $(EXAMPLE_DIR)/*
	@echo "✅ All generated files cleaned"

.PHONY: clean-cache
clean-cache: ## Clean go build cache
	@echo "🗄️ Cleaning go cache..."
	@$(GOCMD) clean -cache -testcache -modcache
	@echo "✅ Cache cleaned"

# Run targets
.PHONY: run
run: build ## Build and run with default configuration
	@echo "🚀 Starting $(BINARY_NAME)..."
	@echo "See example.config.yaml for hard coded defaults"
	./$(BUILD_DIR)/$(BINARY_NAME)

.PHONY: run-dev
run-dev: build config-dev ## Run in development mode with example certificates
	@echo "🚀 Starting $(BINARY_NAME) in development mode with development configuration..."
	./$(BUILD_DIR)/$(BINARY_NAME) -config=$(EXAMPLE_DIR)/configs/config.dev.yaml

.PHONY: run-dry
run-dry: build config-dev ## Run in dry-run mode
	@echo "🚀 Running $(BINARY_NAME) in dry-run mode with development configuration..."
	./$(BUILD_DIR)/$(BINARY_NAME) -config=$(EXAMPLE_DIR)/configs/config.dev.yaml -dry-run

# Install targets
.PHONY: install
install: build ## Install binary in $GOPATH/bin
	@echo "📦 Installing $(BINARY_NAME)..."
	$(GOCMD) install $(LDFLAGS) .
	@echo "✅ $(BINARY_NAME) installed"

# Docker targets
.PHONY: docker
docker: ## Build Docker image
	@echo "🐳 Building Docker image..."
	docker build -f $(PWD)/docker/Dockerfile -t $(BINARY_NAME):$(VERSION) .
# 	docker build -f $(PWD)/docker/Dockerfile -t $(BINARY_NAME):latest .
	docker tag $(BINARY_NAME):$(VERSION) $(BINARY_NAME):latest
	@echo "✅ Docker image built: $(BINARY_NAME):$(VERSION)"

.PHONY: docker-run
docker-run: certs docker ## Run in Docker container
	@echo "🐳 Running Docker container..."
	docker run --rm -p 3200:3200 \
		--name tls-monitor \
		-v $(EXAMPLE_DIR)/certs:/app/certs:ro \
		$(BINARY_NAME):latest

# Release targets
.PHONY: release
release: clean deps test
	@echo "Building release binaries..."
	@mkdir -p $(DIST_DIR)
	
	# Linux
	GOOS=linux GOARCH=amd64 $(GOBUILD) $(LDFLAGS) -o $(DIST_DIR)/$(BINARY_NAME)-linux-amd64 .
	GOOS=linux GOARCH=arm64 $(GOBUILD) $(LDFLAGS) -o $(DIST_DIR)/$(BINARY_NAME)-linux-arm64 .
	
	# macOS
	GOOS=darwin GOARCH=amd64 $(GOBUILD) $(LDFLAGS) -o $(DIST_DIR)/$(BINARY_NAME)-darwin-amd64 .
	GOOS=darwin GOARCH=arm64 $(GOBUILD) $(LDFLAGS) -o $(DIST_DIR)/$(BINARY_NAME)-darwin-arm64 .
	
	# Windows
	GOOS=windows GOARCH=amd64 $(GOBUILD) $(LDFLAGS) -o $(DIST_DIR)/$(BINARY_NAME)-windows-amd64.exe .
	
	# Create checksums
	cd $(DIST_DIR) && sha256sum * > checksums.txt
	
	@echo "Release binaries created in $(DIST_DIR)/"

# Development helpers
.PHONY: dev-setup
dev-setup: ## Install necessary go tools and setup test fixtures
	@echo "🚀 Setting up development environment..."
	$(GOCMD) install github.com/golangci/golangci-lint/cmd/golangci-lint@latest
	$(GOCMD) install github.com/securecodewarrior/gosec/v2/cmd/gosec@latest
	@$(MAKE) config-dev
	@mkdir -p cache logs
	@echo "✅ Development environment setup successfully"

.PHONY: certs
certs: ## Generate example certificates for testing
	@echo "🔐 Generating example certificates..."
	@mkdir -p $(EXAMPLE_DIR)/certs

	# Root CA
	@openssl genrsa -out $(EXAMPLE_DIR)/certs/ca.key 2048 2>/dev/null
	@openssl req -new -x509 -key $(EXAMPLE_DIR)/certs/ca.key -out $(EXAMPLE_DIR)/certs/ca-cert.pem -days 365 -subj "/CN=Test CA" 2>/dev/null

	# 1yr_valid certs
	@for i in 1 2 3; do \
		openssl genrsa -out $(EXAMPLE_DIR)/certs/1yr_valid_$$i.key 2048 2>/dev/null; \
		openssl req -new -key $(EXAMPLE_DIR)/certs/1yr_valid_$$i.key -out $(EXAMPLE_DIR)/certs/1yr_valid_$$i.csr -subj "/CN=valid$$i.example.com" 2>/dev/null; \
		openssl x509 -req -in $(EXAMPLE_DIR)/certs/1yr_valid_$$i.csr -CA $(EXAMPLE_DIR)/certs/ca-cert.pem -CAkey $(EXAMPLE_DIR)/certs/ca.key -out $(EXAMPLE_DIR)/certs/1yr_valid_$$i.pem -days 365 2>/dev/null; \
		rm -f $(EXAMPLE_DIR)/certs/1yr_valid_$$i.csr; \
	done

	# Duplicate certs
	@cp $(EXAMPLE_DIR)/certs/1yr_valid_1.pem $(EXAMPLE_DIR)/certs/1yr_valid_dup_1.pem
	@cp $(EXAMPLE_DIR)/certs/1yr_valid_1.pem $(EXAMPLE_DIR)/certs/1yr_valid_dup_2.pem
	@cp $(EXAMPLE_DIR)/certs/1yr_valid_1.key $(EXAMPLE_DIR)/certs/1yr_valid_dup_1.key
	@cp $(EXAMPLE_DIR)/certs/1yr_valid_1.key $(EXAMPLE_DIR)/certs/1yr_valid_dup_2.key

	# Short expiration certs
	@openssl genrsa -out $(EXAMPLE_DIR)/certs/valid_short_1.key 2048 2>/dev/null
	@openssl req -new -key $(EXAMPLE_DIR)/certs/valid_short_1.key -out $(EXAMPLE_DIR)/certs/valid_short_1.csr -subj "/CN=short1.example.com" 2>/dev/null
	@openssl x509 -req -in $(EXAMPLE_DIR)/certs/valid_short_1.csr -CA $(EXAMPLE_DIR)/certs/ca-cert.pem -CAkey $(EXAMPLE_DIR)/certs/ca.key -out $(EXAMPLE_DIR)/certs/valid_short_1.pem -days 5 2>/dev/null
	@rm -f $(EXAMPLE_DIR)/certs/valid_short_1.csr

	@openssl genrsa -out $(EXAMPLE_DIR)/certs/valid_short_2.key 2048 2>/dev/null
	@openssl req -new -key $(EXAMPLE_DIR)/certs/valid_short_2.key -out $(EXAMPLE_DIR)/certs/valid_short_2.csr -subj "/CN=short2.example.com" 2>/dev/null
	@openssl x509 -req -in $(EXAMPLE_DIR)/certs/valid_short_2.csr -CA $(EXAMPLE_DIR)/certs/ca-cert.pem -CAkey $(EXAMPLE_DIR)/certs/ca.key -out $(EXAMPLE_DIR)/certs/valid_short_2.pem -days 180 2>/dev/null
	@rm -f $(EXAMPLE_DIR)/certs/valid_short_2.csr

	# Weak keys
	@for i in 1 2; do \
		openssl genrsa -out $(EXAMPLE_DIR)/certs/1yr_weak_key_$$i.key 512 2>/dev/null; \
		openssl req -new -key $(EXAMPLE_DIR)/certs/1yr_weak_key_$$i.key -out $(EXAMPLE_DIR)/certs/1yr_weak_key_$$i.csr -subj "/CN=weakkey$$i.example.com" 2>/dev/null; \
		openssl x509 -req -in $(EXAMPLE_DIR)/certs/1yr_weak_key_$$i.csr -CA $(EXAMPLE_DIR)/certs/ca-cert.pem -CAkey $(EXAMPLE_DIR)/certs/ca.key -out $(EXAMPLE_DIR)/certs/1yr_weak_key_$$i.pem -days 365 2>/dev/null; \
		rm -f $(EXAMPLE_DIR)/certs/1yr_weak_key_$$i.csr; \
	done

	# Weak algorithms
	@for i in 1 2; do \
		openssl genrsa -out $(EXAMPLE_DIR)/certs/1yr_weak_algo_$$i.key 2048 2>/dev/null; \
		openssl req -new -md5 -key $(EXAMPLE_DIR)/certs/1yr_weak_algo_$$i.key -out $(EXAMPLE_DIR)/certs/1yr_weak_algo_$$i.csr -subj "/CN=weakalgo$$i.example.com" 2>/dev/null; \
		openssl x509 -req -md5 -in $(EXAMPLE_DIR)/certs/1yr_weak_algo_$$i.csr -CA $(EXAMPLE_DIR)/certs/ca-cert.pem -CAkey $(EXAMPLE_DIR)/certs/ca.key -out $(EXAMPLE_DIR)/certs/1yr_weak_algo_$$i.pem -days 365 2>/dev/null; \
		rm -f $(EXAMPLE_DIR)/certs/1yr_weak_algo_$$i.csr; \
	done

	# Simulated DigiCert Issuer via Fake CA
	@openssl genrsa -out $(EXAMPLE_DIR)/certs/fake_digicert_ca.key 2048 2>/dev/null
	@openssl req -new -x509 -key $(EXAMPLE_DIR)/certs/fake_digicert_ca.key -out $(EXAMPLE_DIR)/certs/fake_digicert_ca.pem -days 365 -subj "/O=DigiCert Inc/CN=DigiCert Root CA" 2>/dev/null

	@openssl genrsa -out $(EXAMPLE_DIR)/certs/digicert.key 2048 2>/dev/null
	@openssl req -new -key $(EXAMPLE_DIR)/certs/digicert.key -out $(EXAMPLE_DIR)/certs/digicert.csr -subj "/CN=digicert.example.com" 2>/dev/null
	@openssl x509 -req -in $(EXAMPLE_DIR)/certs/digicert.csr -CA $(EXAMPLE_DIR)/certs/fake_digicert_ca.pem -CAkey $(EXAMPLE_DIR)/certs/fake_digicert_ca.key -out $(EXAMPLE_DIR)/certs/digicert.pem -days 365 2>/dev/null
	@rm -f $(EXAMPLE_DIR)/certs/digicert.csr

	# Simulated Amazon Issuer via Fake CA
	@openssl genrsa -out $(EXAMPLE_DIR)/certs/fake_amazon_ca.key 2048 2>/dev/null
	@openssl req -new -x509 -key $(EXAMPLE_DIR)/certs/fake_amazon_ca.key -out $(EXAMPLE_DIR)/certs/fake_amazon_ca.pem -days 365 -subj "/O=Amazon Trust Services/CN=Amazon Root CA" 2>/dev/null

	@openssl genrsa -out $(EXAMPLE_DIR)/certs/amazon.key 2048 2>/dev/null
	@openssl req -new -key $(EXAMPLE_DIR)/certs/amazon.key -out $(EXAMPLE_DIR)/certs/amazon.csr -subj "/CN=amazon.example.com" 2>/dev/null
	@openssl x509 -req -in $(EXAMPLE_DIR)/certs/amazon.csr -CA $(EXAMPLE_DIR)/certs/fake_amazon_ca.pem -CAkey $(EXAMPLE_DIR)/certs/fake_amazon_ca.key -out $(EXAMPLE_DIR)/certs/amazon.pem -days 365 2>/dev/null
	@rm -f $(EXAMPLE_DIR)/certs/amazon.csr


	# Valid certs with SANs (3–8 entries)
	@openssl genrsa -out $(EXAMPLE_DIR)/certs/san_1.key 2048 2>/dev/null
	@openssl req -new -key $(EXAMPLE_DIR)/certs/san_1.key -out $(EXAMPLE_DIR)/certs/san_1.csr -subj "/CN=san1.example.com" -addext "subjectAltName=DNS:san1.example.com,DNS:www.san1.example.com,DNS:alt1.example.com" 2>/dev/null
	@openssl x509 -req -in $(EXAMPLE_DIR)/certs/san_1.csr -CA $(EXAMPLE_DIR)/certs/ca-cert.pem -CAkey $(EXAMPLE_DIR)/certs/ca.key -out $(EXAMPLE_DIR)/certs/san_1.pem -days 365 -extfile <(echo "subjectAltName=DNS:san1.example.com,DNS:www.san1.example.com,DNS:alt1.example.com") 2>/dev/null
	@rm -f $(EXAMPLE_DIR)/certs/san_1.csr

	@openssl genrsa -out $(EXAMPLE_DIR)/certs/san_2.key 2048 2>/dev/null
	@openssl req -new -key $(EXAMPLE_DIR)/certs/san_2.key -out $(EXAMPLE_DIR)/certs/san_2.csr -subj "/CN=san2.example.com" -addext "subjectAltName=DNS:san2.example.com,DNS:alt2.example.com,DNS:www.alt2.example.com,DNS:dev.alt2.example.com,DNS:test.alt2.example.com,DNS:x.alt2.example.com,DNS:y.alt2.example.com,DNS:z.alt2.example.com" 2>/dev/null
	@openssl x509 -req -in $(EXAMPLE_DIR)/certs/san_2.csr -CA $(EXAMPLE_DIR)/certs/ca-cert.pem -CAkey $(EXAMPLE_DIR)/certs/ca.key -out $(EXAMPLE_DIR)/certs/san_2.pem -days 365 -extfile <(echo "subjectAltName=DNS:san2.example.com,DNS:alt2.example.com,DNS:www.alt2.example.com,DNS:dev.alt2.example.com,DNS:test.alt2.example.com,DNS:x.alt2.example.com,DNS:y.alt2.example.com,DNS:z.alt2.example.com") 2>/dev/null
	@rm -f $(EXAMPLE_DIR)/certs/san_2.csr

	# 2 Valid P12 Certificates
	@for i in 1 2; do \
		openssl genrsa -out $(EXAMPLE_DIR)/certs/p12_cert_$$i.key 2048 2>/dev/null; \
		openssl req -new -key $(EXAMPLE_DIR)/certs/p12_cert_$$i.key -out $(EXAMPLE_DIR)/certs/p12_cert_$$i.csr -subj "/CN=p12cert$$i.example.com" 2>/dev/null; \
		openssl x509 -req -in $(EXAMPLE_DIR)/certs/p12_cert_$$i.csr -CA $(EXAMPLE_DIR)/certs/ca-cert.pem -CAkey $(EXAMPLE_DIR)/certs/ca.key -out $(EXAMPLE_DIR)/certs/p12_cert_$$i.pem -days 365 2>/dev/null; \
		openssl pkcs12 -export -out $(EXAMPLE_DIR)/certs/p12_cert_$$i.p12 -inkey $(EXAMPLE_DIR)/certs/p12_cert_$$i.key -in $(EXAMPLE_DIR)/certs/p12_cert_$$i.pem -passout pass:changeit 2>/dev/null; \
		rm -f $(EXAMPLE_DIR)/certs/p12_cert_$$i.csr; \
	done
	@echo "✅ Example certificates generated in $(EXAMPLE_DIR)/certs/"

# # Development configuration
.PHONY: config-dev
config-dev: certs ## Create development configuration file
	@echo "🛠️  Creating development configuration..."
	@mkdir -p $(EXAMPLE_DIR)/configs
	@echo "port: 3200" > $(EXAMPLE_DIR)/configs/config.dev.yaml
	@echo 'bind_address: "0.0.0.0"' >> $(EXAMPLE_DIR)/configs/config.dev.yaml
	@echo "certificate_directories:" >> $(EXAMPLE_DIR)/configs/config.dev.yaml
	@echo "  - \"$(EXAMPLE_DIR)/certs\"" >> $(EXAMPLE_DIR)/configs/config.dev.yaml
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

# Monitoring and profiling
.PHONY: profile-cpu
profile-cpu: build
	@echo "Running CPU profiling..."
	./$(BUILD_DIR)/$(BINARY_NAME) -cpuprofile=cpu.prof

.PHONY: profile-mem
profile-mem: build
	@echo "Running memory profiling..."
	./$(BUILD_DIR)/$(BINARY_NAME) -memprofile=mem.prof

# Quick development workflow
.PHONY: quick
quick: fmt test build

.PHONY: check
check: fmt lint vet test

# CI/CD helpers
.PHONY: ci
ci: deps fmt lint vet test-race test-cover

.PHONY: pre-commit
pre-commit: fmt lint vet test

# Version information
.PHONY: version
version: ## Show version information
	@echo "💾 Version:	$(VERSION)"
	@echo "Build Time:	$(BUILD_TIME)"
	@echo "Git Commit:	$(GIT_COMMIT)"
	@echo "Go Version:	$(GO_VERSION)"

# Show current status
.PHONY: status
status:
	@echo "TLS Certificate Monitor Status:"
	@echo "  Version:	$(VERSION)"
	@echo "  Go Version:	$(GO_VERSION)"
	@echo "  Platform:	$$(go env GOOS)/$$(go env GOARCH)"
	@echo "  Module:	$$(head -1 go.mod | cut -d' ' -f2)"
	@echo ""
	@echo "Project Structure:"
	@find . -name "*.go" -not -path "./vendor/*" | head -10
	@echo ""

# File watchers for development
.PHONY: watch
watch:
	@echo "👀 Watching for changes..."
	@which inotifywait > /dev/null || (echo "Please install inotify-tools"; exit 1)
	@while inotifywait -r -e modify,create,delete --exclude='\.git|build/|dist/' .; do \
		make quick; \
	done

# Documentation
.PHONY: docs
docs:
	@echo "📄 Generating documentation..."
	@mkdir -p docs
	$(GOCMD) doc -all ./... > docs/api.txt
	@echo "✅ Documentation generated in docs/"