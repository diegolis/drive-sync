#!/bin/sh
set -eu
APP_ID="drive-sync-desktop"
PREFIX="${PREFIX:-$HOME/.local}"
BIN_DIR="$PREFIX/bin"
APPS_DIR="${APPS_DIR:-$HOME/.local/share/applications}"
SYSTEMD_USER_DIR="${SYSTEMD_USER_DIR:-$HOME/.config/systemd/user}"
AUTOSTART_DIR="${AUTOSTART_DIR:-$HOME/.config/autostart}"

# Stop the agent first so we don't leave it running against deleted files.
if command -v systemctl >/dev/null 2>&1; then
  systemctl --user disable --now "$APP_ID-agent.service" >/dev/null 2>&1 || true
fi

rm -rf "$PREFIX/share/$APP_ID"
rm -f "$BIN_DIR/drive-sync-desktop" "$BIN_DIR/drive-sync-desktop-agent" "$BIN_DIR/drive-sync-desktop-tray"
rm -f "$APPS_DIR/$APP_ID.desktop"
rm -f "$SYSTEMD_USER_DIR/$APP_ID-agent.service"
rm -f "$AUTOSTART_DIR/$APP_ID-tray.desktop"

# Remove the rclone binary we installed (if any). We only delete it when we
# left the marker file, so we never remove a user-managed rclone.
if [ -f "$BIN_DIR/.rclone.managed-by-drive-sync" ]; then
  rm -f "$BIN_DIR/rclone" "$BIN_DIR/.rclone.managed-by-drive-sync"
  echo "Removed rclone installed by drive-sync at $BIN_DIR/rclone"
fi

echo "Uninstalled $APP_ID."
echo
echo "Local state was NOT removed. To wipe jobs, runs, logs, and the OAuth token:"
echo "  rm -rf \"\${XDG_DATA_HOME:-\$HOME/.local/share}/$APP_ID\""
echo "  rm -rf \"\${XDG_CONFIG_HOME:-\$HOME/.config}/$APP_ID\""
echo "  # rclone.conf is shared with rclone; remove only the drive-sync remote:"
echo "  # rclone config delete <remote-name>"
