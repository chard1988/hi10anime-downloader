FROM docker.io/library/python:3.15-slim@sha256:65a65fc7b30b06cb6df4930fd4650697cb23f4c2698ab81fc87e4b031bc36928

ARG VERSION=0.3.0-beta.2
ARG VCS_REF=uncommitted
LABEL org.opencontainers.image.title="Hi10 Download Manager" \
      org.opencontainers.image.description="Testing-beta project scanner and download queue" \
      org.opencontainers.image.version=$VERSION \
      org.opencontainers.image.revision=$VCS_REF \
      org.opencontainers.image.licenses="MIT"
ENV PYTHONUNBUFFERED=1 \
    PYTHONDONTWRITEBYTECODE=1 \
    PIP_NO_CACHE_DIR=1 \
    PLAYWRIGHT_BROWSERS_PATH=/opt/playwright \
    HOME=/tmp/hi10-home \
    HI10_CONFIG_DIR=/config \
    HI10_DOWNLOAD_DIR=/downloads
WORKDIR /app
COPY requirements.lock ./
RUN pip install --require-hashes -r requirements.lock \
    && python -m playwright install --with-deps chromium \
    && chmod -R a+rX /opt/playwright \
    && mkdir -p /config /downloads /tmp/hi10-home \
    && chown 99:100 /config /downloads /tmp/hi10-home \
    && rm -rf /var/lib/apt/lists/*
ARG SOURCE_URL=https://github.com/chard1988/hi10anime-downloader
LABEL org.opencontainers.image.source=$SOURCE_URL
# Pick up security fixes released after the pinned base/browser layers.
RUN apt-get update && apt-get upgrade -y --no-install-recommends \
    && rm -rf /var/lib/apt/lists/*
COPY pyproject.toml README.md LICENSE ./
COPY src ./src
RUN pip install --no-deps --no-build-isolation .
USER 99:100
VOLUME ["/config", "/downloads"]
EXPOSE 8080
STOPSIGNAL SIGTERM
HEALTHCHECK --interval=30s --timeout=5s --start-period=20s --retries=3 CMD python -c "import os,urllib.request; urllib.request.urlopen('http://127.0.0.1:'+os.environ.get('HI10_WEB_PORT','8080')+'/healthz',timeout=3)"
CMD ["python", "-m", "hi10_downloader.web"]
