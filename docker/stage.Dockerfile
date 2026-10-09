# syntax=docker/dockerfile:1
#
# One image recipe for every Python container. docker-compose.yml builds it once per service
# with different build args, so each image contains only the dependencies its stage needs.
#
# Targets:
#   api      uvicorn serving the FastAPI app (EXTRAS=api); has its own HEALTHCHECK
#   worker   the default: scheduler and stage workers, whose command compose supplies
#
# Build args:
#   EXTRAS            comma-separated extras from pyproject.toml, e.g. "ingest"
#   APT_PACKAGES      system packages for the runtime image, e.g. "ffmpeg"
#   TORCH_INDEX_URL   when set, install torch from this index first (CPU wheels, smaller image)

ARG PYTHON_VERSION=3.12

FROM python:${PYTHON_VERSION}-slim AS builder
ARG EXTRAS=""
ARG TORCH_INDEX_URL=""
ENV PIP_NO_CACHE_DIR=1 PIP_DISABLE_PIP_VERSION_CHECK=1
RUN python -m venv /opt/venv
ENV PATH="/opt/venv/bin:${PATH}"
WORKDIR /build
COPY pyproject.toml README.md LICENSE ./
COPY src ./src
RUN if [ -n "${TORCH_INDEX_URL}" ]; then pip install torch --index-url "${TORCH_INDEX_URL}"; fi \
    && if [ -n "${EXTRAS}" ]; then pip install ".[${EXTRAS}]"; else pip install .; fi

FROM python:${PYTHON_VERSION}-slim AS runtime
ARG APT_PACKAGES=""
ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PATH="/opt/venv/bin:${PATH}"
# hadolint ignore=DL3008
RUN if [ -n "${APT_PACKAGES}" ]; then \
        apt-get update \
        && apt-get install -y --no-install-recommends ${APT_PACKAGES} \
        && rm -rf /var/lib/apt/lists/*; \
    fi

# Non-root user. Directories that compose mounts volumes onto are created here, owned by the
# user, so named volumes inherit that ownership on first use.
RUN useradd --uid 10001 --create-home --shell /usr/sbin/nologin app \
    && mkdir -p /data/ingest /data/uploads /data/tts_cache /data/audio /data/feeds /data/scheduler \
        /home/app/.cache/huggingface /app/config /app/prompts /app/assets \
    && chown -R app:app /data /home/app /app

COPY --from=builder /opt/venv /opt/venv
USER app
WORKDIR /app

# --- API: uvicorn. Tune with UVICORN_* environment variables (UVICORN_WORKERS, UVICORN_PORT, ...).
FROM runtime AS api
ENV UVICORN_HOST=0.0.0.0 \
    UVICORN_PORT=8000 \
    UVICORN_PROXY_HEADERS=true \
    UVICORN_FORWARDED_ALLOW_IPS=*
EXPOSE 8000
HEALTHCHECK --interval=10s --timeout=3s --start-period=10s --retries=5 \
    CMD ["python", "-c", "import urllib.request as u; u.urlopen('http://localhost:8000/health', timeout=2)"]
CMD ["uvicorn", "podcast_engine.api.main:app"]

# --- Worker: must stay the last stage so it is the default build target.
FROM runtime AS worker
