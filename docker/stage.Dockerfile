
ARG PYTHON_VERSION=3.12

FROM python:${PYTHON_VERSION}-slim AS builder
ARG EXTRAS=""
ARG TORCH_INDEX_URL=""

ENV PIP_DISABLE_PIP_VERSION_CHECK=1 PIP_DEFAULT_TIMEOUT=120 PIP_RETRIES=10
RUN python -m venv /opt/venv
ENV PATH="/opt/venv/bin:${PATH}"
WORKDIR /build
COPY pyproject.toml README.md LICENSE ./
COPY src ./src
# TORCH_INDEX_URL (CPU wheels) is an extra index for the whole install, so a pinned torch (Chatterbox
# pins torch==2.6.0) resolves to its +cpu build there instead of PyPI's multi-GB CUDA one.
RUN --mount=type=cache,target=/root/.cache/pip \
    if [ -n "${TORCH_INDEX_URL}" ]; then set -- --extra-index-url "${TORCH_INDEX_URL}"; fi \
    && if [ -n "${EXTRAS}" ]; then pip install "$@" ".[${EXTRAS}]"; else pip install "$@" .; fi

FROM python:${PYTHON_VERSION}-slim AS runtime
ARG APT_PACKAGES=""
ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PATH="/opt/venv/bin:${PATH}"

    RUN if [ -n "${APT_PACKAGES}" ]; then \
        apt-get update \
        && apt-get install -y --no-install-recommends ${APT_PACKAGES} \
        && rm -rf /var/lib/apt/lists/*; \
    fi


RUN useradd --uid 10001 --create-home --shell /usr/sbin/nologin app \
    && mkdir -p /data/ingest /data/uploads /data/tts_cache /data/audio /data/feeds /data/scheduler \
        /home/app/.cache/huggingface /app/config /app/prompts /app/assets \
    && chown -R app:app /data /home/app /app

COPY --from=builder /opt/venv /opt/venv
USER app
WORKDIR /app

FROM runtime AS api
ENV UVICORN_HOST=0.0.0.0 \
    UVICORN_PORT=8000 \
    UVICORN_PROXY_HEADERS=true \
    UVICORN_FORWARDED_ALLOW_IPS=*
EXPOSE 8000
HEALTHCHECK --interval=10s --timeout=3s --start-period=10s --retries=5 \
    CMD ["python", "-c", "import urllib.request as u; u.urlopen('http://localhost:8000/health', timeout=2)"]
CMD ["uvicorn", "podcast_engine.api.main:app"]

FROM runtime AS worker
