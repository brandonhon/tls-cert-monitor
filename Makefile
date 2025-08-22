# TLS Certificate Monitor Makefile

# Shell setup
SHELL := /bin/bash

# Build variables
BINARY_NAME=tls-cert-monitor
VERSION ?= $(shell git describe --tags --always --dirty 2>/dev/null || echo "dev")
BUILD_TIME ?= $(shell date -u '+%Y-%m-%d_%H:%M:%S')
GIT_COMMIT ?= $(shell git rev-parse HEAD 2>/dev/null || echo "unknown")

# Go variables
GOCMD=go
GOBUILD=$(GOCMD) build
GOCLEAN=$(GOCMD) clean
GOTEST=$(GOCMD) test
GOGET=$(GOCMD) get
GOMOD=$(GOCMD) mod
GOFMT=gofmt
GOLINT=golangci-lint

# Build flags
LDFLAGS=-ldflags "-X main.version=$(VERSION) -X main.buildTime=$(BUILD_TIME) -X main.gitCommit=$(GIT_COMMIT)"

# Directories
BUILD_DIR=build
DIST_DIR=dist
COVERAGE_DIR=coverage
EXAMPLE_DIR=./test/fixtures

# Default target
.PHONY: all
all: clean fmt lint test build

# Help target
.PHONY: help
help:
	@echo "TLS Certificate Monitor - Available targets:"
	@echo ""
	@echo "  build        	  Build the binary"
	@echo "  example-certs	  Generate example certificates for testing"
	@echo "  test         	  Run tests"
	@echo "  test-v       	  Run tests with verbose output"
	@echo "  test-race    	  Run tests with race detection"
	@echo "  test-cover   	  Run tests with coverage"
	@echo "  bench        	  Run benchmarks"
	@echo "  fmt          	  Format code"
	@echo "  lint         	  Run linter"
	@echo "  clean        	  Clean build artifacts"
	@echo "  deps         	  Download dependencies"
	@echo "  tidy         	  Tidy dependencies"
	@echo "  run          	  Run the application"
	@echo "  install      	  Install the binary"
	@echo "  docker-build 	  Build Docker image"
	@echo "  release      	  Build release binaries for all platforms"
	@echo ""

# Build targets
.PHONY: build
build: deps
	@echo "Building $(BINARY_NAME)..."
	@mkdir -p $(BUILD_DIR)
	$(GOBUILD) $(LDFLAGS) -o $(BUILD_DIR)/$(BINARY_NAME) .

.PHONY: build-race
build-race: deps
	@echo "Building $(BINARY_NAME) with race detection..."
	@mkdir -p $(BUILD_DIR)
	$(GOBUILD) -race $(LDFLAGS) -o $(BUILD_DIR)/$(BINARY_NAME)-race .

# Test targets
.PHONY: test
test: deps
	@echo "Running tests..."
	$(GOTEST) -v ./...

.PHONY: test-v
test-v: deps
	@echo "Running tests with verbose output..."
	$(GOTEST) -v -count=1 ./...

.PHONY: test-race
test-race: deps
	@echo "Running tests with race detection..."
	$(GOTEST) -race -v ./...

.PHONY: test-cover
test-cover: deps
	@echo "Running tests with coverage..."
	@mkdir -p $(COVERAGE_DIR)
	$(GOTEST) -v -coverprofile=$(COVERAGE_DIR)/coverage.out ./...
	$(GOCMD) tool cover -html=$(COVERAGE_DIR)/coverage.out -o $(COVERAGE_DIR)/coverage.html
	@echo "Coverage report generated: $(COVERAGE_DIR)/coverage.html"

.PHONY: test-integration
test-integration: deps
	@echo "Running integration tests..."
	$(GOTEST) -v -tags=integration ./test/...

.PHONY: bench
bench: deps
	@echo "Running benchmarks..."
	$(GOTEST) -bench=. -benchmem ./...

# Code quality targets
.PHONY: fmt
fmt:
	@echo "Formatting code..."
	$(GOFMT) -s -w .
	$(GOCMD) mod tidy

