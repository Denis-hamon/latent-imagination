#!/bin/bash
# P16 — rejeu des 120 instances (100 etude + 20 temoin), deux bras.
# Fenetre : governance/act2/window-p16-confondu-proposal.md, scellee avant.
#
# GARDES EN VIGUEUR, verifies et non decoratifs :
#  - chaque etape lit son code de sortie et leve (lecon du 30/08, ou le pipeline
#    a lance une nulle sur 13 variantes dont 7 n'existaient pas) ;
#  - le rejeu s'arrete sur code 75 = transport perdu (lecon des 58 instances
#    perdues dans la nuit du 29) ; il est idempotent, on relance et il reprend.
export LI_CORPUS=p16
export OMP_NUM_THREADS=1 OPENBLAS_NUM_THREADS=1 MKL_NUM_THREADS=1
cd "$HOME/latent-imagination" || exit 1
L="$HOME/latent-imagination/p16-rejeu.log"
P=.venv/bin/python
say() { echo "=== [$(date -u +%H:%M:%S)Z] $*" >> "$L"; }

say "1/2 rejeu p16 — 120 instances, 217 trajectoires"
$P scripts/act2/p12_replay_all.py >> "$L" 2>&1
rc=$?
if [ $rc -eq 75 ]; then
  say "ARRET : transport perdu (code 75). Rejeu idempotent — relancer reprend ici."
  exit 75
elif [ $rc -ne 0 ]; then
  say "ECHEC rejeu (code $rc) — PIPELINE ARRETE, aucun gate n'est lu"
  exit 1
fi

say "2/2 gates p16 — AVANT tout fit"
if ! $P scripts/act2/p12_gates.py >> "$L" 2>&1; then
  say "ECHEC gates (code $?) — PIPELINE ARRETE"
  exit 1
fi
say "REJEU ET GATES TERMINES — arret volontaire avant le fit, decision de lecture"
