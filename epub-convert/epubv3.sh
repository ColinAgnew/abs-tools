#!/bin/bash
# EPUB2→EPUB3 conversion and ABS duplicate libraryFiles fix.
#
# Incremental mode (default, hourly timer):
#   Queries ABS API for ebook items added since last run, converts only those files.
#
# Full mode (--full, weekly timer or manual):
#   Scans the entire EBOOKS_DIR with find, converts all non-EPUB3 files.
#
# Usage:
#   epubv3.sh          # incremental
#   epubv3.sh --full   # full library scan
set -uo pipefail

ABS_HOST="${ABS_HOST:?ABS_HOST not set}"
ABS_TOKEN="${ABS_TOKEN:?ABS_TOKEN not set}"
EBOOKS_LIB_ID="${EBOOKS_LIBRARY_ID:?EBOOKS_LIBRARY_ID not set}"
EBOOKS_DIR="${EBOOKS_DIR:-/ebooks}"
ABS_EBOOKS_PREFIX="${ABS_EBOOKS_PREFIX:-/ebooks}"
STATE_FILE="${STATE_FILE:-/var/lib/abs-tools/epub-convert-state.json}"

FULL_RUN=false
[[ "${1:-}" == "--full" ]] && FULL_RUN=true

ABS_AUTH="Authorization: Bearer ${ABS_TOKEN}"


log() { echo "[$(date -u '+%Y-%m-%d %H:%M:%S UTC')] $*"; }

convert_epub() {
    local f="$1"
    local out="${f%.epub}-epub3.epub"

    local version
    version=$(unzip -p "$f" "*.opf" 2>/dev/null | grep -o 'version="[0-9]' | head -1)
    [[ -z "$version" ]] && version=$(unzip -p "$f" "*/*.opf" 2>/dev/null | grep -o 'version="[0-9]' | head -1)
    version=$(echo "$version" | tr -d 'version="')

    [[ "$version" == "3" ]] && return 0

    if [[ -f "$out" ]]; then
        log "SKIP (already converted): $f"
        return 0
    fi

    log "Converting (v${version:-?}): $f"
    if ebook-convert "$f" "$out" --epub-version=3 2>&1; then
        mv "$out" "$f"
        log "OK: $f"
    else
        log "FAILED: $f"
        rm -f "$out"
    fi
}

fix_duplicates() {
    local item_id="$1"
    local abs_path="$2"
    local host_path="${abs_path/$ABS_EBOOKS_PREFIX/$EBOOKS_DIR}"

    if [[ ! -f "$host_path" ]]; then
        log "SKIP duplicate fix (file not found on host): $host_path"
        return
    fi

    log "Fixing duplicate libraryFiles: $item_id"
    mv "$host_path" "${host_path}.bak"
    curl -s -X POST "${ABS_HOST}/api/items/${item_id}/scan" -H "$ABS_AUTH" > /dev/null
    mv "${host_path}.bak" "$host_path"
    curl -s -X POST "${ABS_HOST}/api/items/${item_id}/scan" -H "$ABS_AUTH" > /dev/null
    log "Fixed: $item_id"
}

check_and_fix_duplicates_for_item() {
    local id="$1"
    local result
    result=$(curl -s "${ABS_HOST}/api/items/${id}" -H "$ABS_AUTH" | python3 -c "
import json, sys
data = json.load(sys.stdin)
files = data.get('libraryFiles', [])
paths = [f['metadata']['path'] for f in files]
if len(paths) != len(set(paths)):
    for f in files:
        if f['metadata']['ext'] == '.epub':
            print(data['id'] + '|' + f['metadata']['path'])
            break
" 2>/dev/null)

    if [[ -n "$result" ]]; then
        local item_id abs_path
        item_id=$(cut -d'|' -f1 <<< "$result")
        abs_path=$(cut -d'|' -f2 <<< "$result")
        fix_duplicates "$item_id" "$abs_path"
    fi
}

# ── Load state ───────────────────────────────────────────────────────────
load_last_added_at() {
    python3 -c "
import json, sys
try:
    data = json.load(open('${STATE_FILE}'))
    print(data.get('last_added_at', 0))
except Exception:
    print(0)
" 2>/dev/null || echo 0
}

save_state() {
    local ts_ms="$1"
    mkdir -p "$(dirname "${STATE_FILE}")"
    python3 -c "
import json
data = {'last_added_at': ${ts_ms}, 'last_check': '$(date -u +%Y-%m-%dT%H:%M:%SZ)'}
json.dump(data, open('${STATE_FILE}', 'w'), indent=2)
"
}

# ── Incremental: get new ebook items from ABS API ─────────────────────────
incremental_run() {
    local since_ms
    since_ms=$(load_last_added_at)
    log "Incremental run — checking items added after epoch ms ${since_ms}"

    local max_added_at="$since_ms"

    curl -s "${ABS_HOST}/api/libraries/${EBOOKS_LIB_ID}/items?sort=addedAt&desc=0" \
        -H "$ABS_AUTH" | python3 -c "
import json, sys
since = ${since_ms}
data = json.load(sys.stdin)
for item in data.get('results', []):
    if item.get('addedAt', 0) > since:
        files = item.get('libraryFiles', [])
        for f in files:
            if f['metadata']['ext'] == '.epub':
                print(str(item['addedAt']) + '|' + item['id'] + '|' + f['metadata']['path'])
                break
" 2>/dev/null | while IFS='|' read -r added_at item_id abs_path; do
        local host_path="${abs_path/$ABS_EBOOKS_PREFIX/$EBOOKS_DIR}"

        if [[ ! -f "$host_path" ]]; then
            log "File not found on host (skipping): $host_path"
            continue
        fi

        log "Processing new item ${item_id}: $host_path"

        # Step 1: convert
        convert_epub "$host_path"

        # Step 2: fix duplicates
        check_and_fix_duplicates_for_item "$item_id"

        [[ "$added_at" -gt "$max_added_at" ]] && max_added_at="$added_at"
    done

    save_state "$max_added_at"
}

# ── Full: scan entire directory ──────────────────────────────────────────
full_run() {
    log "Full run — scanning ${EBOOKS_DIR}"

    log "=== Step 1: Converting EPUB1/2 files ==="
    find "$EBOOKS_DIR" -name "*.epub" | grep -v "\-epub3\.epub" | while read -r f; do
        convert_epub "$f"
    done

    local remaining
    remaining=$(find "$EBOOKS_DIR" -name "*-epub3.epub" | wc -l)
    log "Remaining -epub3.epub files (should be 0): $remaining"

    log "=== Step 2: Fixing ABS duplicate libraryFiles ==="
    curl -s "${ABS_HOST}/api/libraries/${EBOOKS_LIB_ID}/items?limit=1000" \
        -H "$ABS_AUTH" | python3 -c "
import json, sys
data = json.load(sys.stdin)
for item in data.get('results', []):
    print(item['id'])
" | while read -r id; do
        check_and_fix_duplicates_for_item "$id"
    done
}

# ── Main ─────────────────────────────────────────────────────────────────
if $FULL_RUN; then
    full_run
else
    incremental_run
fi

log "=== Done ==="
