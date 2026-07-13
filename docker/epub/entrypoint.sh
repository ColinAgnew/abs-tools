#!/bin/sh
set -e
if [ $# -eq 0 ]; then
    exec supercronic /etc/crontab
fi
exec /scripts/epubv3.sh "$@"
