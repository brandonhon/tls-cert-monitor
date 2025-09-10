# Build stage - Alpine for smaller size
FROM python:3.11-alpine AS builder

# Install build dependencies (only what's needed)
RUN apk add --no-cache \
    gcc \
    musl-dev \
    libffi-dev \
    openssl-dev \
    python3-dev

# Set working directory
WORKDIR /app

# Copy requirements first (for better caching)
COPY requirements.txt .

# Install Python dependencies to a local directory
# Use --no-cache-dir to avoid storing pip cache
# Use --no-deps for faster builds if dependencies are well-defined
RUN pip install --no-cache-dir --user --no-warn-script-location -r requirements.txt

# Production stage - minimal Alpine image
FROM python:3.11-alpine

# Install only runtime dependencies (minimal set)
RUN apk add --no-cache \
    ca-certificates \
    wget \
    && rm -rf /var/cache/apk/*

# Create non-root user (Alpine style)
RUN addgroup -g 1000 appuser && \
    adduser -D -u 1000 -G appuser appuser

# Set working directory
WORKDIR /app

# Copy Python packages from builder stage
COPY --from=builder --chown=appuser:appuser /root/.local /home/appuser/.local

# Copy only necessary application files (exclude dev files, tests, etc.)
COPY --chown=appuser:appuser main.py ./
COPY --chown=appuser:appuser tls_cert_monitor/ ./tls_cert_monitor/
COPY --chown=appuser:appuser docker/docker.config.yaml ./config.yaml

# Create necessary directories with proper permissions
RUN mkdir -p /app/cache /app/logs /app/certs && \
    chown -R appuser:appuser /app

# Switch to non-root user
USER appuser

# Add local Python packages to PATH
ENV PATH=/home/appuser/.local/bin:$PATH \
    PYTHONPATH=/app \
    PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1

# Expose port
EXPOSE 3200

# Health check using wget with GET method
HEALTHCHECK --interval=30s --timeout=10s --start-period=5s --retries=3 \
    CMD wget --no-verbose --tries=1 --method=GET -O /dev/null http://localhost:3200/healthz || exit 1

# Default command - use copied docker config
CMD ["python", "main.py", "--config=config.yaml"]