FROM debian:bookworm-slim

# renovate: datasource=github-releases depName=aptible/supercronic
ARG SUPERCRONIC_VERSION=0.2.33

RUN apt-get update && apt-get install -y --no-install-recommends \
    calibre \
    curl \
    python3 \
    unzip \
    && curl -fsSL "https://github.com/aptible/supercronic/releases/download/v${SUPERCRONIC_VERSION}/supercronic-linux-amd64" \
        -o /usr/local/bin/supercronic \
    && chmod +x /usr/local/bin/supercronic \
    && rm -rf /var/lib/apt/lists/*

COPY epub-convert/epubv3.sh /scripts/epubv3.sh
COPY docker/epub/entrypoint.sh /scripts/entrypoint.sh
COPY docker/epub/crontab /etc/crontab

RUN chmod +x /scripts/epubv3.sh /scripts/entrypoint.sh && \
    mkdir -p /var/log/abs-tools /var/lib/abs-tools

ENTRYPOINT ["/scripts/entrypoint.sh"]
