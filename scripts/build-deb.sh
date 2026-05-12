#!/bin/sh
# Build a .deb package for Drive Sync Desktop.
#
# Output: dist/drive-sync-desktop_<version>_all.deb
#
# Layout produced inside the .deb:
#   /usr/lib/drive-sync-desktop/        Python code and frontend assets
#   /usr/bin/drive-sync-desktop*        Thin shell wrappers
#   /usr/lib/systemd/user/...service    User-scoped agent unit
#   /etc/xdg/autostart/...desktop       Tray autostart entry
#   /usr/share/applications/...desktop  Launcher
#   /usr/share/doc/drive-sync-desktop/  README, LICENSE, CHANGELOG, copyright
#
# Runtime deps come from apt; rclone is a Recommends (apt's rclone is older
# than 1.66 on some releases; the included `drive-sync-desktop-update-rclone`
# helper installs a current one into ~/.local/bin without requiring root).

set -eu

ROOT_DIR="$(CDPATH= cd -- "$(dirname -- "$0")/.." && pwd)"
APP_DIR="$ROOT_DIR/app"
DIST_DIR="$ROOT_DIR/dist"
PKG_NAME="drive-sync-desktop"
ARCH="all"
VERSION="$(awk -F\" '/^__version__/ {print $2}' "$APP_DIR/drive_sync_desktop/__init__.py")"
if [ -z "$VERSION" ]; then
  echo "Error: could not read __version__ from drive_sync_desktop/__init__.py" >&2
  exit 1
fi
MAINTAINER="${MAINTAINER:-Diego Lis <diegolis@users.noreply.github.com>}"

STAGE="$(mktemp -d)"
trap 'rm -rf "$STAGE"' EXIT INT TERM

LIB="$STAGE/usr/lib/$PKG_NAME"
BIN="$STAGE/usr/bin"
DOC="$STAGE/usr/share/doc/$PKG_NAME"
APPS="$STAGE/usr/share/applications"
SYSTEMD="$STAGE/usr/lib/systemd/user"
AUTOSTART="$STAGE/etc/xdg/autostart"
DEBIAN="$STAGE/DEBIAN"

mkdir -p "$LIB" "$BIN" "$DOC" "$APPS" "$SYSTEMD" "$AUTOSTART" "$DEBIAN"

# Application code.
cp -R "$APP_DIR/drive_sync_desktop" "$LIB/"
cp "$APP_DIR/main.py" "$LIB/"
find "$LIB" -name '__pycache__' -type d -prune -exec rm -rf {} +

# Thin wrappers in /usr/bin. They prefer a user-installed rclone in
# ~/.local/bin if available, so the user can install a newer one without root.
cat > "$BIN/drive-sync-desktop" <<'EOF'
#!/bin/sh
export PYTHONPATH="/usr/lib/drive-sync-desktop"
if [ -z "${RCLONE_PATH:-}" ] && [ -x "$HOME/.local/bin/rclone" ]; then
  export RCLONE_PATH="$HOME/.local/bin/rclone"
fi
exec python3 /usr/lib/drive-sync-desktop/main.py "$@"
EOF

cat > "$BIN/drive-sync-desktop-agent" <<'EOF'
#!/bin/sh
export PYTHONPATH="/usr/lib/drive-sync-desktop"
if [ -z "${RCLONE_PATH:-}" ] && [ -x "$HOME/.local/bin/rclone" ]; then
  export RCLONE_PATH="$HOME/.local/bin/rclone"
fi
exec python3 /usr/lib/drive-sync-desktop/main.py --agent "$@"
EOF

cat > "$BIN/drive-sync-desktop-tray" <<'EOF'
#!/bin/sh
export PYTHONPATH="/usr/lib/drive-sync-desktop"
if [ -z "${RCLONE_PATH:-}" ] && [ -x "$HOME/.local/bin/rclone" ]; then
  export RCLONE_PATH="$HOME/.local/bin/rclone"
fi
exec python3 /usr/lib/drive-sync-desktop/main.py --tray "$@"
EOF

# Helper for installing a current rclone into ~/.local/bin (no root needed).
cat > "$BIN/drive-sync-desktop-update-rclone" <<'EOF'
#!/bin/sh
set -eu
BIN_DIR="$HOME/.local/bin"
mkdir -p "$BIN_DIR"
arch="$(uname -m)"
case "$arch" in
  x86_64|amd64) rarch="amd64" ;;
  aarch64|arm64) rarch="arm64" ;;
  armv7l|armv6l) rarch="arm" ;;
  *) echo "Unsupported architecture: $arch" >&2; exit 1 ;;
esac
os="$(uname -s | tr '[:upper:]' '[:lower:]')"
url="https://downloads.rclone.org/rclone-current-${os}-${rarch}.zip"
tmp="$(mktemp -d)"
trap 'rm -rf "$tmp"' EXIT INT TERM
echo "Downloading rclone from $url ..."
curl -fsSL "$url" -o "$tmp/rclone.zip"
unzip -oq "$tmp/rclone.zip" -d "$tmp"
bin="$(find "$tmp" -type f -name rclone | head -n1)"
install -m 0755 "$bin" "$BIN_DIR/rclone"
echo "Installed: $BIN_DIR/rclone"
"$BIN_DIR/rclone" version | head -1
EOF

