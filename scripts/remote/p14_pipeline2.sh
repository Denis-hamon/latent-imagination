#!/bin/bash
# P14, reprise apres l'arret de la vague 1 sur V7.
#
# CORRECTIF DE PROTOCOLE. La v1 de ce script ne lisait le code de sortie
# d'AUCUNE etape sauf la premiere : `p13_variants` est mort sur V7 en
# reclamant `_E-p14-hunkagg.npy`, et le script a enchaine sur V14 puis sur
# la nulle du maximum de TREIZE variantes dont sept n'existaient pas. Un
# echec s'est lu comme un succes — meme classe de defaut que les 58
# instances perdues dans la nuit du 29 au 30/08. Ici chaque etape leve.
set -o pipefail
cd "$HOME/latent-imagination" || exit 1
L="$HOME/latent-imagination/p14-pipeline2.log"
P=.venv/bin/python
say() { echo "=== [$(date -u +%H:%M:%S)Z] $*" >> "$L"; }
etape() { # etape <libelle> <commande...>
  local lib="$1"; shift
  say "$lib"
  if ! "$@" >> "$L" 2>&1; then
    say "ECHEC : $lib (code $?) — PIPELINE ARRETE, rien de plus n'est joue"
    exit 1
  fi
}

etape "1/4 features vague 2 (corps, ast, hunks) pour p14" \
      $P scripts/act2/p13_features.py --corpus p14

etape "2/4 variantes V7 a V13 sur p14" \
      $P scripts/act2/p13_variants.py --corpus p14 --variantes V7,V8,V9,V10,V11,V12,V13

# GARDE : la nulle du maximum ne se lance QUE si les treize variantes existent.
n=$(grep -cE "^  V([1-9]|1[0-3]) " "$L" p14-pipeline.log 2>/dev/null | awk -F: '{s+=$2} END {print s}')
say "controle : $n lignes de variante V1-V13 dans les deux journaux (attendu 13)"
if [ "$n" -lt 13 ]; then
  say "ECHEC : les treize variantes ne sont pas toutes calculees — nulle NON lancee"
  exit 1
fi

etape "3/4 nulle du maximum sur p14 (13 variantes, 100 perms, 12 workers)" \
      $P scripts/act2/p13_nulle.py --corpus p14 \
      --variantes V1,V2,V3,V4,V5,V6,V7,V8,V9,V10,V11,V12,V13 --perms 100 --workers 12

etape "4/4 nulle p12 — reprise des 40 tirages manquants" \
      $P scripts/act2/p13_nulle.py --corpus p12 \
      --variantes V1,V2,V3,V4,V5,V6,V7,V8,V9,V10,V11,V12,V13 --perms 100 --workers 12

say "PIPELINE TERMINE"
