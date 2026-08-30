#!/usr/bin/env bash
# Lance un script Ghost/Act2 sur Kimsufi-standard (jamais en local sur le Mac).
# Usage : scripts/remote/run_remote.sh scripts/act2/p13_nulle.py --corpus p12 --perms 100 --workers 6
set -euo pipefail

HOST="Kimsufi-standard"
REMOTE_DIR="~/latent-imagination"
JOBS_DIR="$REMOTE_DIR/.remote-jobs"

if [ $# -lt 1 ]; then
  echo "Usage: $0 <script.py> [args...]" >&2
  exit 1
fi

SCRIPT="$1"; shift
JOB_NAME="$(basename "$SCRIPT" .py)-$(date +%Y%m%d-%H%M%S)"

echo "→ Sync du repo vers $HOST..."
rsync -az --exclude='.venv/' --exclude='.venv-embed/' --exclude='__pycache__/' --exclude='.git/' --exclude='.remote-jobs/' \
  "$(git -C "$(dirname "$0")/../.." rev-parse --show-toplevel)/" "$HOST:$REMOTE_DIR/"

echo "→ Lancement distant (détaché, survit à la déconnexion SSH) : $SCRIPT $*"
ssh "$HOST" bash -s -- "$REMOTE_DIR" "$JOBS_DIR" "$JOB_NAME" "$SCRIPT" "$@" << 'REMOTE'
set -euo pipefail
REMOTE_DIR="$1"; JOBS_DIR="$2"; JOB_NAME="$3"; SCRIPT="$4"; shift 4
mkdir -p "$JOBS_DIR"
cd "$REMOTE_DIR"
if [ ! -d .venv ]; then
  uv sync
fi
nohup .venv/bin/python "$SCRIPT" "$@" > "$JOBS_DIR/$JOB_NAME.log" 2>&1 < /dev/null &
PID=$!
disown
echo "$PID" > "$JOBS_DIR/$JOB_NAME.pid"
echo "job=$JOB_NAME pid=$PID log=$JOBS_DIR/$JOB_NAME.log"
REMOTE

echo
echo "Suivi : ssh $HOST 'tail -f $JOBS_DIR/$JOB_NAME.log'"
echo "Jobs en cours : ssh $HOST 'for f in $JOBS_DIR/*.pid; do p=\$(cat \$f); ps -p \$p -o pid,etime,cmd --no-headers 2>/dev/null && echo \" -> \$f\"; done'"
