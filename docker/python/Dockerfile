FROM python:3.12-slim

RUN pip install --no-cache-dir requests

WORKDIR /scripts

COPY abs-auto-match/abs_auto_match.py ./abs_auto_match.py
COPY abs-chapter-match/quick_match_chapters.py ./quick_match_chapters.py
COPY docker/python/entrypoint.sh ./entrypoint.sh

RUN chmod +x entrypoint.sh && \
    mkdir -p /var/log/abs-tools /var/lib/abs-tools

ENTRYPOINT ["./entrypoint.sh"]
