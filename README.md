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

All configuration is in the `.env` file. Key options:

| Variable | Default | Description |
|---|---|---|
| `ENABLE_AUTO_MATCH` | `true` | Enable/disable auto-match |
| `ENABLE_CHAPTER_MATCH` | `true` | Enable/disable chapter match |
| `ENABLE_EPUB_CONVERT` | `true` | Enable/disable epub conversion |
| `SCHEDULE_AUTO_MATCH` | `0 * * * *` | Cron schedule for auto-match |
| `SCHEDULE_CHAPTER_MATCH` | `5 * * * *` | Cron schedule for chapter match |
| `SCHEDULE_EPUB_CONVERT` | `10 * * * *` | Cron schedule for epub convert (incremental) |
| `SCHEDULE_EPUB_CONVERT_FULL` | `30 2 * * 0` | Cron schedule for epub convert (full scan) |

See `env/abs-tools.env.example` for all options.

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
- [supercronic](https://github.com/aptible/supercronic) — container-native cron scheduler

## Disclaimer

This project was built with the assistance of [Claude](https://claude.ai) by Anthropic. All code has been reviewed and adapted for this specific use case.

## License

[MIT](LICENSE)
