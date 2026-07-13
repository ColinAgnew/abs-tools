#!/usr/bin/env python3
"""
Cron-like scheduler for abs-tools. Reads schedules and enable flags from
environment variables, runs jobs on schedule, and outputs to both stdout
(Docker logs) and per-tool log files.
"""
import os
import subprocess
import sys
import threading
import time
from datetime import datetime, timezone

LOG_LEVEL = os.environ.get("LOG_LEVEL", "INFO").upper()
_LEVELS = {"DEBUG": 0, "INFO": 1, "WARN": 2, "ERROR": 3}


def log(msg, level="INFO"):
    if _LEVELS.get(level, 1) >= _LEVELS.get(LOG_LEVEL, 1):
        ts = datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M:%S UTC")
        print(f"[scheduler] [{level}] {ts} {msg}", flush=True)


def field_matches(field, value):
    if field == "*":
        return True
    try:
        return int(field) == value
    except ValueError:
        return False


def cron_matches(expr, now):
    try:
        minute, hour, dom, month, dow = expr.split()
    except ValueError:
        return False
    cron_dow = (now.weekday() + 1) % 7  # Python 0=Mon → cron 0=Sun
    return (
        field_matches(minute, now.minute)
        and field_matches(hour, now.hour)
        and field_matches(dom, now.day)
        and field_matches(month, now.month)
        and field_matches(dow, cron_dow)
    )


def run_job(name, cmd):
    log_file = f"/var/log/abs-tools/{name}.log"
    env = os.environ.copy()
    env["PYTHONUNBUFFERED"] = "1"
    try:
        with subprocess.Popen(
            cmd, stdout=subprocess.PIPE, stderr=subprocess.STDOUT, text=True, env=env
        ) as proc:
            with open(log_file, "a") as f:
                for line in proc.stdout:
                    line = line.rstrip("\n")
                    out = f"[{name}] {line}"
                    print(out, flush=True)
                    f.write(out + "\n")
                    f.flush()
        log(f"{name} finished (exit {proc.returncode})")
    except Exception as e:
        log(f"{name} error: {e}", level="ERROR")


_running = set()
_lock = threading.Lock()


def run_job_async(name, cmd):
    key = f"{name}:{' '.join(cmd)}"
    with _lock:
        if key in _running:
            log(f"Skipping {name} — previous run still in progress", level="WARN")
            return
        _running.add(key)

    def worker():
        try:
            run_job(name, cmd)
        finally:
            with _lock:
                _running.discard(key)

    threading.Thread(target=worker, daemon=True).start()


def main():
    os.makedirs("/var/log/abs-tools", exist_ok=True)
    os.makedirs("/var/lib/abs-tools", exist_ok=True)

    jobs = []

    log("=== abs-tools starting ===")

    if os.environ.get("ENABLE_AUTO_MATCH", "true").lower() == "true":
        schedule = os.environ.get("SCHEDULE_AUTO_MATCH", "0 * * * *")
        jobs.append((schedule, "abs-auto-match", ["python3", "/scripts/abs_auto_match.py"]))
        log(f"[+] abs-auto-match enabled (schedule: {schedule})")
    else:
        log("[-] abs-auto-match disabled")

    if os.environ.get("ENABLE_CHAPTER_MATCH", "true").lower() == "true":
        schedule = os.environ.get("SCHEDULE_CHAPTER_MATCH", "5 * * * *")
        jobs.append((schedule, "abs-chapter-match", ["python3", "/scripts/quick_match_chapters.py"]))
        log(f"[+] abs-chapter-match enabled (schedule: {schedule})")
    else:
        log("[-] abs-chapter-match disabled")

    if os.environ.get("ENABLE_EPUB_CONVERT", "true").lower() == "true":
        schedule = os.environ.get("SCHEDULE_EPUB_CONVERT", "10 * * * *")
        schedule_full = os.environ.get("SCHEDULE_EPUB_CONVERT_FULL", "30 2 * * 0")
        jobs.append((schedule, "epub-convert", ["/scripts/epubv3.sh"]))
        jobs.append((schedule_full, "epub-convert-full", ["/scripts/epubv3.sh", "--full"]))
        log(f"[+] epub-convert enabled (incremental: {schedule}, full: {schedule_full})")
    else:
        log("[-] epub-convert disabled")

    if not jobs:
        log("No jobs enabled. Exiting.", level="ERROR")
        sys.exit(1)

    log("=== Scheduler running ===")

    triggered = set()

    while True:
        now = datetime.now(timezone.utc)
        minute_key = now.strftime("%Y%m%d%H%M")

        for schedule, name, cmd in jobs:
            key = f"{name}:{minute_key}"
            if key not in triggered and cron_matches(schedule, now):
                triggered.add(key)
                if len(triggered) > 1000:
                    triggered.clear()
                run_job_async(name, cmd)

        now = datetime.now(timezone.utc)
        time.sleep(60 - now.second - now.microsecond / 1_000_000)


if __name__ == "__main__":
    main()