chmod 0755 "$BIN/drive-sync-desktop" "$BIN/drive-sync-desktop-agent" \
           "$BIN/drive-sync-desktop-tray" "$BIN/drive-sync-desktop-update-rclone"

# Desktop launcher.
cat > "$APPS/$PKG_NAME.desktop" <<EOF
[Desktop Entry]
Type=Application
Name=Drive Sync Desktop
Comment=Sync folders with Google Drive using rclone
Exec=/usr/bin/drive-sync-desktop
Terminal=false
Categories=Utility;Network;FileTransfer;
EOF

# Systemd user unit (Debian places system-installed user units here).
cat > "$SYSTEMD/$PKG_NAME-agent.service" <<EOF
[Unit]
Description=Drive Sync Desktop Agent

[Service]
ExecStart=/usr/bin/drive-sync-desktop-agent --interval-seconds 30
Restart=always
RestartSec=5

[Install]
WantedBy=default.target
EOF

# Tray autostart (system-wide xdg autostart).
cat > "$AUTOSTART/$PKG_NAME-tray.desktop" <<EOF
[Desktop Entry]
Type=Application
Name=Drive Sync Tray
Comment=Drive Sync status icon
Exec=/usr/bin/drive-sync-desktop-tray
X-GNOME-Autostart-enabled=true
NoDisplay=false
Terminal=false
EOF

# Docs.
cp "$ROOT_DIR/README.md" "$DOC/"
cp "$ROOT_DIR/LICENSE" "$DOC/copyright"
cat > "$DOC/changelog.Debian" <<EOF
$PKG_NAME ($VERSION-1) unstable; urgency=low

  * Packaged from upstream $VERSION.

 -- $MAINTAINER  $(date -R)
EOF
gzip -n9 "$DOC/changelog.Debian"

# Compute installed size in KB (excluding DEBIAN/).
INSTALLED_SIZE="$(du -sk --exclude=DEBIAN "$STAGE" | cut -f1)"

# Control file. python3-webview is the apt name for pywebview.
cat > "$DEBIAN/control" <<EOF
Package: $PKG_NAME
Version: $VERSION
Section: net
Priority: optional
Architecture: $ARCH
Maintainer: $MAINTAINER
Installed-Size: $INSTALLED_SIZE
Depends: python3 (>= 3.10), python3-gi, gir1.2-webkit2-4.1, python3-webview, python3-pil
Recommends: rclone (>= 1.66~) | rclone, python3-pystray
Suggests: curl, unzip
Homepage: https://github.com/diegolis/drive-sync
Description: Sync local folders with Google Drive via rclone
 Drive Sync Desktop is a Linux desktop app that wraps rclone with a simple
 graphical UI for keeping local folders in sync with Google Drive.
 .
 Features:
   * Backup, mirror, and bidirectional (bisync) modes.
   * Dry-run preview before destructive operations.
   * Run history and per-run logs in SQLite (WAL).
   * Optional systemd user agent for scheduled syncs.
   * Tray icon with at-a-glance status.
 .
 rclone 1.66+ is required for the bisync --resilient feature. The included
 drive-sync-desktop-update-rclone helper installs a current rclone into
 \$HOME/.local/bin without requiring root.
EOF

# postinst: refresh systemd-user daemons; print a hint about rclone.
cat > "$DEBIAN/postinst" <<'EOF'
#!/bin/sh
set -e
if command -v systemctl >/dev/null 2>&1; then
  systemctl --global daemon-reload >/dev/null 2>&1 || true
fi

# Warn (but don't fail) if no suitable rclone is on the typical PATH.
if ! command -v rclone >/dev/null 2>&1; then
  cat <<MSG
drive-sync-desktop: rclone not found on PATH.
  To install a current rclone into your user bin without root:
      drive-sync-desktop-update-rclone
  Or install it system-wide via your package manager / rclone.org.
MSG
elif ! rclone bisync --help 2>/dev/null | grep -q -- "--resilient"; then
  cat <<MSG
drive-sync-desktop: your rclone is older than 1.66 and lacks --resilient.
  Bidirectional sync will work, but is more fragile. To upgrade per-user:
      drive-sync-desktop-update-rclone
MSG
fi

exit 0
EOF
chmod 0755 "$DEBIAN/postinst"

# prerm: nothing service-wide to stop (units are per-user). Leave the user's
# data alone so reinstalls/upgrades don't lose state.
cat > "$DEBIAN/prerm" <<'EOF'
#!/bin/sh
set -e
exit 0
EOF
chmod 0755 "$DEBIAN/prerm"

# conffiles: none — wrappers and units are owned by the package.

# Fix permissions inside the staging tree.
find "$STAGE" -type d -exec chmod 0755 {} +
find "$STAGE/usr/lib/$PKG_NAME" -type f -exec chmod 0644 {} +
find "$STAGE/usr/share" -type f -exec chmod 0644 {} +
find "$STAGE/etc" -type f -exec chmod 0644 {} +

mkdir -p "$DIST_DIR"
OUT="$DIST_DIR/${PKG_NAME}_${VERSION}_${ARCH}.deb"
dpkg-deb --root-owner-group --build "$STAGE" "$OUT" >/dev/null
echo "Built: $OUT"
ls -lh "$OUT"
