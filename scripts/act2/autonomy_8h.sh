#!/bin/bash
# Autonomie 8h — boucles génération→label→embed→pool→éval (nuit 2026-08-14).
# Pré-enregistré : governance/act2/budget-v1.toml (entrée "nuit").
# Journal : data/landing/act2-pilot/autonomy-8h/journal.md (+ timeline.log).
# Toutes les phases sont idempotentes ; en cas d'échec d'une phase le superviseur
# logue et tente la relance une fois, puis continue si possible.
set -u
ROOT=~/Desktop/wo/latent-imagination
PILOT=$ROOT/data/landing/act2-pilot
JDIR=$PILOT/autonomy-8h
NODE=ghost-mcp
START=$(date +%s)
DEADLINE=$((START + 8*3600))
mkdir -p "$JDIR"
JOURNAL=$JDIR/journal.md
touch "$JOURNAL"

log() { echo "$(date '+%H:%M:%S') $*" | tee -a "$JDIR/timeline.log"; }
journal() { echo "$*" >> "$JOURNAL"; }
now() { date +%s; }
remaining_s() { echo $((DEADLINE - $(now))); }
sshq() { ssh -o ServerAliveInterval=30 -o ServerAliveCountMax=4 \
             -o ConnectTimeout=15 $NODE "$@"; }

journal ""
journal "## Run autonome 8h — démarré $(date '+%Y-%m-%d %H:%M'), fin prévue $(date -r $DEADLINE '+%H:%M')"

# ---------- P0 : attendre la fin du juge S13 (lancé avant le superviseur) ----------
log "P0 attente S13-judge"
i=0
while [ ! -f "$PILOT/s13-judge.json" ] && [ $(now) -lt $((START + 5400)) ]; do
  if ! pgrep -f s13_llm_judge.py >/dev/null 2>&1; then
    log "P0 ⚠️ process S13 mort sans artefact — relance (reprise idempotente)"
    cd "$ROOT" && nohup python3 scripts/act2/s13_llm_judge.py \
        >> "$PILOT/s13-judge/run.log" 2>&1 &
    sleep 60
  fi
  sleep 120; i=$((i+1))
  [ $((i % 5)) -eq 0 ] && log "P0 S13 en cours ($(ls "$PILOT/s13-judge/raw" 2>/dev/null | grep -c probability.json)/177)"
