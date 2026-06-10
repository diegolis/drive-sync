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
  XDG_DATA_HOME="$BASE/data" XDG_CONFIG_HOME="$BASE/config" XDG_RUNTIME_DIR="$BASE/runtime" "$PY" -c "
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

# ===== SETUP =====
echo "==> Setup workspace en $BASE"
echo "==> Drive dir: ${REMOTE}:${DD}"

cat > "$BASE/jobs.json" <<EOF
{"jobs":[
  {"name":"bisync","localPath":"$BASE/local","remote":"$REMOTE","remotePath":"$DD/bisync"}
]}
EOF

run_app --import-config "$BASE/jobs.json" >/dev/null
BISYNC_ID=$(py_db 'print(c.execute("SELECT id FROM jobs WHERE name=?", ("bisync",)).fetchone()["id"])')
echo "    job id: bisync=$BISYNC_ID"

# ===== STRUCTURAL GUARDS (no requieren rclone) =====
echo
echo "==> Guards estructurales"

bridge "
try:
  b.save_job({'name':'dup','local_path':'$BASE/local','remote_name':'$REMOTE','remote_path':'$DD/bisync'})
  print('NORAISE')
except ValueError as e:
  print('RAISED' if 'Another sync' in str(e) else f'WRONG:{e}')
" | tee "$BASE/guard-dup.log" >/dev/null
assert "guard duplicate target rechaza job con misma combinación local↔drive" grep -q RAISED "$BASE/guard-dup.log"

# Nota: este guard aplica a remotes personales (Mi Drive). Si REMOTE es una
# Shared Drive, la raíz es un destino válido y este test no corresponde.
bridge "
try:
  b.save_job({'name':'root','local_path':'$BASE/local','remote_name':'$REMOTE','remote_path':''})
  print('NORAISE')
except ValueError as e:
  print('RAISED' if 'folder in Drive' in str(e) else f'WRONG:{e}')
" | tee "$BASE/guard-root.log" >/dev/null
assert "guard remote_path vacío (raíz de Mi Drive) rechazado" grep -q RAISED "$BASE/guard-root.log"

py_db "
mode = c.execute('SELECT mode FROM jobs WHERE id = $BISYNC_ID').fetchone()['mode']
print(mode)
assert mode == 'bisync'
" >/dev/null 2>&1 && PASS=$((PASS+1)) && printf "  \033[32m✓\033[0m %s\n" "todo job queda en modo bisync" \
  || { FAIL=$((FAIL+1)); FAILED_NAMES+=("todo job queda en modo bisync"); printf "  \033[31m✗\033[0m todo job queda en modo bisync\n"; }

# ===== PRIMERA SYNC = MERGE NO DESTRUCTIVO =====
echo
echo "==> Primera sync (merge automático, sin borrados)"
echo "loc v1" > "$BASE/local/loc.txt"
echo "cloud v1" | rclone rcat "${REMOTE}:${DD}/bisync/cloud.txt"

bridge "
res = b.run($BISYNC_ID, dry_run=False, resync=False)
print('AUTOMERGE' if res.get('resync') and res.get('ok') else f'WRONG:{res}')
" | tee "$BASE/first-sync.log" >/dev/null
assert "primera corrida se auto-promueve a merge (resync)" grep -q AUTOMERGE "$BASE/first-sync.log"
assert "merge inicial baja archivo cloud-only (no lo borra)" local_has cloud.txt
assert "merge inicial sube archivo local-only (no lo borra)" cloud_has bisync loc.txt

# ===== BISYNC NORMAL =====
echo
echo "==> Sincronización bidireccional"
echo "nuevo local" > "$BASE/local/new-local.txt"
run_agent --once "$BISYNC_ID" >/dev/null
assert "nuevo local sube" cloud_has bisync new-local.txt

echo "nuevo cloud" | rclone rcat "${REMOTE}:${DD}/bisync/new-cloud.txt"
run_agent --once "$BISYNC_ID" >/dev/null
assert "nuevo cloud baja" local_has new-cloud.txt

echo "loc v2" > "$BASE/local/loc.txt"
run_agent --once "$BISYNC_ID" >/dev/null
assert "modificación local sube" cloud_eq bisync loc.txt "loc v2"

echo "cloud v2" | rclone rcat "${REMOTE}:${DD}/bisync/cloud.txt"
run_agent --once "$BISYNC_ID" >/dev/null
assert "modificación cloud baja" local_eq cloud.txt "cloud v2"

rm "$BASE/local/new-local.txt"
run_agent --once "$BISYNC_ID" >/dev/null
assert "borrado local borra cloud" cloud_lacks bisync new-local.txt

rclone deletefile "${REMOTE}:${DD}/bisync/new-cloud.txt"
run_agent --once "$BISYNC_ID" >/dev/null
assert "borrado cloud borra local" local_lacks new-cloud.txt

# ===== FRENO --max-delete =====
echo
echo "==> Freno de seguridad: vaciar el local NO vacía el Drive"
run_agent --once "$BISYNC_ID" >/dev/null   # estado estable antes del desastre simulado
rm -rf "$BASE/local"; mkdir -p "$BASE/local"   # simula disco desmontado / carpeta vaciada
run_agent --once "$BISYNC_ID" >/dev/null
assert "cloud conserva loc.txt tras vaciar local" cloud_has bisync loc.txt
assert "cloud conserva cloud.txt tras vaciar local" cloud_has bisync cloud.txt

# ===== REPORTE =====
echo
TOTAL=$((PASS + FAIL))
echo "==> Resumen: $PASS / $TOTAL passed"
if [ $FAIL -gt 0 ]; then
  echo "Fallos:"
  for n in "${FAILED_NAMES[@]}"; do echo "  - $n"; done
  exit 1
fi
