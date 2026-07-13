# abs-tools

Automated metadata and file maintenance tools for [Audiobookshelf](https://www.audiobookshelf.org/), packaged as a single self-scheduling Docker container.

## Tools

### abs-auto-match
Scans both the Audiobooks and Ebooks libraries for items missing an ASIN and runs Audiobookshelf's quickmatch against them. Only triggers on items without an ASIN — items with existing metadata are left alone.

### abs-chapter-match
Matches chapter data for audiobooks via [Audnexus](https://github.com/laxamentumtech/audnexus) (accessed through the ABS API). Includes a fallback to use audio tracks as chapters when no ASIN is available.

### epub-convert
Converts EPUB2/1 files to EPUB3 using Calibre and fixes duplicate `libraryFiles` entries in Audiobookshelf. Runs on newly added ebook items, with a separate full directory scan on a weekly schedule.

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
| `ENABLE_AUTO_MATCH` | `true` | Enable/disable abs-auto-match |
| `ENABLE_CHAPTER_MATCH` | `true` | Enable/disable abs-chapter-match |
| `ENABLE_EPUB_CONVERT` | `true` | Enable/disable epub-convert |
| **Schedules** | | |
| `SCHEDULE_AUTO_MATCH` | `0 * * * *` | Cron schedule for abs-auto-match |
| `SCHEDULE_CHAPTER_MATCH` | `5 * * * *` | Cron schedule for abs-chapter-match |
| `SCHEDULE_EPUB_CONVERT` | `10 * * * *` | Cron schedule for epub-convert (incremental) |
| `SCHEDULE_EPUB_CONVERT_FULL` | `30 2 * * 0` | Cron schedule for epub-convert (full scan) |
| **abs-auto-match** | | |
| `AUTOMATCH_PROVIDER_AUDIOBOOKS` | `audible.com` | Metadata provider for audiobook quickmatch |
| `AUTOMATCH_PROVIDER_EBOOKS` | `openlibrary` | Metadata provider for ebook quickmatch |
| **epub-convert** | | |
| `EBOOKS_DIR` | `/ebooks` | Path where the ebooks directory is mounted inside the container |
| `ABS_EBOOKS_PREFIX` | `/ebooks` | Path as Audiobookshelf sees the ebooks directory internally |
| **abs-chapter-match** | | |
| `CHAPTER_THRESHOLD` | `3` | Max chapter count difference before replacing existing chapters |
| `CHAPTER_PROVIDER` | `audible.com` | Metadata provider for chapter lookup |
| `CHAPTER_REGION` | `US` | Region code for chapter lookup |
| `SEARCH_FOR_ASIN` | `true` | Search for ASIN if not present before matching chapters |
| `USE_TRACKS_AS_CHAPTERS` | `false` | Fall back to audio tracks as chapters if no ASIN found |
| `DISABLE_RATE_PROTECTION` | `false` | Disable 2s delay between API calls |

## Volumes

The container is self-contained by default — logs and state are stored inside it. Optionally mount host directories in `docker-compose.yml` to persist them:

```yaml
volumes:
  - ./logs:/var/log/abs-tools      # persist logs
  - ./data:/var/lib/abs-tools      # persist state (incremental tracking)
  - /path/to/ebooks:/ebooks        # required for epub-convert
```

## Manual full runs

```bash
# Auto-match — all libraries
docker exec abs-tools python3 /scripts/abs_auto_match.py --full

# Auto-match — one library
docker exec abs-tools python3 /scripts/abs_auto_match.py --full --library audiobooks

# Chapter match — full audiobooks library
docker exec abs-tools python3 /scripts/quick_match_chapters.py --full

# EPUB convert — full library scan
docker exec abs-tools /scripts/epubv3.sh --full
```

## Credits

- [Audiobookshelf](https://www.audiobookshelf.org/) — the self-hosted audiobook and podcast server these tools integrate with
- [Audnexus](https://github.com/laxamentumtech/audnexus) — the metadata and chapter data provider used by abs-chapter-match
- [Calibre](https://calibre-ebook.com/) — provides `ebook-convert`, used by epub-convert for EPUB2→EPUB3 conversion
- [absToolbox](https://github.com/Vito0912/absToolbox) by Vito0912 — the original `quick_match_chapters.py` script that abs-chapter-match is based on

## Disclaimer

This project was built with the assistance of [Claude](https://claude.ai) by Anthropic. All code has been reviewed and adapted for this specific use case.

## License

[MIT](LICENSE)
