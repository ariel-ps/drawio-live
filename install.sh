#!/usr/bin/env bash
# Install drawio-live: symlinks the skill for Claude Code (or any Agent
# Skills-compatible host) and puts a `drawio-debug` command on your PATH.
#
# Usage: ./install.sh [--bin-dir ~/.local/bin] [--skills-dir ~/.claude/skills]
set -euo pipefail

REPO_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
BIN_DIR="${HOME}/.local/bin"
SKILLS_DIR="${HOME}/.claude/skills"

while [ $# -gt 0 ]; do
    case "$1" in
        --bin-dir) BIN_DIR="$2"; shift 2 ;;
        --skills-dir) SKILLS_DIR="$2"; shift 2 ;;
        *) echo "unknown argument: $1" >&2; exit 1 ;;
    esac
done

mkdir -p "$BIN_DIR" "$SKILLS_DIR"

if [ -e "$SKILLS_DIR/drawio-live" ] || [ -L "$SKILLS_DIR/drawio-live" ]; then
    echo "skip: $SKILLS_DIR/drawio-live already exists"
else
    ln -s "$REPO_DIR/skills/drawio-live" "$SKILLS_DIR/drawio-live"
    echo "linked skill: $SKILLS_DIR/drawio-live -> $REPO_DIR/skills/drawio-live"
fi

if [ -e "$BIN_DIR/drawio-debug" ] || [ -L "$BIN_DIR/drawio-debug" ]; then
    echo "skip: $BIN_DIR/drawio-debug already exists"
else
    ln -s "$REPO_DIR/skills/drawio-live/scripts/drawio-debug" "$BIN_DIR/drawio-debug"
    echo "linked command: $BIN_DIR/drawio-debug"
fi

echo
echo "Done. If $BIN_DIR isn't on your PATH, add it, then run:"
echo "  drawio-debug"
