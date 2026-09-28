# Verified with docker buildx imagetools inspect; update procedure in docs/development.md.
FROM python:3.12.14-slim-bookworm@sha256:392307d22300de8b5986851a12d9176dfc0fc073e65bf6523ebd7dcbeb23564e AS base

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PIP_DISABLE_PIP_VERSION_CHECK=1

FROM base AS build
WORKDIR /build
COPY requirements.txt ./
# Wheels only: no compiler, source builds, or unconstrained build dependencies.
# The runtime lock includes setuptools (required by torch), also our build backend.
# This build-only cache is never copied into an image layer. Hashes are still checked.
RUN --mount=type=cache,id=intellectaengine-pip,target=/root/.cache/pip \
    python -m venv /opt/venv \
    && /opt/venv/bin/pip install --timeout=120 --retries=5 \
        --require-hashes --only-binary=:all: -r requirements.txt
COPY pyproject.toml MANIFEST.in README.md LICENSE THIRD_PARTY_NOTICES.md ./
COPY src/intellectaengine/ ./src/intellectaengine/
RUN /opt/venv/bin/pip wheel --no-deps --no-build-isolation --wheel-dir /wheels . \
    && /opt/venv/bin/pip install --no-deps --no-index /wheels/intellectaengine-*.whl \
    && /opt/venv/bin/pip check

FROM base AS runtime
# No additional OS packages: the supported amd64 wheels supply native requirements.
ENV PATH="/opt/venv/bin:$PATH" \
    PIP_NO_CACHE_DIR=1 \
    HOME=/home/app \
    CHROMA_PERSIST_BASE_DIR=/data/chroma \
    XDG_CACHE_HOME=/home/app/.cache \
    HF_HOME=/home/app/.cache/huggingface \
    SENTENCE_TRANSFORMERS_HOME=/home/app/.cache/sentence-transformers \
    FASTEMBED_CACHE_PATH=/home/app/.cache/fastembed \
    STREAMLIT_BROWSER_GATHER_USAGE_STATS=false
RUN groupadd --gid 10001 app \
    && useradd --uid 10001 --gid 10001 --create-home --home-dir /home/app app \
    && mkdir -p /app/.streamlit /data/chroma /home/app/.cache/huggingface \
        /home/app/.cache/sentence-transformers /home/app/.cache/fastembed \
    && chown -R 10001:10001 /data /home/app
COPY --from=build /opt/venv /opt/venv
COPY .streamlit/config.toml /app/.streamlit/config.toml
WORKDIR /app
USER 10001:10001
EXPOSE 8501
STOPSIGNAL SIGTERM
HEALTHCHECK --interval=10s --timeout=5s --start-period=30s --retries=6 \
    CMD ["python", "-c", "import urllib.request; r = urllib.request.urlopen('http://127.0.0.1:8501/_stcore/health', timeout=3); assert r.status == 200 and r.read(16) == b'ok'"]
CMD ["intellectaengine", "--server.address=0.0.0.0", "--server.port=8501", "--server.headless=true"]
