#!/usr/bin/env bash
# Story 10.1 — watchdog de reprise Q1 pendant l'incident endpoint galere.
# Discipline d'enveloppe : chaque sonde est UN appel compté au cap (journalisé),
# arrêt automatique si le budget restant passerait sous les ~60 appels requis
# par les 28 slots bloqués, et arrêt après 20 sondes DOWN consécutives (la main
# revient à l'owner). Reprise automatique seulement après 2 HEALTHY consécutifs.
set -u
REPO="$HOME/Desktop/wo/latent-imagination"
LOG="$REPO/data/landing/act2-pilot/genfam-q1/call-log.jsonl"
WATCHDOG_LOG="$REPO/data/landing/act2-pilot/genfam-q1/watchdog.log"
CAP=350; BUDGET_FLOOR=290; MAX_DOWN=20; INTERVAL=600
down=0; healthy=0; probes=0
ts() { date -u +%Y-%m-%dT%H:%M:%SZ; }
count_calls() { wc -l < "$LOG" | tr -d ' '; }

probe() {
  local body resp
  body='{"model":"MLX-Qwen3.5-35B-A3B-Claude-4.6-Opus-Reasoning-Distilled-bf16","messages":[{"role":"user","content":"Reply with the single word: pong"}],"temperature":0.7,"max_tokens":16}'
  resp=$(curl -sS --max-time 40 -X POST "https://ai.galere.org/v1/chat/completions" \
    -H "Content-Type: application/json" -H "User-Agent: opencode/1.0" \
    --data-binary "$body" 2>/dev/null)
  probes=$((probes+1))
  echo "$resp" | python3 -c "import json,sys
try: j=json.load(sys.stdin)
except Exception: sys.exit(1)
sys.exit(0 if 'choices' in j else 1)"
  local rc=$?
  local n; n=$(count_calls)
  python3 - "$n" "$rc" "$LOG" <<'PY'
import json, sys
from pathlib import Path
n, rc = int(sys.argv[1]), int(sys.argv[2])
row = {"ts": __import__("datetime").datetime.now(__import__("datetime").timezone.utc).isoformat(),
       "window":"gen-families-v1","quota":"q1","slot":f"probe-watchdog-{n+1}","attempt":0,
       "model":"MLX-Qwen3.5-35B-A3B-Claude-4.6-Opus-Reasoning-Distilled-bf16","campaign":"genfam-q1",
       "temperature":0.7,"note":"watchdog probe (1 appel compté au cap)",
       "result":"healthy" if rc==0 else "down","calls_used_window":n+1}
Path(sys.argv[3]).open("a").write(json.dumps(row)+"\n")
PY
  return $rc
}

echo "[$(ts)] watchdog démarré : intervalle ${INTERVAL}s, floor budget ${BUDGET_FLOOR}/${CAP}, max-down ${MAX_DOWN}" >> "$WATCHDOG_LOG"
while true; do
  n=$(count_calls)
  if [ "$n" -ge "$BUDGET_FLOOR" ]; then
    echo "[$(ts)] ARRÊT WATCHDOG : budget ${n}/${CAP} ≥ floor ${BUDGET_FLOOR} — la reprise des 28 slots revient à l'owner" >> "$WATCHDOG_LOG"
    exit 0
  fi
  if probe; then
    healthy=$((healthy+1)); down=0
    echo "[$(ts)] sonde HEALTHY (${healthy}/2), budget ${n}/${CAP}" >> "$WATCHDOG_LOG"
    if [ "$healthy" -ge 2 ]; then
      echo "[$(ts)] endpoint stable — reprise Q1" >> "$WATCHDOG_LOG"
      cd "$REPO" || exit 1
      nohup caffeinate -i uv run python scripts/act2/genfam_gen.py --quota q1 \
        > data/landing/act2-pilot/genfam-q1/gen-console-watchdog.log 2>&1 &
      echo "[$(ts)] genfam_gen relancé PID $!" >> "$WATCHDOG_LOG"
      exit 0
    fi
  else
    down=$((down+1)); healthy=0
    echo "[$(ts)] sonde DOWN (${down}/${MAX_DOWN}), budget ${n}/${CAP}" >> "$WATCHDOG_LOG"
    if [ "$down" -ge "$MAX_DOWN" ]; then
      echo "[$(ts)] ARRÊT WATCHDOG : ${MAX_DOWN} DOWN consécutifs — incident prolongé, décision owner" >> "$WATCHDOG_LOG"
      exit 0
    fi
  fi
  sleep "$INTERVAL"
done
