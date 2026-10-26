# syntax=docker/dockerfile:1.7
#
# Elexon's API is public and needs no credentials, so this image carries no
# secrets and nothing needs to be mounted in at runtime.
FROM python:3.12-slim

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PIP_NO_CACHE_DIR=1

WORKDIR /app

# Dependencies first, so edits to application code reuse the cached layer.
COPY requirements.txt ./

# `extra_ca` is an optional build secret holding a PEM CA bundle, for networks
# behind a TLS-inspecting proxy where the package index presents a corporate
# certificate. It is absent and ignored on an ordinary network, and because it
# is a secret mount it never becomes part of an image layer.
#   docker build --secret id=extra_ca,src=/path/to/ca-bundle.crt .
RUN --mount=type=secret,id=extra_ca,target=/tmp/extra-ca.crt,required=false \
    if grep -q "BEGIN CERTIFICATE" /tmp/extra-ca.crt 2>/dev/null; then \
        cp /tmp/extra-ca.crt /usr/local/share/ca-certificates/extra-ca.crt && \
        update-ca-certificates && \
        export PIP_CERT=/tmp/extra-ca.crt; \
    fi; \
    pip install --no-cache-dir -r requirements.txt

COPY app ./app

# Run unprivileged.
RUN useradd --create-home --uid 10001 appuser && chown -R appuser:appuser /app
USER appuser

EXPOSE 8000

# Compose polls this; the frontend waits for it to pass before starting.
HEALTHCHECK --interval=15s --timeout=5s --start-period=10s --retries=3 \
  CMD python -c "import urllib.request,sys; sys.exit(0 if urllib.request.urlopen('http://127.0.0.1:8000/api/health', timeout=4).status == 200 else 1)"

CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8000"]
