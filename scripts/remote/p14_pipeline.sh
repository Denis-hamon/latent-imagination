#!/bin/bash
# Pipeline P14 joue sur Kimsufi-standard (16 coeurs, 31 Go) et NON sur le Mac.
# Detache : une coupure SSH ou un capot ferme ne le tue plus — c'est la lecon
# des 58 instances perdues dans la nuit du 29 au 30/08.
cd "$HOME/latent-imagination" || exit 1
L="$HOME/latent-imagination/p14-pipeline.log"
P=.venv/bin/python
say() { echo "=== [$(date -u +%H:%M:%S)Z] $*" >> "$L"; }

say "1/5 encodage p14 (LI_EMB_WORKERS=8)"
LI_EMB_WORKERS=8 $P scripts/act2/p10_fit.py --corpus p14 >> "$L" 2>&1 || { say "ECHEC encodage"; exit 1; }

say "2/5 les 13 variantes GELEES sur p14"
$P scripts/act2/p13_variants.py --corpus p14 \
   --variantes V1,V2,V3,V4,V5,V6,V7,V8,V9,V10,V11,V12,V13 >> "$L" 2>&1 || { say "ECHEC etape"; exit 1; }

say "3/5 V14 (P15, hypothese unique K=1)"
$P scripts/act2/p13_variants.py --corpus p14 --variantes V14 >> "$L" 2>&1 || { say "ECHEC etape"; exit 1; }

say "4/5 nulle du maximum sur p14 (13 variantes, 100 perms, 12 workers)"
$P scripts/act2/p13_nulle.py --corpus p14 \
   --variantes V1,V2,V3,V4,V5,V6,V7,V8,V9,V10,V11,V12,V13 \
   --perms 100 --workers 12 >> "$L" 2>&1 || { say "ECHEC etape"; exit 1; }

say "5/5 nulle p12 — REPRISE des 40 tirages manquants"
$P scripts/act2/p13_nulle.py --corpus p12 \
   --variantes V1,V2,V3,V4,V5,V6,V7,V8,V9,V10,V11,V12,V13 \
   --perms 100 --workers 12 >> "$L" 2>&1 || { say "ECHEC etape"; exit 1; }

say "PIPELINE TERMINE"
