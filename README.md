# abs-tools

Automated metadata and file maintenance tools for [Audiobookshelf](https://www.audiobookshelf.org/), packaged as Docker containers and managed by systemd timers.

## Tools

### abs-auto-match
Scans both the Audiobooks and Ebooks libraries hourly for items missing an ASIN and runs Audiobookshelf's quickmatch against them. Only triggers on items without an ASIN — items with existing metadata are left alone.

### abs-chapter-match
Matches chapter data for audiobooks via [Audnexus](https://github.com/laxamentumtech/audnexus) (accessed through the ABS API). Runs hourly on newly added items. Includes a fallback to use audio tracks as chapters when no ASIN is available.

### epub-convert
Converts EPUB2/1 files to EPUB3 using Calibre and fixes duplicate `libraryFiles` entries in Audiobookshelf. Runs hourly on newly added ebook items, with a full directory scan weekly.

## How it works

Each tool runs in two modes:

| Mode | Trigger | Behaviour |
|---|---|---|
| Incremental | Hourly systemd timer | Processes only items added since the last run (tracked in a state file) |
| Full | Manual or weekly timer (epub-convert only) | Processes the entire library |

State is persisted to `/var/lib/abs-tools/` so incremental runs survive reboots.

## Requirements

- Docker
- systemd (on the host/LXC)
- Access to the Audiobookshelf API
- For epub-convert: the ebooks directory must be bind-mounted into the container

## Installation

```bash
git clone https://github.com/ColinAgnew/abs-tools.git /opt/abs-tools
cd /opt/abs-tools
sudo bash install.sh
```

`install.sh` creates runtime directories, drops env file templates, installs systemd units and logrotate configs, and prints next steps.

### Configuration

Edit the env files installed to `/etc/abs-tools/`:

```bash
sudo nano /etc/abs-tools/abs-tools.env     # abs-auto-match + abs-chapter-match
sudo nano /etc/abs-tools/epub-convert.env  # epub-convert
```

See `env/*.env.example` for all available options.

### Pull images

```bash
docker pull ghcr.io/colinagnew/abs-tools-python:latest
docker pull ghcr.io/colinagnew/abs-tools-epub:latest
```

### Enable timers

```bash
systemctl enable --now abs-auto-match.timer
systemctl enable --now abs-chapter-match.timer
systemctl enable --now epub-convert-hourly.timer
systemctl enable --now epub-convert-weekly.timer
```

## Manual full runs

```bash
# Auto-match — all libraries
docker run --rm --user 1000:1000 --env-file /etc/abs-tools/abs-tools.env \
  -v /var/log/abs-tools:/var/log/abs-tools \
  -v /var/lib/abs-tools:/var/lib/abs-tools \
  ghcr.io/colinagnew/abs-tools-python:latest abs-auto-match --full

# Auto-match — one library
docker run --rm --user 1000:1000 --env-file /etc/abs-tools/abs-tools.env \
  -v /var/log/abs-tools:/var/log/abs-tools \
  -v /var/lib/abs-tools:/var/lib/abs-tools \
  ghcr.io/colinagnew/abs-tools-python:latest abs-auto-match --full --library audiobooks

# Chapter match — full audiobooks library
docker run --rm --user 1000:1000 --env-file /etc/abs-tools/abs-tools.env \
  -v /var/log/abs-tools:/var/log/abs-tools \
  -v /var/lib/abs-tools:/var/lib/abs-tools \
  ghcr.io/colinagnew/abs-tools-python:latest abs-chapter-match --full

# EPUB convert — full library scan
systemctl start epub-convert-full.service
```

## Versioning

Images are published to GitHub Container Registry on every push to `main` (`:latest`) and on version tags (`:1.0.0`, `:1.0`).

To release a new version:

```bash
git tag v1.0.0
git push origin v1.0.0
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
