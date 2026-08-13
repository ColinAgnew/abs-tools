# abs-tools

Automated metadata and file maintenance tools for [Audiobookshelf](https://www.audiobookshelf.org/), packaged as a single self-scheduling Docker container.

## Tools

### abs-auto-match
Scans both the Audiobooks and Ebooks libraries for items missing an ASIN or ISBN and runs Audiobookshelf's quickmatch against them. Supports a primary and fallback metadata provider per library — useful when your primary provider (e.g. a custom Hardcover integration) doesn't have identifiers for every book. Sends items in configurable batches to avoid rate-limiting custom providers. Also supports routing a GraphicAudio subfolder within the audiobooks library to its own provider, since Audible has no data for those titles — these items are searched individually (title tag and part suffix stripped first, since the raw title won't match GraphicAudio's catalog) rather than through the batch quickmatch used for everything else.

Every match always takes the provider's cover image, even if one is already set (identifiers, description, and other fields are only ever filled when currently empty — never overwritten). Pass `--force-covers` to re-run this cover refresh across every item in a library regardless of identifier status, useful for a one-time bulk re-pull. After each run, matched items are checked for a language mismatch — either the matched language isn't English, or the language is English but the description text itself doesn't read as English (which can happen when a field gets filled in on a later run while an earlier, correct language value is left in place) — and logged as a warning for manual review rather than auto-corrected.

### abs-chapter-match
Matches chapter data for audiobooks via [Audnexus](https://github.com/laxamentumtech/audnexus) (accessed through the ABS API). Searches for an ASIN if one isn't present, and optionally falls back to using audio tracks as chapters. Supports a `--skip-matched` flag to skip books that already have sufficient chapters on full runs.

### epub-convert
Converts EPUB2/1 files to EPUB3 using Calibre and fixes duplicate `libraryFiles` entries in Audiobookshelf. Runs incrementally on newly added ebook items, with a separate full directory scan on a weekly schedule.

## Deployment

### 1. Download the config files

```bash
mkdir abs-tools && cd abs-tools

curl -o docker-compose.yml https://raw.githubusercontent.com/ColinAgnew/abs-tools/main/docker/docker-compose.yml
curl -o .env https://raw.githubusercontent.com/ColinAgnew/abs-tools/main/env/abs-tools.env.example
```

### 2. Edit `.env`

```bash
vi .env
```

The only required values are `ABS_HOST`, `ABS_TOKEN`, `AUDIOBOOKS_LIBRARY_ID`, and `EBOOKS_LIBRARY_ID`. Everything else has sensible defaults.

### 3. Start

```bash
docker compose up -d
```

The container starts its internal scheduler immediately. On startup it prints which tools are enabled and their schedules.

## Configuration

Credentials go in `.env`. Everything else is configured in the `environment:` section of `docker-compose.yml`.

All available variables with their defaults:

| Variable | Default | Description |
|---|---|---|
| **General** | | |
| `LOG_LEVEL` | `INFO` | Log verbosity: `DEBUG`, `INFO`, `WARN`, `ERROR`. `DEBUG` includes per-item detail; `INFO` is the default. |
| `ENABLE_AUTO_MATCH` | `true` | Enable/disable abs-auto-match |
| `ENABLE_CHAPTER_MATCH` | `true` | Enable/disable abs-chapter-match |
| `ENABLE_EPUB_CONVERT` | `true` | Enable/disable epub-convert |
| **Schedules** | | |
| `SCHEDULE_AUTO_MATCH` | `0 * * * *` | Cron schedule for abs-auto-match |
| `SCHEDULE_CHAPTER_MATCH` | `5 * * * *` | Cron schedule for abs-chapter-match |
| `SCHEDULE_EPUB_CONVERT` | `10 * * * *` | Cron schedule for epub-convert (incremental) |
| `SCHEDULE_EPUB_CONVERT_FULL` | `30 2 * * 0` | Cron schedule for epub-convert (full scan) |
| **abs-auto-match** | | |
| `AUTOMATCH_PROVIDER_AUDIOBOOKS` | `google` | Primary metadata provider for audiobook quickmatch. Built-in: `audible`, `audible.com`, `google`, `openlibrary`. Custom providers: `custom-<id>` — find IDs via `GET /api/custom-metadata-providers`. |
| `AUTOMATCH_PROVIDER_AUDIOBOOKS_FALLBACK` | *(none)* | Fallback provider for audiobooks still missing identifiers after the primary pass. |
| `AUTOMATCH_PROVIDER_EBOOKS` | `google` | Primary metadata provider for ebook quickmatch. Same values as above. |
| `AUTOMATCH_PROVIDER_EBOOKS_FALLBACK` | *(none)* | Fallback provider for ebooks still missing identifiers after the primary pass. |
| `AUTOMATCH_PROVIDER_AUDIOBOOKS_GRAPHICAUDIO` | *(none)* | Provider used for GraphicAudio items in the audiobooks library, detected by folder path (and by title tag `[Dramatized Adaptation]` as a safety net for misfiled items). Leave unset to disable this routing entirely. |
| `AUTOMATCH_GRAPHICAUDIO_PATH_PREFIX` | `/path/to/audiobooks/GraphicAudio` | Path prefix, as Audiobookshelf's own API reports it, used to detect GraphicAudio items. |
| `AUTOMATCH_BATCH_SIZE` | `25` | Items per quickmatch batch. Lower this if your metadata provider rate-limits on large libraries. |
| `AUTOMATCH_BATCH_DELAY` | `10` | Seconds to wait between batches. |
| `AUTOMATCH_FALLBACK_DELAY` | `60` | Seconds to wait after the primary pass before checking which items still need a fallback match. |
| **abs-chapter-match** | | |
| `CHAPTER_THRESHOLD` | `3` | Maximum chapter count difference allowed before replacing existing chapters. Also used by `--skip-matched` to determine which books are considered already complete. |
| `CHAPTER_PROVIDER` | `audible.com` | Metadata provider for chapter lookup |
| `CHAPTER_REGION` | `US` | Region code for chapter lookup |
| `SEARCH_FOR_ASIN` | `true` | Search for an ASIN if one is not present before attempting chapter match |
| `USE_TRACKS_AS_CHAPTERS` | `false` | Fall back to audio tracks as chapters if no ASIN can be found |
| `DISABLE_RATE_PROTECTION` | `false` | Disable the 2s delay between API calls |
| **epub-convert** | | |
| `EBOOKS_DIR` | `/ebooks` | Path where the ebooks directory is mounted inside the container |
| `ABS_EBOOKS_PREFIX` | `/ebooks` | Path as Audiobookshelf sees the ebooks directory internally |

## Volumes

The container is self-contained by default — logs and state are stored inside it. Optionally mount host directories in `docker-compose.yml` to persist them across container updates:

```yaml
volumes:
  - ./logs:/var/log/abs-tools      # persist logs
  - ./data:/var/lib/abs-tools      # persist state (incremental tracking)
  - /path/to/ebooks:/ebooks        # required for epub-convert
```

## Manual runs

All tools support being run manually via `docker exec`. Output goes to your terminal; scheduled runs go to Docker logs and optionally to log files if the volume is mounted.

```bash
# Auto-match — all libraries
docker exec abs-tools python3 /scripts/abs_auto_match.py --full

# Auto-match — one library
docker exec abs-tools python3 /scripts/abs_auto_match.py --full --library audiobooks
docker exec abs-tools python3 /scripts/abs_auto_match.py --full --library ebooks

# Auto-match — force-refresh covers on every item, regardless of identifier status
# (identifiers and other already-set fields are left untouched)
docker exec abs-tools python3 /scripts/abs_auto_match.py --full --force-covers

# Auto-match — check language/description mismatches only, no matching or writes
docker exec abs-tools python3 /scripts/abs_auto_match.py --audit-only

# Chapter match — full run
docker exec abs-tools python3 /scripts/quick_match_chapters.py --full

# Chapter match — full run, skip books that already have enough chapters
docker exec abs-tools python3 /scripts/quick_match_chapters.py --full --skip-matched

# EPUB convert — full library scan
docker exec abs-tools /scripts/epubv3.sh --full
```

## Custom metadata providers

ABS supports custom metadata provider plugins (such as Hardcover, Goodreads integrations, etc.). To use one with abs-auto-match, find its ID first:

```bash
curl -H "Authorization: Bearer <token>" <ABS_HOST>/api/custom-metadata-providers
```

Then set the provider in `docker-compose.yml`:

```yaml
- AUTOMATCH_PROVIDER_EBOOKS=custom-<id>
- AUTOMATCH_PROVIDER_EBOOKS_FALLBACK=custom-<id>
```

The batch quickmatch API defaults to Google Books when no provider is set. Custom providers are rate-limited more easily than built-ins — tune `AUTOMATCH_BATCH_SIZE` and `AUTOMATCH_BATCH_DELAY` if you see 500 errors during large runs.

## Credits

- [Audiobookshelf](https://www.audiobookshelf.org/) — the self-hosted audiobook and podcast server these tools integrate with
- [Audnexus](https://github.com/laxamentumtech/audnexus) — the metadata and chapter data provider used by abs-chapter-match
- [Calibre](https://calibre-ebook.com/) — provides `ebook-convert`, used by epub-convert for EPUB2→EPUB3 conversion
- [absToolbox](https://github.com/Vito0912/absToolbox) by Vito0912 — the original `quick_match_chapters.py` script that abs-chapter-match is based on

## Disclaimer

This project was built with the assistance of [Claude](https://claude.ai) by Anthropic. All code has been reviewed and adapted for this specific use case.

## License

[MIT](LICENSE)
