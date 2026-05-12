#!/bin/sh
set -eu

APP_ID="drive-sync-desktop"
PREFIX="${PREFIX:-$HOME/.local}"
SHARE_DIR="$PREFIX/share/$APP_ID"
BIN_DIR="$PREFIX/bin"
APPS_DIR="${APPS_DIR:-$HOME/.local/share/applications}"
SYSTEMD_USER_DIR="${SYSTEMD_USER_DIR:-$HOME/.config/systemd/user}"
APP_DIR="$(CDPATH= cd -- "$(dirname -- "$0")" && pwd)"

PYTHON_BIN="${PYTHON:-}"
if [ -z "$PYTHON_BIN" ]; then
  for candidate in /usr/bin/python3.12 /usr/bin/python3.11 /usr/bin/python3.10 python3.12 python3.11 python3.10 python3; do
    bin="$(command -v "$candidate" 2>/dev/null || true)"
    if [ -n "$bin" ] && "$bin" -c 'import sys; sys.exit(0 if sys.version_info >= (3,10) else 1)' >/dev/null 2>&1; then
      PYTHON_BIN="$bin"
      break
    fi
  done
fi
if [ -z "$PYTHON_BIN" ]; then
  echo "Error: could not find python3.10+. Install Python 3.10+ or pass PYTHON=/path/to/python." >&2
  exit 1
fi
echo "Using Python: $PYTHON_BIN"

mkdir -p "$BIN_DIR"

rclone_supports_resilient() {
  "$1" bisync --help 2>/dev/null | grep -q -- "--resilient"
}

pick_rclone() {
  best=""
  for cand in "$BIN_DIR/rclone" $(command -v rclone 2>/dev/null) /usr/local/bin/rclone /usr/bin/rclone; do
    [ -n "$cand" ] && [ -x "$cand" ] || continue
    if rclone_supports_resilient "$cand"; then
      best="$cand"
      break
    fi
  done
  echo "$best"
}

install_rclone_to_local() {
  arch="$(uname -m)"
  case "$arch" in
    x86_64|amd64) rarch="amd64" ;;
    aarch64|arm64) rarch="arm64" ;;
    armv7l|armv6l) rarch="arm" ;;
    *) echo "Error: unsupported architecture for rclone auto-install: $arch" >&2; return 1 ;;
  esac
  os="$(uname -s | tr '[:upper:]' '[:lower:]')"
  url="https://downloads.rclone.org/rclone-current-${os}-${rarch}.zip"
  tmp="$(mktemp -d)"
  echo "Downloading rclone from $url ..."
  if ! curl -fsSL "$url" -o "$tmp/rclone.zip"; then
    echo "Error: could not download rclone." >&2
    rm -rf "$tmp"
    return 1
  fi
  if ! command -v unzip >/dev/null 2>&1; then
    echo "Error: 'unzip' is not installed. Install it (e.g. sudo apt install unzip) and retry." >&2
    rm -rf "$tmp"
    return 1
  fi
  (cd "$tmp" && unzip -oq rclone.zip)
  bin="$(find "$tmp" -type f -name rclone | head -n1)"
  if [ -z "$bin" ]; then
    echo "Error: rclone binary not found in the downloaded zip." >&2
    rm -rf "$tmp"
    return 1
  fi
  install -m 0755 "$bin" "$BIN_DIR/rclone"
  rm -rf "$tmp"
  # Mark as installed by us so uninstall.sh knows it can remove it.
  : > "$BIN_DIR/.rclone.managed-by-drive-sync"
  echo "rclone installed at: $BIN_DIR/rclone"
}

RCLONE_BIN="$(pick_rclone)"
if [ -z "$RCLONE_BIN" ]; then
  echo "No rclone with --resilient support found (>=1.66). Installing an up-to-date one in $BIN_DIR ..."
  install_rclone_to_local
  RCLONE_BIN="$BIN_DIR/rclone"
fi

if ! rclone_supports_resilient "$RCLONE_BIN"; then
  echo "Error: selected rclone ($RCLONE_BIN) does not support --resilient." >&2
  exit 1
fi
echo "Using rclone: $RCLONE_BIN ($("$RCLONE_BIN" version 2>/dev/null | head -1))"

if ! "$PYTHON_BIN" -c 'import webview' >/dev/null 2>&1; then
  cat >&2 <<MSG
Error: 'pywebview' package missing.