.PHONY: lint
lint:
	@echo "Running linter..."
	@which $(GOLINT) > /dev/null || (echo "golangci-lint not found. Install with: curl -sSfL https://raw.githubusercontent.com/golangci/golangci-lint/master/install.sh | sh -s -- -b $$(go env GOPATH)/bin v1.54.2"; exit 1)
	$(GOLINT) run ./...

.PHONY: vet
vet: deps
	@echo "Running go vet..."
	$(GOCMD) vet ./...

# Dependency targets
.PHONY: deps
deps:
	@echo "Downloading dependencies..."
	$(GOMOD) download

.PHONY: tidy
tidy:
	@echo "Tidying dependencies..."
	$(GOMOD) tidy
	$(GOMOD) verify

.PHONY: vendor
vendor: deps
	@echo "Vendoring dependencies..."
	$(GOMOD) vendor

# Clean targets
.PHONY: clean
clean:
	@echo "Cleaning..."
	$(GOCLEAN)
	@rm -rf $(BUILD_DIR)
	@rm -rf $(DIST_DIR)
	@rm -rf $(COVERAGE_DIR)
	@rm -rf vendor/

.PHONY: clean-cache
clean-cache:
	@echo "Cleaning go cache..."
	$(GOCMD) clean -cache -testcache -modcache

# Run targets
.PHONY: run
run: build
	@echo "Running $(BINARY_NAME)..."
	./$(BUILD_DIR)/$(BINARY_NAME)

.PHONY: run-dev
run-dev: build
	@echo "Running $(BINARY_NAME) in development mode..."
	./$(BUILD_DIR)/$(BINARY_NAME) -config=config.yaml

.PHONY: run-dry
run-dry: build
	@echo "Running $(BINARY_NAME) in dry-run mode..."
	./$(BUILD_DIR)/$(BINARY_NAME) -config=config.yaml -dry-run

# Install targets
.PHONY: install
install: build
	@echo "Installing $(BINARY_NAME)..."
	$(GOCMD) install $(LDFLAGS) .

# Docker targets
.PHONY: docker-build
docker-build:
	@echo "Building Docker image..."
	docker build -t $(BINARY_NAME):$(VERSION) .
	docker build -t $(BINARY_NAME):latest .

.PHONY: docker-run
docker-run:
	@echo "Running Docker container..."
	docker run --rm -p 3200:3200 -v $(PWD)/config.yaml:/app/config.yaml $(BINARY_NAME):latest

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
dev-setup:
	@echo "Setting up development environment..."
	$(GOGET) -u github.com/golangci/golangci-lint/cmd/golangci-lint@latest
	@mkdir -p cache logs

.PHONY: generate
generate:
	@echo "Running go generate..."
	$(GOCMD) generate ./...

.PHONY: mock
mock:
	@echo "Generating mocks..."
	@which mockgen > /dev/null || $(GOGET) github.com/golang/mock/mockgen@latest
	$(GOCMD) generate -tags=mock ./...

