FROM debian:bookworm-slim

RUN apt-get update && apt-get install -y --no-install-recommends \
    calibre \
    curl \
    python3 \
    unzip \
    && rm -rf /var/lib/apt/lists/*

COPY epub-convert/epubv3.sh /scripts/epubv3.sh

RUN chmod +x /scripts/epubv3.sh && \
    mkdir -p /var/log/abs-tools /var/lib/abs-tools

ENTRYPOINT ["/scripts/epubv3.sh"]
