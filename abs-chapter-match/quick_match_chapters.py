#!/usr/bin/env python3
"""
Matches chapters for audiobooks in ABS using Audnexus via the ABS API.

Incremental mode (default, hourly timer): only items added since last run.
Full mode (--full): entire audiobooks library.

Handle with care: if chapters are manually set, they can be overwritten
if the found count differs from the local count by more than CHAPTER_THRESHOLD.
"""
import argparse
import json
import os
import time
import requests
from datetime import datetime, timezone
from urllib import parse

ABS_HOST            = os.environ["ABS_HOST"]
ABS_TOKEN           = os.environ["ABS_TOKEN"]
AUDIOBOOKS_LIB_ID   = os.environ["AUDIOBOOKS_LIBRARY_ID"]
CHAPTER_THRESHOLD   = int(os.environ.get("CHAPTER_THRESHOLD", "3"))
PROVIDER            = os.environ.get("CHAPTER_PROVIDER", "audible.com")
REGION              = os.environ.get("CHAPTER_REGION", "US")
DISABLE_RATE_PROTECTION = os.environ.get("DISABLE_RATE_PROTECTION", "false").lower() == "true"
SEARCH_FOR_ASIN     = os.environ.get("SEARCH_FOR_ASIN", "true").lower() == "true"
USE_TRACKS_AS_CHAPTERS = os.environ.get("USE_TRACKS_AS_CHAPTERS", "false").lower() == "true"
STATE_FILE          = os.environ.get("STATE_FILE", "/var/lib/abs-tools/chapter-match-state.json")
LOG_LEVEL           = os.environ.get("LOG_LEVEL", "INFO").upper()

_LEVELS = {"DEBUG": 0, "INFO": 1, "WARN": 2, "ERROR": 3}

HEADERS = {"Authorization": f"Bearer {ABS_TOKEN}"}


def log(msg, level="INFO"):
    if _LEVELS.get(level, 1) >= _LEVELS.get(LOG_LEVEL, 1):
        ts = datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M:%S UTC")
        print(f"[{ts}] [{level}] {msg}", flush=True)


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


def get_library_items(since_ms=None):
    resp = requests.get(
        f"{ABS_HOST}/api/libraries/{AUDIOBOOKS_LIB_ID}/items",
        headers=HEADERS,
        params={"sort": "addedAt", "desc": "0"},
        timeout=15,
    )
    if resp.status_code != 200:
        log(f"Error fetching library items: {resp.status_code}", level="ERROR")
        return []
    items = resp.json().get("results", [])
    if since_ms is not None:
        items = [i for i in items if i.get("addedAt", 0) > since_ms]
    return items


