#!/usr/bin/env python3
"""
Scans ABS libraries for items missing an ASIN/ISBN and runs quickmatch on them.

Incremental mode (default, hourly timer): only items added since last run.
Full mode (--full): entire library. Optionally scoped with --library.

Usage:
  abs_auto_match.py                                  # incremental, both libraries
  abs_auto_match.py --full                           # full run, both libraries
  abs_auto_match.py --full --library audiobooks      # full run, audiobooks only
  abs_auto_match.py --full --library ebooks          # full run, ebooks only
  abs_auto_match.py --full --force-covers            # refresh covers on every item, all libraries
"""
import argparse
import json
import os
import re
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
FALLBACK_DELAY      = float(os.environ.get("AUTOMATCH_FALLBACK_DELAY", "60"))
LOG_LEVEL           = os.environ.get("LOG_LEVEL", "INFO").upper()

_LEVELS = {"DEBUG": 0, "INFO": 1, "WARN": 2, "ERROR": 3}

HEADERS = {"Authorization": f"Bearer {ABS_TOKEN}"}
LIBRARIES = {"audiobooks": AUDIOBOOKS_LIB_ID, "ebooks": EBOOKS_LIB_ID}

LIBRARY_PROVIDERS = {
    "audiobooks": {
        "primary":  os.environ.get("AUTOMATCH_PROVIDER_AUDIOBOOKS"),
        "fallback": os.environ.get("AUTOMATCH_PROVIDER_AUDIOBOOKS_FALLBACK"),
    },
    "ebooks": {
        "primary":  os.environ.get("AUTOMATCH_PROVIDER_EBOOKS"),
        "fallback": os.environ.get("AUTOMATCH_PROVIDER_EBOOKS_FALLBACK"),
    },
}

# GraphicAudio items live in their own audiobooks subfolder and need a different
# provider than the rest of the library. Detected primarily by folder path; the
# title tag is a safety net in case a GA item ever lands outside that folder.
GA_PROVIDER    = os.environ.get("AUTOMATCH_PROVIDER_AUDIOBOOKS_GRAPHICAUDIO")
GA_PATH_PREFIX = os.environ.get("AUTOMATCH_GRAPHICAUDIO_PATH_PREFIX", "/path/to/audiobooks/GraphicAudio")
GA_TITLE_RE    = re.compile(r"\[dramati\w*\s*adapt\w*\]", re.IGNORECASE)

# GA titles carry a "(Part X of Y) [Dramatized Adaptation]" suffix that GraphicAudio's
# own catalog doesn't use, so bulk quickmatch (which searches on the stored title
# verbatim) never finds them. Strip it before searching instead. Same regexes and
# disambiguation approach as the one-off abs_match_ga.py cleanup script.
GA_PART_RE     = re.compile(r"\s*\(part\s*\d+\s*of\s*\d+\)\s*", re.IGNORECASE)
GA_PART_NUM_RE = re.compile(r"\(part\s*(\d+)\s*of\s*(\d+)\)", re.IGNORECASE)

# ABS only fills a field when it's currently empty unless overrideDetails is set
# (which we deliberately never set — see quickmatch()). A book with language
# already set to English but an empty description can still pick up a wrong-
# language description on a later match, since the description field itself was
# empty. English-ness is checked on the actual text as a result, not just the
# stored language field. Coarse on purpose: this only needs to catch "clearly
# not English", not classify precisely.
ENGLISH_STOPWORDS = {
    "the", "and", "of", "to", "a", "in", "is", "was", "for", "on", "with", "as",
    "by", "at", "from", "it", "this", "be", "or", "an", "are", "were", "that",
    "his", "her", "he", "she", "they", "their", "not", "but", "has", "have",
    "had", "you", "your", "will", "when", "who", "one", "all", "there", "if",
}


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


def is_graphicaudio_item(item):
    for f in item.get("libraryFiles", []):
        path = f.get("metadata", {}).get("path") or ""
        if path.startswith(GA_PATH_PREFIX):
            return True
    title = item.get("media", {}).get("metadata", {}).get("title") or ""
    return bool(GA_TITLE_RE.search(title))


def ga_search_title(title):
    t = GA_TITLE_RE.sub("", title)
    t = GA_PART_RE.sub(" ", t)
    return re.sub(r"\s+", " ", t).strip(" -")


def ga_part_info(title):
    m = GA_PART_NUM_RE.search(title)
    if not m:
        return None, None
    return int(m.group(1)), int(m.group(2))


def ga_part_from_cover(cover_url):
    if not cover_url:
        return None, None
    m = re.search(r"_(\d+)_of_(\d+)(?:\.\w+)?$", cover_url.rstrip("/"))
    if not m:
        return None, None
    return int(m.group(1)), int(m.group(2))


