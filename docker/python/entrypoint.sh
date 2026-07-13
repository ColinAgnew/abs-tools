#!/bin/sh
set -e
cmd="$1"; shift
case "$cmd" in
    abs-auto-match)    exec python3 /scripts/abs_auto_match.py "$@" ;;
    abs-chapter-match) exec python3 /scripts/quick_match_chapters.py "$@" ;;
    *) echo "Unknown command: $cmd. Valid: abs-auto-match, abs-chapter-match" >&2; exit 1 ;;
esac
