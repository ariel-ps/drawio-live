#!/usr/bin/env bash
# curl -fsSL https://raw.githubusercontent.com/ariel-ps/drawio-live/main/bootstrap.sh | bash
#
# Clones this repo (if not already present) and runs the one-click setup:
# clones draw.io, applies the patch, starts the relay, opens your browser.
set -euo pipefail

REPO_URL="https://github.com/ariel-ps/drawio-live.git"
REPO_DIR="${DRAWIO_LIVE_DIR:-$HOME/drawio-live}"

if [ ! -d "$REPO_DIR" ]; then
    git clone --depth 1 "$REPO_URL" "$REPO_DIR"
else
    echo "$REPO_DIR already exists, skipping clone"
fi

exec python3 "$REPO_DIR/skills/drawio-live/scripts/setup.py" "$@"
