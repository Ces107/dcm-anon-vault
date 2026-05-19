# Stage 1: build dependencies
FROM python:3.12-slim AS builder

WORKDIR /build
COPY pyproject.toml .
RUN pip install --no-cache-dir --prefix=/install \
    "fastapi>=0.110,<1.0" \
    "uvicorn[standard]>=0.27,<1.0" \
    "python-multipart>=0.0.9,<1.0" \
    "pydantic>=2.6,<3.0" \
    "sqlalchemy>=2.0,<3.0" \
    "stripe>=8.0,<13.0" \
    "pydicom>=3.0.2,<4.0" \
    "dcm-anonymizer>=0.4.0,<0.5"

# Stage 2: runtime image
FROM python:3.12-slim

# Create a non-root user; container must not run as root.
RUN groupadd -r app && useradd -r -g app -d /app -s /usr/sbin/nologin app \
    && mkdir -p /app /data \
    && chown -R app:app /app /data

WORKDIR /app

COPY --from=builder /install /usr/local
COPY --chown=app:app src/ ./src/

ENV DCM_DB_URL=sqlite:////data/vault.db \
    PYTHONPATH=/app/src \
    PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1

USER app
EXPOSE 8080

HEALTHCHECK --interval=30s --timeout=5s --start-period=10s --retries=3 \
    CMD python -c "import urllib.request; urllib.request.urlopen('http://localhost:8080/health')" || exit 1

CMD ["python", "-m", "uvicorn", "dcm_anon_vault.app:app", "--host", "0.0.0.0", "--port", "8080"]
