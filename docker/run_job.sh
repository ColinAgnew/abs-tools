#!/bin/bash
# Runs a script and sends output to both Docker logs (stdout) and a log file.
LOG_NAME="$1"; shift
LOG_FILE="/var/log/abs-tools/${LOG_NAME}.log"
"$@" 2>&1 | tee -a "$LOG_FILE"
exit "${PIPESTATUS[0]}"
