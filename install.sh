#!/bin/bash
# Installs systemd units, timers, and logrotate configs to the host.
# Does NOT build Docker images or start services — see below for those steps.
#
# Run as root on the Proxmox LXC hosting Docker.
set -euo pipefail

REPO_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"

log() { echo "==> $*"; }

# ── Directories ──────────────────────────────────────────────────────────
log "Creating runtime directories"
mkdir -p /etc/abs-tools /var/log/abs-tools /var/lib/abs-tools
chown 1000:1000 /var/log/abs-tools /var/lib/abs-tools

# ── Env files ────────────────────────────────────────────────────────────
if [[ ! -f /etc/abs-tools/abs-tools.env ]]; then
    log "Installing abs-tools.env template — edit /etc/abs-tools/abs-tools.env before starting services"
    cp "${REPO_DIR}/env/abs-tools.env.example" /etc/abs-tools/abs-tools.env
    chmod 600 /etc/abs-tools/abs-tools.env
else
    log "Skipping abs-tools.env (already exists)"
fi

if [[ ! -f /etc/abs-tools/epub-convert.env ]]; then
    log "Installing epub-convert.env template — edit /etc/abs-tools/epub-convert.env before starting services"
    cp "${REPO_DIR}/env/epub-convert.env.example" /etc/abs-tools/epub-convert.env
    chmod 600 /etc/abs-tools/epub-convert.env
else
    log "Skipping epub-convert.env (already exists)"
fi

# ── Systemd units ────────────────────────────────────────────────────────
log "Installing systemd units"
UNITS=(
    abs-auto-match/abs-auto-match.service
    abs-auto-match/abs-auto-match.timer
    abs-chapter-match/abs-chapter-match.service
    abs-chapter-match/abs-chapter-match.timer
    epub-convert/epub-convert.service
    epub-convert/epub-convert-full.service
    epub-convert/epub-convert-hourly.timer
    epub-convert/epub-convert-weekly.timer
)
for unit in "${UNITS[@]}"; do
    cp "${REPO_DIR}/${unit}" /etc/systemd/system/
done

systemctl daemon-reload

# ── Logrotate ────────────────────────────────────────────────────────────
log "Installing logrotate configs"
cp "${REPO_DIR}/abs-auto-match/logrotate.d/abs-auto-match" /etc/logrotate.d/
cp "${REPO_DIR}/abs-chapter-match/logrotate.d/abs-chapter-match" /etc/logrotate.d/
cp "${REPO_DIR}/epub-convert/logrotate.d/epub-convert" /etc/logrotate.d/

log ""
log "Installation complete."
log ""
log "Next steps:"
log "  1. Edit /etc/abs-tools/abs-tools.env and /etc/abs-tools/epub-convert.env"
log "  2. Pull images from GHCR:"
log "       docker pull ghcr.io/colinagnew/ghcr.io/colinagnew/abs-tools-python:latest:latest"
log "       docker pull ghcr.io/colinagnew/abs-tools-epub:latest"
log "  3. Enable timers:"
log "       systemctl enable --now abs-auto-match.timer"
log "       systemctl enable --now abs-chapter-match.timer"
log "       systemctl enable --now epub-convert-hourly.timer"
log "       systemctl enable --now epub-convert-weekly.timer"
log ""
log "Manual full runs:"
log "  docker run --rm --user 1000:1000 --env-file /etc/abs-tools/abs-tools.env \\"
log "    -v /var/log/abs-tools:/var/log/abs-tools -v /var/lib/abs-tools:/var/lib/abs-tools \\"
log "    ghcr.io/colinagnew/abs-tools-python:latest abs-auto-match --full"
log "  docker run --rm --user 1000:1000 --env-file /etc/abs-tools/abs-tools.env \\"
log "    -v /var/log/abs-tools:/var/log/abs-tools -v /var/lib/abs-tools:/var/lib/abs-tools \\"
log "    ghcr.io/colinagnew/abs-tools-python:latest abs-auto-match --full --library audiobooks"
log "  docker run --rm --user 1000:1000 --env-file /etc/abs-tools/abs-tools.env \\"
log "    -v /var/log/abs-tools:/var/log/abs-tools -v /var/lib/abs-tools:/var/lib/abs-tools \\"
log "    ghcr.io/colinagnew/abs-tools-python:latest abs-chapter-match --full"
log "  systemctl start epub-convert-full.service"