def match_book(item):
    book_id = item["id"]
    metadata = item["media"]["metadata"]
    title = metadata.get("title", "Unknown Title")
    authors = metadata.get("authorName", "Unknown Author")
    result = {"id": book_id, "title": title, "status": "ERROR", "comment": "Unknown Error", "asin": "N/A"}

    log(f"Processing: {title}", level="DEBUG")

    # Resolve ASIN
    if not metadata.get("asin"):
        result["status"] = "NO_ASIN"
        if SEARCH_FOR_ASIN:
            search_resp = requests.get(
                f"{ABS_HOST}/api/search/books",
                headers=HEADERS,
                params={"title": title, "author": authors, "provider": PROVIDER},
                timeout=15,
            )
            if search_resp.status_code != 200 or not search_resp.json():
                log(f"ASIN search failed for '{title}'", level="WARN")
                result["comment"] = "ASIN retrieval failed"
                return result
            asin = search_resp.json()[0].get("asin")
            if not asin:
                log(f"No ASIN in search results for '{title}'", level="WARN")
                result["comment"] = "ASIN retrieval failed - no ASIN in results"
                return result
            item["media"]["metadata"]["asin"] = asin
            metadata["asin"] = asin
            log(f"ASIN found via search: {asin} for '{title}'")

    # Still no ASIN after search — try tracks as chapters fallback
    if not metadata.get("asin"):
        if not USE_TRACKS_AS_CHAPTERS:
            log(f"Skipping '{title}' — no ASIN and tracks fallback disabled")
            result["comment"] = "ASIN retrieval failed"
            return result

        book_resp = requests.get(
            f"{ABS_HOST}/api/items/{book_id}?expanded=1",
            headers=HEADERS,
            timeout=15,
        )
        result["status"] = "TRACKS"
        if book_resp.status_code != 200:
            result["comment"] = "Tracks retrieval failed"
            return result

        tracks = book_resp.json()["media"].get("audioFiles", [])
        if len(tracks) <= 1:
            log(f"Not enough tracks for '{title}'", level="DEBUG")
            result["comment"] = "Tracks retrieval failed"
            return result

        current_chapters_num = item["media"].get("numChapters", 0)
        if current_chapters_num != 0 and abs(current_chapters_num - len(tracks)) <= CHAPTER_THRESHOLD:
            log(f"Chapters already correct for '{title}'", level="DEBUG")
            result["status"] = "FINISHED"
            result["comment"] = "No chapters to update"
            return result

        log(f"Using tracks as chapters for '{title}' ({len(tracks)} tracks)")
        current_time = 0
        length_of_book = item["media"]["duration"]
        new_chapters = []
        for i, track in enumerate(tracks):
            duration = track["duration"]
            track_title = track["metadata"]["filename"].rsplit(".", 1)[0]
            new_chapters.append({"id": i, "start": current_time,
                                  "end": current_time + duration, "title": track_title, "error": None})
            current_time += duration - 0.001
            if current_time >= length_of_book:
                break

        update_resp = requests.post(
            f"{ABS_HOST}/api/items/{book_id}/chapters",
            headers=HEADERS,
            json={"chapters": new_chapters},
            timeout=15,
        )
        if update_resp.status_code == 200:
            result["status"] = "FINISHED"
            result["comment"] = "Tracks used as chapters"
        else:
            result["comment"] = "Chapters update failed"
        return result

    result["asin"] = metadata["asin"]

    # Fetch chapters via ASIN
    chapter_resp = requests.get(
        f"{ABS_HOST}/api/search/chapters",
        headers=HEADERS,
        params={"asin": metadata["asin"], "region": REGION},
        timeout=15,
    )
    if chapter_resp.status_code != 200 or chapter_resp.json().get("error"):
        log(f"Error fetching chapters for '{title}': {chapter_resp.status_code}", level="ERROR")
        result["comment"] = "Chapters retrieval failed"
        return result

    chapters = chapter_resp.json().get("chapters", [])
    if not chapters:
        log(f"No chapters found for '{title}'")
        result["comment"] = "No chapters found"
        return result

    log(f"Found {len(chapters)} chapters for '{title}'", level="DEBUG")
    current_chapters_num = item["media"].get("numChapters", 0)

    if current_chapters_num != 0 and abs(current_chapters_num - len(chapters)) <= CHAPTER_THRESHOLD:
        log(f"Chapters already correct for '{title}'", level="DEBUG")
        result["status"] = "FINISHED"
        result["comment"] = "No chapters to update"
        return result

    log(f"Updating chapters for '{title}' (current: {current_chapters_num}, found: {len(chapters)})")
    length_of_book = item["media"]["duration"]
    new_chapters = []
    for i, chapter in enumerate(chapters):
        start = chapter["startOffsetMs"] / 1000
        if start >= length_of_book:
            break
        end = min((chapter["startOffsetMs"] + chapter["lengthMs"]) / 1000, length_of_book)
        new_chapters.append({"id": i, "start": start, "end": end, "title": chapter["title"], "error": None})

    update_resp = requests.post(
        f"{ABS_HOST}/api/items/{book_id}/chapters",
        headers=HEADERS,
        json={"chapters": new_chapters},
        timeout=15,
    )
    if update_resp.status_code == 200:
        result["status"] = "FINISHED"
        result["comment"] = "Chapters updated"
        log(f"Chapters updated for '{title}'")
    else:
        result["comment"] = "Chapters update failed"
        log(f"Failed to update chapters for '{title}': {update_resp.status_code}", level="ERROR")

    return result


def main():
    parser = argparse.ArgumentParser(description="Match audiobook chapters via Audnexus")
    parser.add_argument("--full", action="store_true",
                        help="Process entire library instead of only new items")
    args = parser.parse_args()

    state = load_state()
    since_ms = None if args.full else state.get("last_added_at")
    if since_ms:
        log(f"Incremental run: checking items added after epoch ms {since_ms}", level="DEBUG")
    else:
        log("Full run: processing entire audiobooks library")

    items = get_library_items(since_ms=since_ms)
    log(f"Found {len(items)} item(s) to process")

    book_info = {}
    for item in items:
        book_info[item["id"]] = match_book(item)
        if not DISABLE_RATE_PROTECTION:
            time.sleep(2)

    max_added_at = max((i.get("addedAt", 0) for i in items), default=state.get("last_added_at"))
    state["last_added_at"] = max_added_at
    state["last_check"] = datetime.now(timezone.utc).isoformat()
    save_state(state)

    log("--- Summary ---")
    for info in book_info.values():
        log(f"  {info['status']}: {info['title']} — {info['comment']}")

    failed = [v for v in book_info.values() if v["status"] not in ("FINISHED",)]
    if failed:
        log(f"{len(failed)} item(s) did not finish successfully", level="WARN")


if __name__ == "__main__":
    main()
