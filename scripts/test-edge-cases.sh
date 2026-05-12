#!/usr/bin/env bash
set -uo pipefail

# Validación E2E de edge cases contra Drive real.
# Crea un workspace aislado bajo /tmp y un dir Drive timestamped, los limpia al salir.
# No toca tu DB ni tus jobs reales.
#
# Requiere: drive-sync-desktop instalado, rclone con remote 'drive', python3.10+.
# Uso: bash scripts/test-edge-cases.sh
#       NO_CLEANUP=1 bash scripts/test-edge-cases.sh   (deja artefactos para inspección)

PY="${PYTHON:-/usr/bin/python3.12}"
REMOTE="${REMOTE:-drive}"
BIN="${HOME}/.local/bin/drive-sync-desktop"
AGENT="${HOME}/.local/bin/drive-sync-desktop-agent"
APP_PATH="${HOME}/.local/share/drive-sync-desktop/app"

[ -x "$BIN" ] || { echo "Falta $BIN. Corré install.sh primero." >&2; exit 1; }
"$PY" -c 'import sys; sys.exit(0 if sys.version_info >= (3,10) else 1)' || { echo "Necesito python3.10+." >&2; exit 1; }
rclone listremotes | grep -q "^${REMOTE}:" || { echo "Remote '$REMOTE' no existe en rclone." >&2; exit 1; }

TS=$(date +%s)
BASE="/tmp/dsds-edge-$TS"
DD="DriveSyncEdge-$TS"
mkdir -p "$BASE/local" "$BASE/data" "$BASE/config" "$BASE/runtime"

PASS=0; FAIL=0; FAILED_NAMES=()

cleanup() {
  if [ "${NO_CLEANUP:-}" = "1" ]; then
    echo "(NO_CLEANUP=1) artefactos en $BASE y drive:$DD"
    return
  fi
  rclone purge "${REMOTE}:${DD}" 2>/dev/null
  rm -rf "$BASE"
}
trap cleanup EXIT

run_agent()  { XDG_DATA_HOME="$BASE/data" XDG_CONFIG_HOME="$BASE/config" XDG_RUNTIME_DIR="$BASE/runtime" "$AGENT" "$@" 2>&1; }
run_app()    { XDG_DATA_HOME="$BASE/data" XDG_CONFIG_HOME="$BASE/config" XDG_RUNTIME_DIR="$BASE/runtime" "$BIN" "$@" 2>&1; }

py_db() {
  XDG_DATA_HOME="$BASE/data" "$PY" -c "
import sys, sqlite3, os
sys.path.insert(0, '$APP_PATH')
db = '$BASE/data/drive-sync-desktop/app.db'
c = sqlite3.connect(db); c.row_factory = sqlite3.Row
$1
"
}

bridge() {
  XDG_DATA_HOME="$BASE/data" XDG_CONFIG_HOME="$BASE/config" "$PY" -c "
import sys, json
sys.path.insert(0, '$APP_PATH')
from drive_sync_desktop.bridge import Bridge
b = Bridge()
$1
"
}

assert() {
  local name="$1"; shift
  if "$@" >/dev/null 2>&1; then
    printf "  \033[32m✓\033[0m %s\n" "$name"
    PASS=$((PASS+1))
  else
    printf "  \033[31m✗\033[0m %s\n" "$name"
    FAIL=$((FAIL+1))
    FAILED_NAMES+=("$name")
  fi
}

cloud_has() { rclone lsf "${REMOTE}:${DD}/$1/$2" 2>/dev/null | grep -q .; }
cloud_lacks() { ! cloud_has "$1" "$2"; }
local_has()  { test -f "$BASE/local/$1"; }
local_lacks(){ ! test -e "$BASE/local/$1"; }
cloud_eq()   { test "$(rclone cat "${REMOTE}:${DD}/$1/$2")" = "$3"; }
local_eq()   { test "$(cat "$BASE/local/$1")" = "$2"; }

