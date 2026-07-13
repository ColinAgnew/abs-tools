#!/bin/sh
set -e
if [ $# -eq 0 ]; then
    exec supercronic /etc/crontab
fi
cmd="$1"; shift
case "$cmd" in
    abs-auto-match)    exec python3 /scripts/abs_auto_match.py "$@" ;;
    abs-chapter-match) exec python3 /scripts/quick_match_chapters.py "$@" ;;
    *)                 exec "$cmd" "$@" ;;
esac