done
if [ -f "$PILOT/s13-judge.json" ]; then
  log "P0 S13 terminé"
  { echo ""; echo "### S13 — juge Qwen3.8-2.4T zero-shot (terminé $(date '+%H:%M'))"; \
    python3 -c "
import json
d = json.load(open('$PILOT/s13-judge.json'))
j = d['judge']; g = d['recomputed_instruments']
print('juge : AUC %.3f | acc100 %.3f | cov@≥0.95 %.0f %%' % (j['auc'], j['acc100'], j['max_cov']*100))
print('rappel v7 GOLD %.3f / GxF strict %.3f' % (g['v7_gold']['auc'], g['v7_gxf_strict']['auc']))
print('strata:', json.dumps(d.get('strata', {})))
print('pairing vs GxF:', json.dumps(d.get('pairing_vs_gxf', {})))
print('attempts:', json.dumps(d.get('attempts_hist', {})))"; } >> "$JOURNAL"
else
  journal "⚠️ S13 : pas d'artefact après 90 min (ou process mort) — poursuite ; reprise manuelle possible (le run est idempotent)."
fi

# ---------- P1 : attendre les pulls docker (lancés en // avant le superviseur) ----------
log "P1 attente pulls docker node"
while ! sshq 'grep -q PULL-DONE ~/s14-pull.log 2>/dev/null'; do
  [ $(remaining_s) -lt $((6*3600)) ] && { log "P1 pulls pas finis après 2h — on avance"; break; }
  sleep 180
done
sshq 'grep -c "Pull complete\|up to date\|already exists" ~/s14-pull.log 2>/dev/null; echo ---; grep -ci error ~/s14-pull.log 2>/dev/null' > "$JDIR/pull-counts.txt" 2>&1
log "P1 pulls: $(tr '\n' ' ' < "$JDIR/pull-counts.txt")"

GATE=FAIL
CYCLE=0
while [ $CYCLE -lt 2 ]; do
  CYCLE=$((CYCLE+1))
  DS=$((2*CYCLE-1))   # draw start : 1 puis 3
  if [ $CYCLE -eq 1 ]; then CLOGNAME=call-log.jsonl; SCAP=350; else CLOGNAME=call-log-w2.jsonl; SCAP=250; fi
  log "===== CYCLE $CYCLE (tirages d$DS-d$((DS+1)), fenêtre $CLOGNAME cap $SCAP) — reste $(( $(remaining_s)/3600 ))h$(( ($(remaining_s)%3600)/60 )) ====="
  if [ $CYCLE -eq 2 ] && [ $(remaining_s) -lt $((5*3600 + 15*60)) ]; then
    journal ""; journal "**Cycle 2 abandonné : temps restant insuffisant (< 5h15).**"
    break
  fi

  # ---- génération (Mac) ----
  GLOG=$PILOT/s14-gen/run-c$CYCLE.log
  mkdir -p "$PILOT/s14-gen"
  if grep -q "== S14-G" "$GLOG" 2>/dev/null; then
    log "C$CYCLE gen déjà faite — skip"
  else
    log "C$CYCLE S14-G génération"
    cd "$ROOT"
    S14_DRAW_START=$DS S14_LOGNAME=$CLOGNAME S14_CAP=$SCAP \
      S14_DEADLINE=$((DEADLINE - 3600)) \
      nohup python3 scripts/act2/s14_gen.py >> "$GLOG" 2>&1 &
    GENPID=$!
    relances=0
    while ! grep -q "== S14-G" "$GLOG" 2>/dev/null; do
      sleep 300
      m=$(ls "$PILOT/s14-gen/results"/*/meta.json 2>/dev/null | wc -l | tr -d ' ')
      c=$(wc -l < "$PILOT/s14-gen/$CLOGNAME" 2>/dev/null | tr -d ' ')
      log "C$CYCLE gen: metas $m | calls fenêtre $c"
      if ! kill -0 $GENPID 2>/dev/null && ! grep -q "== S14-G" "$GLOG" 2>/dev/null; then
        relances=$((relances+1))
        if [ $relances -gt 3 ]; then log "C$CYCLE ⚠️ gen : 3 relances échouées — abandon phase gen"; break; fi
        log "C$CYCLE ⚠️ process gen mort — relance $relances (reprise idempotente)"
        S14_DRAW_START=$DS S14_LOGNAME=$CLOGNAME S14_CAP=$SCAP \
          S14_DEADLINE=$((DEADLINE - 3600)) \
          nohup python3 scripts/act2/s14_gen.py >> "$GLOG" 2>&1 &
        GENPID=$!
      fi
      [ $(remaining_s) -lt $((3*3600)) ] && { log "C$CYCLE timeout mou gen"; kill $GENPID 2>/dev/null; sleep 10; break; }
    done
    tail -2 "$GLOG" >> "$JDIR/timeline.log"
  fi
  { echo ""; echo "### Cycle $CYCLE — S14-G (terminé $(date '+%H:%M'))"; \
    grep "== S14-G" "$PILOT/s14-gen/run.log" "$GLOG" 2>/dev/null | tail -2; } >> "$JOURNAL"

  [ $(remaining_s) -lt $((2*3600 + 30*60)) ] && { journal "⚠️ arrêt avant label (temps)."; break; }

  # ---- sync + labellisation docker (node) ----
  log "C$CYCLE rsync résultats → node"
  sshq 'mkdir -p ~/latent-imagination/data/landing/act2-pilot/s14-gen/results' || true
  rsync -a --include="*/" --include="patch.diff" --include="meta.json" \
        --include="task.json" --include="run-result.json" --exclude="*" \
        "$PILOT/s14-gen/results/" \
        "$NODE:latent-imagination/data/landing/act2-pilot/s14-gen/results/" \
        >> "$JDIR/rsync.log" 2>&1 \
    || log "C$CYCLE ⚠️ rsync aller échoué — retry dans 60s" && sleep 60 && \
  rsync -a --include="*/" --include="patch.diff" --include="meta.json" \
        --include="task.json" --include="run-result.json" --exclude="*" \
        "$PILOT/s14-gen/results/" \
        "$NODE:latent-imagination/data/landing/act2-pilot/s14-gen/results/" \
        >> "$JDIR/rsync.log" 2>&1
  scp -q "$ROOT/scripts/act2/s12_label_exec.py" "$NODE:latent-imagination/scripts/act2/s12_label_exec.py"
  log "C$CYCLE S14-L labellisation docker (node)"
  LLOG="s14-label-c$CYCLE.log"
  sshq "cd ~/latent-imagination && nohup env S_LABEL_STAGE=s14-gen python3 scripts/act2/s12_label_exec.py >> data/landing/act2-pilot/$LLOG 2>&1 < /dev/null &" || log "C$CYCLE ⚠️ lancement label échoué"
  sleep 20
  while ! sshq "grep -q '== S14-L' ~/latent-imagination/data/landing/act2-pilot/$LLOG 2>/dev/null"; do
    sleep 300
    if ! sshq 'pgrep -f s12_label_exec.py >/dev/null 2>&1'; then
      log "C$CYCLE ⚠️ label mort sans marker — relance (idempotent)"
      sshq "cd ~/latent-imagination && nohup env S_LABEL_STAGE=s14-gen python3 scripts/act2/s12_label_exec.py >> data/landing/act2-pilot/$LLOG 2>&1 < /dev/null &" || true
    fi
    n=$(sshq "grep -c 'apply=' ~/latent-imagination/data/landing/act2-pilot/$LLOG 2>/dev/null" || echo "?")
    log "C$CYCLE label: lignes log $n"
    [ $(remaining_s) -lt $((90*60)) ] && { log "C$CYCLE timeout label — suite avec l'existant"; break; }
  done
  rsync -a --include="*/" --include="run-result.json" --exclude="*" \
        "$NODE:latent-imagination/data/landing/act2-pilot/s14-gen/results/" \
        "$PILOT/s14-gen/results/" >> "$JDIR/rsync.log" 2>&1
  rsync -a "$NODE:latent-imagination/data/landing/act2-pilot/$LLOG" \
        "$PILOT/$LLOG" >> "$JDIR/rsync.log" 2>&1
  { echo ""; echo "### Cycle $CYCLE — S14-L (terminé $(date '+%H:%M'))"; \
    grep "== S14-L" "$PILOT/$LLOG" 2>/dev/null | tail -1; } >> "$JOURNAL"

  # ---- pool + embed uxc + éval ----
  log "C$CYCLE construction pool v8"
  cd "$ROOT"
  python3 scripts/act2/s14_pool.py --stage pool >> "$JDIR/pool.log" 2>&1 || log "C$CYCLE ⚠️ pool build échoué"
  { echo ""; echo "### Cycle $CYCLE — pool v8 (construit $(date '+%H:%M'))"; \
    python3 -c "
import json; d=json.load(open('$PILOT/s14-pool-build.json'))
print({k:v for k,v in d.items() if k!='skipped_detail'})" 2>/dev/null; } >> "$JOURNAL"
  N_V8=$(python3 -c "import json;print(len(json.load(open('$PILOT/latent-pool-v8.json'))))" 2>/dev/null || echo 0)
  if [ "${N_V8:-0}" -le 177 ]; then
    log "C$CYCLE ⚠️ pool vide — re-vérif rsync/label puis 2e tentative"
    RRL=$(ls "$PILOT/s14-gen/results"/*/run-result.json 2>/dev/null | wc -l | tr -d ' ')
    journal "⚠️ cycle $CYCLE : pool v8 sans nouvelles lignes à la 1re tentative (run-results locaux: $RRL) — 2e tentative label."
    sshq 'mkdir -p ~/latent-imagination/data/landing/act2-pilot/s14-gen/results' || true
    rsync -a --include="*/" --include="patch.diff" --include="meta.json" \
          --include="task.json" --exclude="*" \
          "$PILOT/s14-gen/results/" \
          "$NODE:latent-imagination/data/landing/act2-pilot/s14-gen/results/" \
          >> "$JDIR/rsync.log" 2>&1
    LLOG2="s14-label-c$CYCLE-r2.log"
    sshq "cd ~/latent-imagination && nohup env S_LABEL_STAGE=s14-gen python3 scripts/act2/s12_label_exec.py >> data/landing/act2-pilot/$LLOG2 2>&1 < /dev/null &" || true
    while ! sshq "grep -q '== S14-L' ~/latent-imagination/data/landing/act2-pilot/$LLOG2 2>/dev/null"; do
      sleep 300
      [ $(remaining_s) -lt $((90*60)) ] && break
    done
    rsync -a --include="*/" --include="run-result.json" --exclude="*" \
          "$NODE:latent-imagination/data/landing/act2-pilot/s14-gen/results/" \
          "$PILOT/s14-gen/results/" >> "$JDIR/rsync.log" 2>&1
    python3 scripts/act2/s14_pool.py --stage pool >> "$JDIR/pool.log" 2>&1
    N_V8=$(python3 -c "import json;print(len(json.load(open('$PILOT/latent-pool-v8.json'))))" 2>/dev/null || echo 0)
    [ "${N_V8:-0}" -le 177 ] && { journal "⚠️ pool v8 toujours vide après retry ($N_V8) — arrêt de la boucle."; break; }
  fi
  log "C$CYCLE embeds node (uxc puis Qwen-7B) + éval"
  rsync -a "$PILOT/latent-pool-v7.npz" "$PILOT/latent-pool-v7.json" "$PILOT/latent-pool-v8.json" \
        "$NODE:latent-imagination/data/landing/act2-pilot/" >> "$JDIR/rsync.log" 2>&1
  scp -q "$ROOT/scripts/act2/s14_pool.py" "$ROOT/scripts/act2/s11_ext_pool.py" "$ROOT/scripts/act2/s14_qwen_embed.py" \
        "$NODE:latent-imagination/scripts/act2/"
  sshq 'cd ~/latent-imagination && .venv/bin/python scripts/act2/s14_pool.py --stage embed' \
        >> "$JDIR/embed.log" 2>&1 || log "C$CYCLE ⚠️ embed uxc échoué"
  sshq 'cd ~/latent-imagination && .venv/bin/python scripts/act2/s14_qwen_embed.py data/landing/act2-pilot/latent-pool-v8.json data/landing/act2-pilot/latent-pool-v8-qwen7b-last.npz' \
        >> "$JDIR/embed.log" 2>&1 || log "C$CYCLE ⚠️ embed Qwen échoué (non bloquant)"
  rsync -a "$NODE:latent-imagination/data/landing/act2-pilot/latent-pool-v8.npz" \
        "$NODE:latent-imagination/data/landing/act2-pilot/latent-pool-v8-qwen7b-last.npz" \
        "$PILOT/" >> "$JDIR/rsync.log" 2>&1
  python3 scripts/act2/s14_pool.py --stage eval >> "$JDIR/eval.log" 2>&1 || log "C$CYCLE ⚠️ éval échouée"
  { echo ""; echo "### Cycle $CYCLE — éval v8 LOAO-strict ($(date '+%H:%M'))"; \
    python3 -c "
import json; d=json.load(open('$PILOT/s14-pool-v8-eval.json'))
for k,v in d['variants'].items():
    print('%s : AUC %.3f | acc100 %.3f | cov@≥0.95 %.0f %%' % (k, v['auc'], v['acc100'], v['max_cov']*100))
print('queue top25:'); print(json.dumps(d.get('queue_top25_gxf', {}), indent=1))
print('gate_v2:', d['gate_v2'])" 2>/dev/null; } >> "$JOURNAL"
  python3 scripts/act2/s14_extras.py >> "$JDIR/extras.log" 2>&1 || log "C$CYCLE ⚠️ extras échoués (non bloquant)"
  [ -f "$PILOT/s14-extras.json" ] && { echo ""; echo "### Cycle $CYCLE — extras (GBDT v3 + C1)"; \
    python3 -c "
import json; d=json.load(open('$PILOT/s14-extras.json'))
print('GBDT v3 LOTO:', json.dumps({k:v for k,v in d.get('gbdt_v3_loto',{}).items() if k!='confusion'}))
print('C1 4 espaces:', json.dumps({k:v for k,v in d.get('c1_gxf_4espaces',{}).items() if k!='curve'}))
print('rappel refit v2:', json.dumps(d.get('rappel_refit_v2',{})))" >> "$JOURNAL" 2>/dev/null; }

  GATE=$(python3 -c "
import json; d=json.load(open('$PILOT/s14-pool-v8-eval.json'))
print('PASS' if (d['gate_v2']['gold_pass'] or d['gate_v2']['gxf_pass']) else 'FAIL')" 2>/dev/null || echo FAIL)
  journal ""; journal "**Gate v2 après cycle $CYCLE : $GATE**"
  log "C$CYCLE gate v2: $GATE | reste $(( $(remaining_s)/3600 ))h$(( ($(remaining_s)%3600)/60 ))"
  [ "$GATE" = PASS ] && break
done

journal ""
journal "## FIN DU RUN AUTONOME — $(date '+%H:%M') (budget temps : $(( ($(now) - START)/3600 ))h$(( (($(now) - START)%3600)/60 ))), gate v2 : $GATE"
journal "Canonique reste v6 ; v8/éventuels suivants = candidats. Décision de promotion : owner."
log "FIN superviseur"