On Ubuntu/Debian:
  sudo apt install python3-gi gir1.2-webkit2-4.1 libcairo2-dev
  $PYTHON_BIN -m pip install --user pywebview

(on other distros, install the equivalent GTK + WebKit bindings)
MSG
  exit 1
fi

HAS_TRAY=1
if ! "$PYTHON_BIN" -c 'import pystray, PIL' >/dev/null 2>&1; then
  echo "Warning: 'pystray' or 'Pillow' not installed — the tray icon will not be available." >&2
  echo "  To enable it: $PYTHON_BIN -m pip install --user pystray Pillow" >&2
  HAS_TRAY=0
fi

mkdir -p "$SHARE_DIR" "$BIN_DIR"
rm -rf "$SHARE_DIR/app"
mkdir -p "$SHARE_DIR/app"
cp -R "$APP_DIR/drive_sync_desktop" "$SHARE_DIR/app/"
cp "$APP_DIR/main.py" "$SHARE_DIR/app/"
cp "$APP_DIR/uninstall.sh" "$SHARE_DIR/"

cat > "$BIN_DIR/drive-sync-desktop" <<EOF
#!/bin/sh
export PYTHONPATH="$SHARE_DIR/app"
export RCLONE_PATH="\${RCLONE_PATH:-$RCLONE_BIN}"
exec "$PYTHON_BIN" "$SHARE_DIR/app/main.py" "\$@"
EOF
chmod +x "$BIN_DIR/drive-sync-desktop"

cat > "$BIN_DIR/drive-sync-desktop-agent" <<EOF
#!/bin/sh
export PYTHONPATH="$SHARE_DIR/app"
export RCLONE_PATH="\${RCLONE_PATH:-$RCLONE_BIN}"
exec "$PYTHON_BIN" "$SHARE_DIR/app/main.py" --agent "\$@"
EOF
chmod +x "$BIN_DIR/drive-sync-desktop-agent"

cat > "$BIN_DIR/drive-sync-desktop-tray" <<EOF
#!/bin/sh
export PYTHONPATH="$SHARE_DIR/app"
export RCLONE_PATH="\${RCLONE_PATH:-$RCLONE_BIN}"
exec "$PYTHON_BIN" "$SHARE_DIR/app/main.py" --tray "\$@"
EOF
chmod +x "$BIN_DIR/drive-sync-desktop-tray"

if [ "$(uname -s)" = "Linux" ]; then
  mkdir -p "$APPS_DIR"
  cat > "$APPS_DIR/$APP_ID.desktop" <<EOF
[Desktop Entry]
Type=Application
Name=Drive Sync Desktop
Comment=Sync folders with Google Drive using rclone
Exec=$BIN_DIR/drive-sync-desktop
Terminal=false
Categories=Utility;
EOF
fi

if command -v systemctl >/dev/null 2>&1 && systemctl --user >/dev/null 2>&1; then
  mkdir -p "$SYSTEMD_USER_DIR"
  cat > "$SYSTEMD_USER_DIR/$APP_ID-agent.service" <<EOF
[Unit]
Description=Drive Sync Desktop Agent

[Service]
Environment=RCLONE_PATH=$RCLONE_BIN
ExecStart=$BIN_DIR/drive-sync-desktop-agent --interval-seconds 30
Restart=always
RestartSec=5

[Install]
WantedBy=default.target
EOF
  systemctl --user daemon-reload || true
fi

AUTOSTART_DIR="${AUTOSTART_DIR:-$HOME/.config/autostart}"
if [ "$HAS_TRAY" = "1" ]; then
  mkdir -p "$AUTOSTART_DIR"
  cat > "$AUTOSTART_DIR/$APP_ID-tray.desktop" <<EOF
[Desktop Entry]
Type=Application
Name=Drive Sync Tray
Comment=Drive Sync status icon
Exec=$BIN_DIR/drive-sync-desktop-tray
X-GNOME-Autostart-enabled=true
NoDisplay=false
Terminal=false
EOF
fi

echo "Installed at: $BIN_DIR/drive-sync-desktop"
echo "If $BIN_DIR is not in your PATH, add it to your shell."
echo "To run the agent manually: $BIN_DIR/drive-sync-desktop-agent"
echo "To enable it as a service: systemctl --user enable --now $APP_ID-agent.service"
if [ "$HAS_TRAY" = "1" ]; then
  echo "Tray autostart entry: $AUTOSTART_DIR/$APP_ID-tray.desktop"
  echo "To start it now: $BIN_DIR/drive-sync-desktop-tray &"
fi
