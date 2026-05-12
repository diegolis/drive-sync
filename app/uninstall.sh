#!/bin/sh
set -eu
APP_ID="drive-sync-desktop"
PREFIX="${PREFIX:-$HOME/.local}"
APPS_DIR="${APPS_DIR:-$HOME/.local/share/applications}"
SYSTEMD_USER_DIR="${SYSTEMD_USER_DIR:-$HOME/.config/systemd/user}"
AUTOSTART_DIR="${AUTOSTART_DIR:-$HOME/.config/autostart}"
rm -rf "$PREFIX/share/$APP_ID"
rm -f "$PREFIX/bin/drive-sync-desktop" "$PREFIX/bin/drive-sync-desktop-agent" "$PREFIX/bin/drive-sync-desktop-tray"
rm -f "$APPS_DIR/$APP_ID.desktop"
rm -f "$SYSTEMD_USER_DIR/$APP_ID-agent.service"
rm -f "$AUTOSTART_DIR/$APP_ID-tray.desktop"
echo "Desinstalado $APP_ID"
