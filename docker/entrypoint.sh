#!/bin/bash
set -e

mkdir -p /var/log/abs-tools /var/lib/abs-tools

CRONTAB_FILE="/tmp/abs-tools-crontab"
> "$CRONTAB_FILE"

echo "=== abs-tools starting ==="

if [ "${ENABLE_AUTO_MATCH:-true}" = "true" ]; then
    schedule="${SCHEDULE_AUTO_MATCH:-0 * * * *}"
    echo "$schedule /scripts/run_job.sh abs-auto-match python3 /scripts/abs_auto_match.py" >> "$CRONTAB_FILE"
    echo "[+] abs-auto-match enabled (schedule: $schedule)"
else
    echo "[-] abs-auto-match disabled"
fi

if [ "${ENABLE_CHAPTER_MATCH:-true}" = "true" ]; then
    schedule="${SCHEDULE_CHAPTER_MATCH:-5 * * * *}"
    echo "$schedule /scripts/run_job.sh abs-chapter-match python3 /scripts/quick_match_chapters.py" >> "$CRONTAB_FILE"
    echo "[+] abs-chapter-match enabled (schedule: $schedule)"
else
    echo "[-] abs-chapter-match disabled"
fi

if [ "${ENABLE_EPUB_CONVERT:-true}" = "true" ]; then
    schedule="${SCHEDULE_EPUB_CONVERT:-10 * * * *}"
    schedule_full="${SCHEDULE_EPUB_CONVERT_FULL:-30 2 * * 0}"
    echo "$schedule /scripts/run_job.sh epub-convert /scripts/epubv3.sh" >> "$CRONTAB_FILE"
    echo "$schedule_full /scripts/run_job.sh epub-convert /scripts/epubv3.sh --full" >> "$CRONTAB_FILE"
    echo "[+] epub-convert enabled (incremental: $schedule, full: $schedule_full)"
else
    echo "[-] epub-convert disabled"
fi

echo "=== Scheduler starting ==="
exec supercronic "$CRONTAB_FILE"
