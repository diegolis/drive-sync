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
  echo "Error: no encontré python3.10+. Instalá Python 3.10+ o pasá PYTHON=/ruta/al/python." >&2
  exit 1
fi
echo "Usando Python: $PYTHON_BIN"

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
    *) echo "Error: arquitectura no soportada para auto-instalación de rclone: $arch" >&2; return 1 ;;
  esac
  os="$(uname -s | tr '[:upper:]' '[:lower:]')"
  url="https://downloads.rclone.org/rclone-current-${os}-${rarch}.zip"
  tmp="$(mktemp -d)"
  echo "Descargando rclone desde $url ..."
  if ! curl -fsSL "$url" -o "$tmp/rclone.zip"; then
    echo "Error: no pude descargar rclone." >&2
    rm -rf "$tmp"
    return 1
  fi
  if ! command -v unzip >/dev/null 2>&1; then
    echo "Error: 'unzip' no está instalado. Instalalo (ej: sudo apt install unzip) y reintentá." >&2
    rm -rf "$tmp"
    return 1
  fi
  (cd "$tmp" && unzip -oq rclone.zip)
  bin="$(find "$tmp" -type f -name rclone | head -n1)"
  if [ -z "$bin" ]; then
    echo "Error: no encontré el binario rclone en el zip descargado." >&2
    rm -rf "$tmp"
    return 1
  fi
  install -m 0755 "$bin" "$BIN_DIR/rclone"
  rm -rf "$tmp"
  echo "rclone instalado en: $BIN_DIR/rclone"
}

RCLONE_BIN="$(pick_rclone)"
if [ -z "$RCLONE_BIN" ]; then
  echo "No encontré un rclone con soporte para bisync --resilient (>=1.66). Instalando uno actualizado en $BIN_DIR ..."
  install_rclone_to_local
  RCLONE_BIN="$BIN_DIR/rclone"
fi

if ! rclone_supports_resilient "$RCLONE_BIN"; then
  echo "Error: el rclone seleccionado ($RCLONE_BIN) no soporta --resilient." >&2
  exit 1
fi
echo "Usando rclone: $RCLONE_BIN ($("$RCLONE_BIN" version 2>/dev/null | head -1))"

if ! "$PYTHON_BIN" -c 'import webview' >/dev/null 2>&1; then
  cat >&2 <<MSG
Error: falta el paquete 'pywebview'.

En Ubuntu/Debian:
  sudo apt install python3-gi gir1.2-webkit2-4.1 libcairo2-dev
  $PYTHON_BIN -m pip install --user pywebview

(en otras distros, instalar el binding GTK + WebKit equivalente)
MSG
  exit 1
fi

HAS_TRAY=1
if ! "$PYTHON_BIN" -c 'import pystray, PIL' >/dev/null 2>&1; then
  echo "Advertencia: 'pystray' o 'Pillow' no instalados — el icono de la bandeja no estará disponible." >&2
  echo "  Para habilitarlo: $PYTHON_BIN -m pip install --user pystray Pillow" >&2
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
Comment=Sync de carpetas con Google Drive usando rclone
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
Comment=Icono de estado de Drive Sync
Exec=$BIN_DIR/drive-sync-desktop-tray
X-GNOME-Autostart-enabled=true
NoDisplay=false
Terminal=false
EOF
fi

echo "Instalado en: $BIN_DIR/drive-sync-desktop"
echo "Si $BIN_DIR no está en PATH, agregalo a tu shell."
echo "Para correr el agente manualmente: $BIN_DIR/drive-sync-desktop-agent"
echo "Para activarlo como servicio: systemctl --user enable --now $APP_ID-agent.service"
if [ "$HAS_TRAY" = "1" ]; then
  echo "Icono de bandeja autostart: $AUTOSTART_DIR/$APP_ID-tray.desktop"
  echo "Para arrancarlo ya: $BIN_DIR/drive-sync-desktop-tray &"
fi