.PHONY: example-certs
example-certs: ## Generate example certificates for testing
	@echo "🔐 Generating example certificates..."
	@mkdir -p $(EXAMPLE_DIR)/example-certs

	# Root CA
	@openssl genrsa -out $(EXAMPLE_DIR)/example-certs/ca.key 2048 2>/dev/null
	@openssl req -new -x509 -key $(EXAMPLE_DIR)/example-certs/ca.key -out $(EXAMPLE_DIR)/example-certs/ca-cert.pem -days 365 -subj "/CN=Test CA" 2>/dev/null

	# 1yr_valid certs
	@for i in 1 2 3; do \
		openssl genrsa -out $(EXAMPLE_DIR)/example-certs/1yr_valid_$$i.key 2048 2>/dev/null; \
		openssl req -new -key $(EXAMPLE_DIR)/example-certs/1yr_valid_$$i.key -out $(EXAMPLE_DIR)/example-certs/1yr_valid_$$i.csr -subj "/CN=valid$$i.example.com" 2>/dev/null; \
		openssl x509 -req -in $(EXAMPLE_DIR)/example-certs/1yr_valid_$$i.csr -CA $(EXAMPLE_DIR)/example-certs/ca-cert.pem -CAkey $(EXAMPLE_DIR)/example-certs/ca.key -out $(EXAMPLE_DIR)/example-certs/1yr_valid_$$i.pem -days 365 2>/dev/null; \
		rm -f $(EXAMPLE_DIR)/example-certs/1yr_valid_$$i.csr; \
	done

	# Duplicate certs
	@cp $(EXAMPLE_DIR)/example-certs/1yr_valid_1.pem $(EXAMPLE_DIR)/example-certs/1yr_valid_dup_1.pem
	@cp $(EXAMPLE_DIR)/example-certs/1yr_valid_1.pem $(EXAMPLE_DIR)/example-certs/1yr_valid_dup_2.pem
	@cp $(EXAMPLE_DIR)/example-certs/1yr_valid_1.key $(EXAMPLE_DIR)/example-certs/1yr_valid_dup_1.key
	@cp $(EXAMPLE_DIR)/example-certs/1yr_valid_1.key $(EXAMPLE_DIR)/example-certs/1yr_valid_dup_2.key

	# Short expiration certs
	@openssl genrsa -out $(EXAMPLE_DIR)/example-certs/valid_short_1.key 2048 2>/dev/null
	@openssl req -new -key $(EXAMPLE_DIR)/example-certs/valid_short_1.key -out $(EXAMPLE_DIR)/example-certs/valid_short_1.csr -subj "/CN=short1.example.com" 2>/dev/null
	@openssl x509 -req -in $(EXAMPLE_DIR)/example-certs/valid_short_1.csr -CA $(EXAMPLE_DIR)/example-certs/ca-cert.pem -CAkey $(EXAMPLE_DIR)/example-certs/ca.key -out $(EXAMPLE_DIR)/example-certs/valid_short_1.pem -days 5 2>/dev/null
	@rm -f $(EXAMPLE_DIR)/example-certs/valid_short_1.csr

	@openssl genrsa -out $(EXAMPLE_DIR)/example-certs/valid_short_2.key 2048 2>/dev/null
	@openssl req -new -key $(EXAMPLE_DIR)/example-certs/valid_short_2.key -out $(EXAMPLE_DIR)/example-certs/valid_short_2.csr -subj "/CN=short2.example.com" 2>/dev/null
	@openssl x509 -req -in $(EXAMPLE_DIR)/example-certs/valid_short_2.csr -CA $(EXAMPLE_DIR)/example-certs/ca-cert.pem -CAkey $(EXAMPLE_DIR)/example-certs/ca.key -out $(EXAMPLE_DIR)/example-certs/valid_short_2.pem -days 180 2>/dev/null
	@rm -f $(EXAMPLE_DIR)/example-certs/valid_short_2.csr

	# Weak keys
	@for i in 1 2; do \
		openssl genrsa -out $(EXAMPLE_DIR)/example-certs/1yr_weak_key_$$i.key 512 2>/dev/null; \
		openssl req -new -key $(EXAMPLE_DIR)/example-certs/1yr_weak_key_$$i.key -out $(EXAMPLE_DIR)/example-certs/1yr_weak_key_$$i.csr -subj "/CN=weakkey$$i.example.com" 2>/dev/null; \
		openssl x509 -req -in $(EXAMPLE_DIR)/example-certs/1yr_weak_key_$$i.csr -CA $(EXAMPLE_DIR)/example-certs/ca-cert.pem -CAkey $(EXAMPLE_DIR)/example-certs/ca.key -out $(EXAMPLE_DIR)/example-certs/1yr_weak_key_$$i.pem -days 365 2>/dev/null; \
		rm -f $(EXAMPLE_DIR)/example-certs/1yr_weak_key_$$i.csr; \
	done

	# Weak algorithms
	@for i in 1 2; do \
		openssl genrsa -out $(EXAMPLE_DIR)/example-certs/1yr_weak_algo_$$i.key 2048 2>/dev/null; \
		openssl req -new -md5 -key $(EXAMPLE_DIR)/example-certs/1yr_weak_algo_$$i.key -out $(EXAMPLE_DIR)/example-certs/1yr_weak_algo_$$i.csr -subj "/CN=weakalgo$$i.example.com" 2>/dev/null; \
		openssl x509 -req -md5 -in $(EXAMPLE_DIR)/example-certs/1yr_weak_algo_$$i.csr -CA $(EXAMPLE_DIR)/example-certs/ca-cert.pem -CAkey $(EXAMPLE_DIR)/example-certs/ca.key -out $(EXAMPLE_DIR)/example-certs/1yr_weak_algo_$$i.pem -days 365 2>/dev/null; \
		rm -f $(EXAMPLE_DIR)/example-certs/1yr_weak_algo_$$i.csr; \
	done

	# Simulated DigiCert Issuer via Fake CA
	@openssl genrsa -out $(EXAMPLE_DIR)/example-certs/fake_digicert_ca.key 2048 2>/dev/null
	@openssl req -new -x509 -key $(EXAMPLE_DIR)/example-certs/fake_digicert_ca.key -out $(EXAMPLE_DIR)/example-certs/fake_digicert_ca.pem -days 365 -subj "/O=DigiCert Inc/CN=DigiCert Root CA" 2>/dev/null

	@openssl genrsa -out $(EXAMPLE_DIR)/example-certs/digicert.key 2048 2>/dev/null
	@openssl req -new -key $(EXAMPLE_DIR)/example-certs/digicert.key -out $(EXAMPLE_DIR)/example-certs/digicert.csr -subj "/CN=digicert.example.com" 2>/dev/null
	@openssl x509 -req -in $(EXAMPLE_DIR)/example-certs/digicert.csr -CA $(EXAMPLE_DIR)/example-certs/fake_digicert_ca.pem -CAkey $(EXAMPLE_DIR)/example-certs/fake_digicert_ca.key -out $(EXAMPLE_DIR)/example-certs/digicert.pem -days 365 2>/dev/null
	@rm -f $(EXAMPLE_DIR)/example-certs/digicert.csr

	# Simulated Amazon Issuer via Fake CA
	@openssl genrsa -out $(EXAMPLE_DIR)/example-certs/fake_amazon_ca.key 2048 2>/dev/null
	@openssl req -new -x509 -key $(EXAMPLE_DIR)/example-certs/fake_amazon_ca.key -out $(EXAMPLE_DIR)/example-certs/fake_amazon_ca.pem -days 365 -subj "/O=Amazon Trust Services/CN=Amazon Root CA" 2>/dev/null

	@openssl genrsa -out $(EXAMPLE_DIR)/example-certs/amazon.key 2048 2>/dev/null
	@openssl req -new -key $(EXAMPLE_DIR)/example-certs/amazon.key -out $(EXAMPLE_DIR)/example-certs/amazon.csr -subj "/CN=amazon.example.com" 2>/dev/null
	@openssl x509 -req -in $(EXAMPLE_DIR)/example-certs/amazon.csr -CA $(EXAMPLE_DIR)/example-certs/fake_amazon_ca.pem -CAkey $(EXAMPLE_DIR)/example-certs/fake_amazon_ca.key -out $(EXAMPLE_DIR)/example-certs/amazon.pem -days 365 2>/dev/null
	@rm -f $(EXAMPLE_DIR)/example-certs/amazon.csr


	# Valid certs with SANs (3–8 entries)
	@openssl genrsa -out $(EXAMPLE_DIR)/example-certs/san_1.key 2048 2>/dev/null
	@openssl req -new -key $(EXAMPLE_DIR)/example-certs/san_1.key -out $(EXAMPLE_DIR)/example-certs/san_1.csr -subj "/CN=san1.example.com" -addext "subjectAltName=DNS:san1.example.com,DNS:www.san1.example.com,DNS:alt1.example.com" 2>/dev/null
	@openssl x509 -req -in $(EXAMPLE_DIR)/example-certs/san_1.csr -CA $(EXAMPLE_DIR)/example-certs/ca-cert.pem -CAkey $(EXAMPLE_DIR)/example-certs/ca.key -out $(EXAMPLE_DIR)/example-certs/san_1.pem -days 365 -extfile <(echo "subjectAltName=DNS:san1.example.com,DNS:www.san1.example.com,DNS:alt1.example.com") 2>/dev/null
	@rm -f $(EXAMPLE_DIR)/example-certs/san_1.csr

	@openssl genrsa -out $(EXAMPLE_DIR)/example-certs/san_2.key 2048 2>/dev/null
	@openssl req -new -key $(EXAMPLE_DIR)/example-certs/san_2.key -out $(EXAMPLE_DIR)/example-certs/san_2.csr -subj "/CN=san2.example.com" -addext "subjectAltName=DNS:san2.example.com,DNS:alt2.example.com,DNS:www.alt2.example.com,DNS:dev.alt2.example.com,DNS:test.alt2.example.com,DNS:x.alt2.example.com,DNS:y.alt2.example.com,DNS:z.alt2.example.com" 2>/dev/null
	@openssl x509 -req -in $(EXAMPLE_DIR)/example-certs/san_2.csr -CA $(EXAMPLE_DIR)/example-certs/ca-cert.pem -CAkey $(EXAMPLE_DIR)/example-certs/ca.key -out $(EXAMPLE_DIR)/example-certs/san_2.pem -days 365 -extfile <(echo "subjectAltName=DNS:san2.example.com,DNS:alt2.example.com,DNS:www.alt2.example.com,DNS:dev.alt2.example.com,DNS:test.alt2.example.com,DNS:x.alt2.example.com,DNS:y.alt2.example.com,DNS:z.alt2.example.com") 2>/dev/null
	@rm -f $(EXAMPLE_DIR)/example-certs/san_2.csr

	# 2 Valid P12 Certificates
	@for i in 1 2; do \
		openssl genrsa -out $(EXAMPLE_DIR)/example-certs/p12_cert_$$i.key 2048 2>/dev/null; \
		openssl req -new -key $(EXAMPLE_DIR)/example-certs/p12_cert_$$i.key -out $(EXAMPLE_DIR)/example-certs/p12_cert_$$i.csr -subj "/CN=p12cert$$i.example.com" 2>/dev/null; \
		openssl x509 -req -in $(EXAMPLE_DIR)/example-certs/p12_cert_$$i.csr -CA $(EXAMPLE_DIR)/example-certs/ca-cert.pem -CAkey $(EXAMPLE_DIR)/example-certs/ca.key -out $(EXAMPLE_DIR)/example-certs/p12_cert_$$i.pem -days 365 2>/dev/null; \
		openssl pkcs12 -export -out $(EXAMPLE_DIR)/example-certs/p12_cert_$$i.p12 -inkey $(EXAMPLE_DIR)/example-certs/p12_cert_$$i.key -in $(EXAMPLE_DIR)/example-certs/p12_cert_$$i.pem -passout pass:changeit 2>/dev/null; \
		rm -f $(EXAMPLE_DIR)/example-certs/p12_cert_$$i.csr; \
	done

	@echo "✅ Example certificates generated in $(EXAMPLE_DIR)/example-certs/"