def ga_disambiguate(title, candidates):
    """Resolve multiple search candidates for a split-part GA title, or return
    None if it can't be resolved cleanly (caller should skip, not guess)."""
    part_num, part_total = ga_part_info(title)
    if part_num is None:
        return None

    cover_matches = [c for c in candidates if ga_part_from_cover(c.get("cover")) == (part_num, part_total)]
    if len(cover_matches) == 1:
        return cover_matches[0]

    if len(candidates) != part_total:
        return None
    years = [c.get("publishedYear") for c in candidates]
    if any(y is None for y in years):
        return None
    try:
        sorted_candidates = sorted(candidates, key=lambda c: int(c["publishedYear"]))
    except (ValueError, TypeError):
        return None
    return sorted_candidates[part_num - 1]


def ga_search(title, author, provider):
    resp = requests.get(
        f"{ABS_HOST}/api/search/books",
        headers=HEADERS,
        params={"title": title, "author": author or "", "provider": provider},
        timeout=30,
    )
    resp.raise_for_status()
    raw = resp.json()
    if isinstance(raw, list):
        return raw
    if isinstance(raw, dict):
        for key in ("matches", "results", "books"):
            if key in raw and isinstance(raw[key], list):
                return raw[key]
    log(f"GraphicAudio search: unrecognized response shape: {json.dumps(raw)[:300]}", level="WARN")
    return []


def ga_patch_identifiers(item_id, candidate):
    metadata = {}
    if candidate.get("asin"):
        metadata["asin"] = candidate["asin"]
    if candidate.get("isbn"):
        metadata["isbn"] = candidate["isbn"]
    if not metadata:
        return None
    resp = requests.patch(
        f"{ABS_HOST}/api/items/{item_id}/media",
        headers=HEADERS,
        json={"metadata": metadata},
        timeout=30,
    )
    resp.raise_for_status()
    return metadata


def ga_apply_cover(item_id, cover_url):
    resp = requests.post(
        f"{ABS_HOST}/api/items/{item_id}/cover",
        headers=HEADERS,
        json={"url": cover_url},
        timeout=30,
    )
    resp.raise_for_status()


def match_graphicaudio_items(items, provider, apply_identifiers=True):
    """apply_identifiers=False is used by --force-covers: re-search purely to
    find the cover URL, without touching identifiers that are already correct."""
    for idx, item in enumerate(items):
        if idx > 0:
            time.sleep(2)

        meta = item.get("media", {}).get("metadata", {})
        title = meta.get("title", item["id"])
        author = meta.get("authorName", "")
        search_title = ga_search_title(title)

        log(f"  Searching (GraphicAudio): '{search_title}'", level="DEBUG")
        try:
            candidates = ga_search(search_title, author, provider)
        except requests.RequestException as e:
            log(f"  GraphicAudio search failed for '{title}': {e}", level="WARN")
            continue

        if not candidates:
            log(f"  No GraphicAudio results for '{title}' — skipping", level="WARN")
            continue

        if len(candidates) == 1:
            chosen = candidates[0]
        else:
            chosen = ga_disambiguate(title, candidates)
            if chosen is None:
                log(f"  {len(candidates)} ambiguous GraphicAudio results for '{title}' — "
                    f"skipping (run abs_match_ga.py manually)", level="WARN")
                continue

        applied_identifiers = None
        if apply_identifiers:
            try:
                applied_identifiers = ga_patch_identifiers(item["id"], chosen)
            except requests.RequestException as e:
                log(f"  GraphicAudio metadata update failed for '{title}': {e}", level="ERROR")
                continue
            if not applied_identifiers:
                log(f"  GraphicAudio match for '{title}' had no ASIN/ISBN", level="WARN")

        cover_url = chosen.get("cover")
        cover_applied = False
        if cover_url:
            try:
                ga_apply_cover(item["id"], cover_url)
                cover_applied = True
            except requests.RequestException as e:
                log(f"  GraphicAudio cover update failed for '{title}': {e}", level="WARN")

        if applied_identifiers or cover_applied:
            parts = []
            if applied_identifiers:
                parts.append(str(applied_identifiers))
            if cover_applied:
                parts.append("cover")
            log(f"  Matched (GraphicAudio): '{title}' -> {' + '.join(parts)}")


def looks_english(text, min_words=8, min_ratio=0.08):
    """Coarse, dependency-free English check: what fraction of words are common
    English function words. Too-short text is treated as inconclusive (True) to
    avoid false positives rather than trying to be precise."""
    words = re.findall(r"[a-zA-Z']+", text.lower())
    if len(words) < min_words:
        return True
    hits = sum(1 for w in words if w in ENGLISH_STOPWORDS)
    return (hits / len(words)) >= min_ratio


def audit_matched_items(items_by_id):
    for item_id, item in items_by_id.items():
        meta = item.get("media", {}).get("metadata", {})
        title = meta.get("title", item_id)
        language = (meta.get("language") or "").strip()
        description = meta.get("description") or ""

        if language and language.lower() != "english":
            log(f"  Language check: '{title}' matched with language='{language}' — review manually", level="WARN")
        elif description and not looks_english(description):
            log(f"  Language check: '{title}' has language='{language or 'unset'}' but the description "
                f"doesn't look English — review manually", level="WARN")