set_mode_field() {
  py_db "
c.execute(\"UPDATE jobs SET $2 WHERE id = $1\")
c.commit()
"
}

# ===== SETUP =====
echo "==> Setup workspace en $BASE"
echo "==> Drive dir: ${REMOTE}:${DD}"

cat > "$BASE/jobs.json" <<EOF
{"jobs":[
  {"name":"copy","localPath":"$BASE/local","remote":"$REMOTE","remotePath":"$DD/copy","mode":"copy","dryRunRequired":false},
  {"name":"sync","localPath":"$BASE/local","remote":"$REMOTE","remotePath":"$DD/sync","mode":"sync","dryRunRequired":false},
  {"name":"bisync","localPath":"$BASE/local","remote":"$REMOTE","remotePath":"$DD/bisync","mode":"bisync","dryRunRequired":false}
]}
EOF

run_app --import-config "$BASE/jobs.json" >/dev/null
read COPY_ID SYNC_ID BISYNC_ID < <(py_db '
ids = []
for n in ["copy", "sync", "bisync"]:
    ids.append(c.execute("SELECT id FROM jobs WHERE name=?", (n,)).fetchone()["id"])
print(*ids)
')
echo "    job ids: copy=$COPY_ID  sync=$SYNC_ID  bisync=$BISYNC_ID"

# ===== STRUCTURAL GUARDS (no requieren rclone) =====
echo
echo "==> Guards estructurales"

bridge "
import json
try:
  b.save_job({'name':'dup','local_path':'$BASE/local','remote_name':'$REMOTE','remote_path':'$DD/copy','mode':'copy'})
  print('NORAISE')
except ValueError as e:
  print('RAISED' if 'otra sync' in str(e) else f'WRONG:{e}')
" | tee "$BASE/guard-dup.log" >/dev/null
assert "guard duplicate target rechaza job con misma combinación local↔drive" grep -q RAISED "$BASE/guard-dup.log"

bridge "
res = b.run($BISYNC_ID, dry_run=False, resync=False)
print('NEEDS_RESYNC' if res.get('needs_resync') else f'WRONG:{res}')
" | tee "$BASE/guard-bi.log" >/dev/null
assert "guard bisync sin baseline → needs_resync" grep -q NEEDS_RESYNC "$BASE/guard-bi.log"

# ===== MODO COPY =====
echo
echo "==> Modo copy"
echo "alpha v1" > "$BASE/local/alpha.txt"
run_agent --once "$COPY_ID" >/dev/null
assert "copy: nuevo en local sube a cloud" cloud_has copy alpha.txt
assert "copy: contenido coincide en cloud" cloud_eq copy alpha.txt "alpha v1"

echo "alpha v2" > "$BASE/local/alpha.txt"
run_agent --once "$COPY_ID" >/dev/null
assert "copy: modificación local actualiza cloud" cloud_eq copy alpha.txt "alpha v2"

echo "cloud-only" | rclone rcat "${REMOTE}:${DD}/copy/cloud-only.txt"
run_agent --once "$COPY_ID" >/dev/null
assert "copy: archivo creado en cloud no baja al local" local_lacks cloud-only.txt
assert "copy: archivo creado en cloud sigue en cloud" cloud_has copy cloud-only.txt

rm "$BASE/local/alpha.txt"
run_agent --once "$COPY_ID" >/dev/null
assert "copy: borrado local NO borra cloud" cloud_has copy alpha.txt

# Limpiar local antes del próximo grupo
rm -rf "$BASE/local"; mkdir -p "$BASE/local"

# ===== MODO SYNC =====
echo
echo "==> Modo sync (espejo)"
echo "x v1" > "$BASE/local/x.txt"
run_agent --once "$SYNC_ID" >/dev/null
assert "sync: nuevo en local sube a cloud" cloud_has sync x.txt

echo "y" | rclone rcat "${REMOTE}:${DD}/sync/y.txt"
run_agent --once "$SYNC_ID" >/dev/null
assert "sync: archivo cloud-only se BORRA en cloud (espejo)" cloud_lacks sync y.txt
assert "sync: archivo local sigue en cloud" cloud_has sync x.txt

rm "$BASE/local/x.txt"
run_agent --once "$SYNC_ID" >/dev/null
assert "sync: borrado local borra cloud" cloud_lacks sync x.txt

rm -rf "$BASE/local"; mkdir -p "$BASE/local"

# ===== MODO BISYNC =====
echo
echo "==> Modo bisync"
echo "loc v1" > "$BASE/local/loc.txt"
echo "cloud v1" | rclone rcat "${REMOTE}:${DD}/bisync/cloud.txt"
run_agent --once "$BISYNC_ID" --resync >/dev/null
assert "bisync: resync inicial baja archivo cloud-only" local_has cloud.txt
assert "bisync: resync inicial sube archivo local-only" cloud_has bisync loc.txt

echo "nuevo local" > "$BASE/local/new-local.txt"
run_agent --once "$BISYNC_ID" >/dev/null
assert "bisync: nuevo local sube" cloud_has bisync new-local.txt

echo "nuevo cloud" | rclone rcat "${REMOTE}:${DD}/bisync/new-cloud.txt"
run_agent --once "$BISYNC_ID" >/dev/null
assert "bisync: nuevo cloud baja" local_has new-cloud.txt

echo "loc v2" > "$BASE/local/loc.txt"
run_agent --once "$BISYNC_ID" >/dev/null
assert "bisync: modificación local sube" cloud_eq bisync loc.txt "loc v2"

echo "cloud v2" | rclone rcat "${REMOTE}:${DD}/bisync/cloud.txt"
run_agent --once "$BISYNC_ID" >/dev/null
assert "bisync: modificación cloud baja" local_eq cloud.txt "cloud v2"

rm "$BASE/local/new-local.txt"
run_agent --once "$BISYNC_ID" >/dev/null
assert "bisync: borrado local borra cloud" cloud_lacks bisync new-local.txt

rclone deletefile "${REMOTE}:${DD}/bisync/new-cloud.txt"
run_agent --once "$BISYNC_ID" >/dev/null
assert "bisync: borrado cloud borra local" local_lacks new-cloud.txt

# ===== REPORTE =====
echo
TOTAL=$((PASS + FAIL))
echo "==> Resumen: $PASS / $TOTAL passed"
if [ $FAIL -gt 0 ]; then
  echo "Fallos:"
  for n in "${FAILED_NAMES[@]}"; do echo "  - $n"; done
  exit 1
fi
