FROM debian:bookworm-slim

RUN apt-get update && apt-get install -y --no-install-recommends \
    calibre \
    curl \
    python3 \
    python3-requests \
    unzip \
    && rm -rf /var/lib/apt/lists/* \
    && mkdir -p /var/log/abs-tools /var/lib/abs-tools \
    && chown -R 1000:1000 /var/log/abs-tools /var/lib/abs-tools

COPY abs-auto-match/abs_auto_match.py /scripts/
COPY abs-chapter-match/quick_match_chapters.py /scripts/
COPY epub-convert/epubv3.sh /scripts/
COPY docker/scheduler.py /scripts/scheduler.py

RUN chmod +x /scripts/epubv3.sh

USER 1000:1000

ENTRYPOINT ["python3", "/scripts/scheduler.py"]