def quickmatch(item_ids, provider=None):
    # overrideCover always on: any time we match an item, take the provider's
    # cover. overrideDetails deliberately left off so we never clobber fields
    # (description, genres, etc.) that are already set.
    options = {"overrideCover": True}
    if provider:
        options["provider"] = provider
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
        log(f"Quickmatch unexpected response ({resp.status_code}): {resp.text[:300]}", level="WARN")
        return {}


def run_batches(ids, provider, label):
    batches = [ids[i:i + BATCH_SIZE] for i in range(0, len(ids), BATCH_SIZE)]
    for idx, batch in enumerate(batches):
        if idx > 0:
            log(f"Waiting {BATCH_DELAY}s before next batch...", level="DEBUG")
            time.sleep(BATCH_DELAY)
        log(f"{label} batch {idx + 1}/{len(batches)} ({len(batch)} items)")
        quickmatch(batch, provider)


def process_library(name, library_id, full, state, force_covers=False):
    mode = "full" if full else "incremental"
    if force_covers:
        mode += ", force-covers"
    log(f"--- {name} ({mode}) ---")

    providers = LIBRARY_PROVIDERS[name]
    primary  = providers["primary"]
    fallback = providers["fallback"]

    since_ms = None if full else state.get(name, {}).get("last_added_at")
    if since_ms:
        log(f"Checking items added after epoch ms {since_ms}", level="DEBUG")

    items = get_items(library_id, since_ms=since_ms)
    log(f"{len(items)} item(s) to check")

    if force_covers:
        # Ignore identifier status entirely — every item gets re-submitted so its
        # cover is refreshed. overrideDetails is never set, so already-correct
        # identifiers/description/etc. are left alone; only the cover is forced.
        to_match = list(items)
        log(f"{len(to_match)} item(s) — refreshing covers regardless of identifier status")
    else:
        to_match = filter_missing_identifiers(items)
        log(f"{len(to_match)} missing ASIN and ISBN")

    touched_ids = set()

    if name == "audiobooks" and GA_PROVIDER:
        ga_items = [i for i in to_match if is_graphicaudio_item(i)]
        to_match = [i for i in to_match if i not in ga_items]

        if ga_items:
            log(f"{len(ga_items)} GraphicAudio item(s) — searching '{GA_PROVIDER}' individually "
                f"(title-tag/part-suffix stripped before search)")
            match_graphicaudio_items(ga_items, GA_PROVIDER, apply_identifiers=not force_covers)
            touched_ids.update(i["id"] for i in ga_items)

    if to_match:
        for i in to_match:
            title = i.get("media", {}).get("metadata", {}).get("title", i["id"])
            log(f"  Queuing: {title}", level="DEBUG")

        run_batches([i["id"] for i in to_match], primary, "Primary")
        touched_ids.update(i["id"] for i in to_match)

        if fallback and not force_covers:
            log(f"Waiting {FALLBACK_DELAY}s for ABS to finish primary pass...")
            time.sleep(FALLBACK_DELAY)

            refreshed = get_items(library_id, since_ms=since_ms)
            original_ids = {i["id"] for i in to_match}
            still_missing = [i for i in filter_missing_identifiers(refreshed) if i["id"] in original_ids]

            if still_missing:
                log(f"{len(still_missing)} still missing after primary pass — trying fallback provider")
                for i in still_missing:
                    title = i.get("media", {}).get("metadata", {}).get("title", i["id"])
                    log(f"  Fallback: {title}", level="DEBUG")
                run_batches([i["id"] for i in still_missing], fallback, "Fallback")
            else:
                log("All items matched in primary pass")
    else:
        log("Nothing to match")

    if touched_ids:
        log(f"Auditing {len(touched_ids)} matched item(s) for language/description mismatches...")
        refreshed = get_items(library_id)
        refreshed_by_id = {i["id"]: i for i in refreshed if i["id"] in touched_ids}
        audit_matched_items(refreshed_by_id)

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
    parser = argparse.ArgumentParser(description="Auto-match ABS items missing ASIN/ISBN")
    parser.add_argument("--full", action="store_true",
                        help="Process entire library instead of only new items")
    parser.add_argument("--library", choices=["audiobooks", "ebooks", "all"], default="all",
                        help="Library to process (default: all)")
    parser.add_argument("--force-covers", action="store_true",
                        help="Re-submit every item regardless of identifier status to refresh "
                             "its cover from the matched provider. Identifiers and other "
                             "already-set fields are left untouched.")
    args = parser.parse_args()

    if args.library == "all":
        targets = LIBRARIES
    else:
        targets = {args.library: LIBRARIES[args.library]}

    state = load_state()
    for name, library_id in targets.items():
        try:
            state[name] = process_library(name, library_id, args.full, state, force_covers=args.force_covers)
        except Exception as e:
            log(f"ERROR processing {name}: {e}", level="ERROR")
    save_state(state)


if __name__ == "__main__":
    main()
