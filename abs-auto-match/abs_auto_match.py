#!/usr/bin/env python3
"""
Scans ABS libraries for items missing an ASIN/ISBN and runs quickmatch on them.

Incremental mode (default, hourly timer): only items added since last run.
Full mode (--full): entire library. Optionally scoped with --library.

Usage:
  abs_auto_match.py                              # incremental, both libraries
  abs_auto_match.py --full                       # full run, both libraries
  abs_auto_match.py --full --library audiobooks  # full run, audiobooks only
  abs_auto_match.py --full --library ebooks      # full run, ebooks only
"""
import argparse
import json
import os
import requests
import time
from datetime import datetime, timezone

ABS_HOST            = os.environ["ABS_HOST"]
ABS_TOKEN           = os.environ["ABS_TOKEN"]
AUDIOBOOKS_LIB_ID   = os.environ["AUDIOBOOKS_LIBRARY_ID"]
EBOOKS_LIB_ID       = os.environ["EBOOKS_LIBRARY_ID"]
STATE_FILE          = os.environ.get("STATE_FILE", "/var/lib/abs-tools/auto-match-state.json")
BATCH_SIZE          = int(os.environ.get("AUTOMATCH_BATCH_SIZE", "25"))
BATCH_DELAY         = float(os.environ.get("AUTOMATCH_BATCH_DELAY", "10"))

HEADERS = {"Authorization": f"Bearer {ABS_TOKEN}"}
LIBRARIES = {"audiobooks": AUDIOBOOKS_LIB_ID, "ebooks": EBOOKS_LIB_ID}

LIBRARY_PROVIDERS = {
    "audiobooks": os.environ.get("AUTOMATCH_PROVIDER_AUDIOBOOKS"),
    "ebooks":     os.environ.get("AUTOMATCH_PROVIDER_EBOOKS"),
}


def log(msg):
    ts = datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M:%S UTC")
    print(f"[{ts}] {msg}", flush=True)


def load_state():
    try:
        with open(STATE_FILE) as f:
            return json.load(f)
    except (FileNotFoundError, json.JSONDecodeError):
        return {}


def save_state(state):
    os.makedirs(os.path.dirname(STATE_FILE), exist_ok=True)
    with open(STATE_FILE, "w") as f:
        json.dump(state, f, indent=2)


def get_items(library_id, since_ms=None):
    resp = requests.get(
        f"{ABS_HOST}/api/libraries/{library_id}/items",
        headers=HEADERS,
        params={"sort": "addedAt", "desc": "0"},
        timeout=30,
    )
    resp.raise_for_status()
    items = resp.json().get("results", [])
    if since_ms is not None:
        items = [i for i in items if i.get("addedAt", 0) > since_ms]
    return items


def filter_missing_identifiers(items):
    def needs_match(item):
        meta = item.get("media", {}).get("metadata", {})
        return not meta.get("asin") and not meta.get("isbn")
    return [i for i in items if needs_match(i)]


def quickmatch(item_ids, library_name):
    provider = LIBRARY_PROVIDERS.get(library_name)
    options = {"provider": provider} if provider else {}
    resp = requests.post(
        f"{ABS_HOST}/api/items/batch/quickmatch",
        headers=HEADERS,
        json={"options": options, "libraryItemIds": item_ids},
        timeout=60,
    )
    resp.raise_for_status()
    if not resp.content or not resp.content.strip():
        return {}
    try:
        return resp.json()
    except ValueError:
        log(f"Quickmatch unexpected response ({resp.status_code}): {resp.text[:300]}")
        return {}


def process_library(name, library_id, full, state):
    log(f"--- {name} ({'full' if full else 'incremental'}) ---")

    since_ms = None if full else state.get(name, {}).get("last_added_at")
    if since_ms:
        log(f"Checking items added after epoch ms {since_ms}")

    items = get_items(library_id, since_ms=since_ms)
    log(f"{len(items)} item(s) to check")

    to_match = filter_missing_identifiers(items)
    log(f"{len(to_match)} missing ASIN and ISBN")

    if to_match:
        for i in to_match:
            title = i.get("media", {}).get("metadata", {}).get("title", i["id"])
            log(f"  Queuing: {title}")
        ids = [i["id"] for i in to_match]
        batches = [ids[i:i + BATCH_SIZE] for i in range(0, len(ids), BATCH_SIZE)]
        for idx, batch in enumerate(batches):
            if idx > 0:
                log(f"Waiting {BATCH_DELAY}s before next batch...")
                time.sleep(BATCH_DELAY)
            log(f"Batch {idx + 1}/{len(batches)} ({len(batch)} items)")
            quickmatch(batch, name)
    else:
        log("Nothing to match")

    max_added_at = (
        max(i.get("addedAt", 0) for i in items)
        if items
        else state.get(name, {}).get("last_added_at")
    )
    return {
        "last_check": datetime.now(timezone.utc).isoformat(),
        "last_added_at": max_added_at,
    }


def main():
    parser = argparse.ArgumentParser(description="Auto-match ABS items missing ASIN")
    parser.add_argument("--full", action="store_true",
                        help="Process entire library instead of only new items")
    parser.add_argument("--library", choices=["audiobooks", "ebooks", "all"], default="all",
                        help="Library to process (default: all)")
    args = parser.parse_args()

    if args.library == "all":
        targets = LIBRARIES
    else:
        targets = {args.library: LIBRARIES[args.library]}

    state = load_state()
    for name, library_id in targets.items():
        try:
            state[name] = process_library(name, library_id, args.full, state)
        except Exception as e:
            log(f"ERROR processing {name}: {e}")
    save_state(state)


if __name__ == "__main__":
    main()
