#!/bin/bash
# Nulles P14 puis P12, relancees a 15 workers.
#
# MOTIF MESURE : a 12 workers, chacun tournait a 96 % d'UN cœur, soit 11,6
# cœurs sur 16 — 4,4 cœurs inutilises. Le `load average` de 197 trompait :
# il compte les fils runnables, pas les cœurs occupes. Aucun tirage n'etait
# termine, donc le redemarrage ne perd rien de calcule.
cd "$HOME/latent-imagination" || exit 1
L="$HOME/latent-imagination/p14-pipeline3.log"
P=.venv/bin/python
V=V1,V2,V3,V4,V5,V6,V7,V8,V9,V10,V11,V12,V13
say() { echo "=== [$(date -u +%H:%M:%S)Z] $*" >> "$L"; }
etape() { local lib="$1"; shift; say "$lib"
  if ! "$@" >> "$L" 2>&1; then say "ECHEC : $lib — PIPELINE ARRETE"; exit 1; fi; }

etape "1/2 nulle du maximum p14 (13 variantes, 100 perms, 15 workers)" \
      $P scripts/act2/p13_nulle.py --corpus p14 --variantes "$V" --perms 100 --workers 15
etape "2/2 nulle p12 — reprise des tirages manquants" \
      $P scripts/act2/p13_nulle.py --corpus p12 --variantes "$V" --perms 100 --workers 15
say "NULLES TERMINEES"
