FROM debian:bookworm-slim

# renovate: datasource=github-releases depName=aptible/supercronic
ARG SUPERCRONIC_VERSION=0.2.33

RUN apt-get update && apt-get install -y --no-install-recommends \
    calibre \
    curl \
    python3 \
    python3-requests \
    unzip \
    && curl -fsSL "https://github.com/aptible/supercronic/releases/download/v${SUPERCRONIC_VERSION}/supercronic-linux-amd64" \
        -o /usr/local/bin/supercronic \
    && chmod +x /usr/local/bin/supercronic \
    && rm -rf /var/lib/apt/lists/* \
    && mkdir -p /var/log/abs-tools /var/lib/abs-tools

COPY abs-auto-match/abs_auto_match.py /scripts/
COPY abs-chapter-match/quick_match_chapters.py /scripts/
COPY epub-convert/epubv3.sh /scripts/
COPY docker/run_job.sh /scripts/run_job.sh
COPY docker/entrypoint.sh /scripts/entrypoint.sh

RUN chmod +x /scripts/epubv3.sh /scripts/run_job.sh /scripts/entrypoint.sh

ENTRYPOINT ["/scripts/entrypoint.sh"]
