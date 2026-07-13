# abs-tools

Automated metadata and file maintenance tools for [Audiobookshelf](https://www.audiobookshelf.org/), packaged as self-scheduling Docker containers.

## Tools

### abs-auto-match
Scans both the Audiobooks and Ebooks libraries hourly for items missing an ASIN and runs Audiobookshelf's quickmatch against them. Only triggers on items without an ASIN — items with existing metadata are left alone.

### abs-chapter-match
Matches chapter data for audiobooks via [Audnexus](https://github.com/laxamentumtech/audnexus) (accessed through the ABS API). Runs hourly on newly added items. Includes a fallback to use audio tracks as chapters when no ASIN is available.

### epub-convert
Converts EPUB2/1 files to EPUB3 using Calibre and fixes duplicate `libraryFiles` entries in Audiobookshelf. Runs hourly on newly added ebook items, with a full directory scan weekly.

## Deployment

### 1. Create host directories

```bash
mkdir -p /var/log/abs-tools /var/lib/abs-tools /etc/abs-tools
chown 1000:1000 /var/log/abs-tools /var/lib/abs-tools
```

### 2. Configure env files

```bash
cp env/abs-tools.env.example /etc/abs-tools/abs-tools.env
cp env/epub-convert.env.example /etc/abs-tools/epub-convert.env
nano /etc/abs-tools/abs-tools.env
nano /etc/abs-tools/epub-convert.env
```

### 3. Pull and start

```bash
docker pull ghcr.io/colinagnew/abs-tools-python:latest
docker pull ghcr.io/colinagnew/abs-tools-epub:latest
docker compose -f docker/docker-compose.yml up -d
```

Both containers start their internal schedulers immediately. Nothing runs on the host.

## Manual full runs

While the containers are running:

```bash
# Auto-match — all libraries
docker compose -f docker/docker-compose.yml exec abs-tools-python abs-auto-match --full

# Auto-match — one library
docker compose -f docker/docker-compose.yml exec abs-tools-python abs-auto-match --full --library audiobooks

# Chapter match — full audiobooks library
docker compose -f docker/docker-compose.yml exec abs-tools-python abs-chapter-match --full

# EPUB convert — full library scan
docker compose -f docker/docker-compose.yml exec abs-tools-epub --full
```

## Logs

```bash
# Live container output
docker compose -f docker/docker-compose.yml logs -f

# Script logs
tail -f /var/log/abs-tools/abs-auto-match.log
tail -f /var/log/abs-tools/abs-chapter-match.log
tail -f /var/log/abs-tools/epub-convert.log
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
