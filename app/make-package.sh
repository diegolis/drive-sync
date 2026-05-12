#!/bin/sh
set -eu
APP_DIR="$(CDPATH= cd -- "$(dirname -- "$0")" && pwd)"
OUT_DIR="$APP_DIR/../dist"
STAGE_DIR="$(mktemp -d)"
trap 'rm -rf "$STAGE_DIR"' EXIT INT TERM
mkdir -p "$OUT_DIR"
VERSION="0.1.0"
PKG="$OUT_DIR/drive-sync-desktop-$VERSION.tar.gz"
cp -R "$APP_DIR/drive_sync_desktop" "$STAGE_DIR/"
find "$STAGE_DIR/drive_sync_desktop" -name '__pycache__' -type d -prune -exec rm -rf {} +
cp "$APP_DIR/main.py" "$APP_DIR/install.sh" "$APP_DIR/uninstall.sh" "$APP_DIR/requirements.txt" "$STAGE_DIR/"
tar -C "$STAGE_DIR" -czf "$PKG" drive_sync_desktop main.py install.sh uninstall.sh requirements.txt
printf '%s\n' "$PKG"
