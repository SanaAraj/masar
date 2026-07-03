# syntax=docker/dockerfile:1

# ---- Builder: resolve and install into an isolated venv ---------------------
FROM python:3.11-slim AS builder

WORKDIR /app
RUN pip install --no-cache-dir uv

# Copy only what the build needs, then install the package and its deps.
COPY pyproject.toml README.md ./
COPY src ./src
RUN uv venv /opt/venv \
    && VIRTUAL_ENV=/opt/venv uv pip install --no-cache .

# ---- Runtime: minimal image running as a non-root user ----------------------
FROM python:3.11-slim AS runtime

WORKDIR /app
RUN useradd --create-home --uid 1000 masar

COPY --from=builder /opt/venv /opt/venv
COPY configs ./configs

ENV PATH="/opt/venv/bin:$PATH" \
    MASAR_CONFIG=configs/routing.v0.yaml \
    PYTHONUNBUFFERED=1

USER masar
EXPOSE 8000

HEALTHCHECK --interval=30s --timeout=3s --start-period=5s --retries=3 \
    CMD python -c "import urllib.request,sys; sys.exit(0 if urllib.request.urlopen('http://localhost:8000/healthz').status==200 else 1)"

CMD ["uvicorn", "masar.app:create_app", "--factory", "--host", "0.0.0.0", "--port", "8000"]
