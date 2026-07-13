FROM python:3.12-slim

# renovate: datasource=github-releases depName=aptible/supercronic
ARG SUPERCRONIC_VERSION=0.2.33

RUN pip install --no-cache-dir requests && \
    apt-get update && apt-get install -y --no-install-recommends curl && \
    curl -fsSL "https://github.com/aptible/supercronic/releases/download/v${SUPERCRONIC_VERSION}/supercronic-linux-amd64" \
        -o /usr/local/bin/supercronic && \
    chmod +x /usr/local/bin/supercronic && \
    apt-get purge -y curl && apt-get autoremove -y && rm -rf /var/lib/apt/lists/*

WORKDIR /scripts

COPY abs-auto-match/abs_auto_match.py ./abs_auto_match.py
COPY abs-chapter-match/quick_match_chapters.py ./quick_match_chapters.py
COPY docker/python/entrypoint.sh ./entrypoint.sh
COPY docker/python/crontab /etc/crontab

RUN chmod +x entrypoint.sh && \
    mkdir -p /var/log/abs-tools /var/lib/abs-tools

ENTRYPOINT ["./entrypoint.sh"]