# Database/Migration helpers (if needed in future)
.PHONY: migrate-up
migrate-up:
	@echo "Running database migrations..."
	# Add migration commands here when needed

.PHONY: migrate-down
migrate-down:
	@echo "Rolling back database migrations..."
	# Add rollback commands here when needed

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
version:
	@echo "Version: $(VERSION)"
	@echo "Build Time: $(BUILD_TIME)"
	@echo "Git Commit: $(GIT_COMMIT)"

# Show current status
.PHONY: status
status:
	@echo "TLS Certificate Monitor Status:"
	@echo "  Version: $(VERSION)"
	@echo "  Go Version: $$(go version)"
	@echo "  Platform: $$(go env GOOS)/$$(go env GOARCH)"
	@echo "  Module: $$(head -1 go.mod | cut -d' ' -f2)"
	@echo ""
	@echo "Project Structure:"
	@find . -name "*.go" -not -path "./vendor/*" | head -10
	@echo ""

# File watchers for development
.PHONY: watch
watch:
	@echo "Watching for changes..."
	@which inotifywait > /dev/null || (echo "Please install inotify-tools"; exit 1)
	@while inotifywait -r -e modify,create,delete --exclude='\.git|build/|dist/' .; do \
		make quick; \
	done

# Documentation
.PHONY: docs
docs:
	@echo "Generating documentation..."
	$(GOCMD) doc -all ./... > docs/api.txt
	@echo "Documentation generated in docs/"