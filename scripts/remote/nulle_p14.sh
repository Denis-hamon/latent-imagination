#!/bin/bash
# Nulle du maximum P14 — VERSION AVEC LES FILS BLAS REELLEMENT EPINGLES.
#
# DEFAUT MESURE LE 2026-08-30. `p13_nulle._init` posait OMP_NUM_THREADS=1 dans
# l'initializer du pool, donc APRES que numpy/OpenBLAS aient ete charges par le
# parent : OpenBLAS lit cette variable AU CHARGEMENT, jamais ensuite. Les 15
# workers tournaient donc a 16 fils chacun sur des matrices 1009x1540 — assez
# petites pour que la synchronisation des fils coute plus que le calcul.
#
# Mesure : V1 en mono-fil = 158 s (MiscV2) contre 866 s en multi-fil (Kimsufi),
# soit 5,5x plus lent A CAUSE des fils. En 2 h 56, 15 workers n'avaient pas
# termine un seul tirage.
#
# Le correctif est dans l'ENVIRONNEMENT du lancement, avant tout import Python.
export OMP_NUM_THREADS=1 OPENBLAS_NUM_THREADS=1 MKL_NUM_THREADS=1
export NUMEXPR_NUM_THREADS=1 VECLIB_MAXIMUM_THREADS=1
cd "$HOME/latent-imagination" || exit 1
L="$HOME/latent-imagination/nulle-p14.log"
V=V1,V2,V3,V4,V5,V6,V7,V8,V9,V10,V11,V12,V13
echo "=== [$(date -u +%H:%M:%S)Z] nulle p14 — fils epingles a 1, ${1:-15} workers, k<[${2:-71}]" >> "$L"
.venv/bin/python scripts/act2/p13_nulle.py --corpus p14 --variantes "$V" \
  --perms 100 --workers "${1:-15}" --k-max "${2:-71}" >> "$L" 2>&1
echo "=== [$(date -u +%H:%M:%S)Z] TERMINE (code $?)" >> "$L"
