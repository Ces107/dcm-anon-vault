# Stage 1: build dependencies
FROM python:3.12-slim AS builder

WORKDIR /build
COPY pyproject.toml .
# Install runtime deps only
RUN pip install --no-cache-dir --prefix=/install \
    "fastapi>=0.100" \
    "uvicorn[standard]>=0.20" \
    "python-multipart>=0.0.7" \
    "pydantic>=2" \
    "sqlalchemy>=2.0" \
    "stripe>=7" \
    "pydicom>=2.4"

# Stage 2: runtime image
FROM python:3.12-slim

WORKDIR /app

# Copy installed packages from builder
COPY --from=builder /install /usr/local

# Copy source
COPY src/ ./src/

# Create data directory for SQLite volume mount
RUN mkdir -p /data

ENV DCM_DB_URL=sqlite:////data/vault.db
ENV PYTHONPATH=/app/src

EXPOSE 8080

HEALTHCHECK --interval=30s --timeout=5s --start-period=10s --retries=3 \
    CMD python -c "import urllib.request; urllib.request.urlopen('http://localhost:8080/health')" || exit 1

CMD ["python", "-m", "uvicorn", "dcm_anon_vault.app:app", "--host", "0.0.0.0", "--port", "8080"]
