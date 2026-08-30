#!/bin/bash
# Le Mac et le serveur encodent-ils DE FACON INTERCHANGEABLE ?
# Cosinus vecteur-a-vecteur : 0.9998 (1 degre). Trop proche pour conclure a
# l'oeil, trop loin pour l'ignorer. On mesure ce qui compte : l'AUC en aval.
# P12 est RE-ENCODE INTEGRALEMENT sur le serveur, caches ecartes, puis V11 et V6
# doivent rendre exactement 0.3884 et 0.4711 — leurs valeurs publiees.
cd "$HOME/latent-imagination" || exit 1
L="$HOME/latent-imagination/controle-encodage.log"
P10=data/landing/act2-pilot/night-harvest/py-p12/p10
say() { echo "=== [$(date -u +%H:%M:%S)Z] $*" >> "$L"; }

say "mise a l ecart des caches faits sur le Mac"
mkdir -p "$P10/_mac"
for f in emb-cache-p10.npz _X-p12.npy _y-p12.npy _g-p12.npy; do
  [ -f "$P10/$f" ] && cp "$P10/$f" "$P10/_mac/$f"
done
mv "$P10/emb-cache-p10.npz" "$P10/_mac/emb-cache-p10.npz.ecarte" 2>/dev/null
say "re-encodage integral de p12 sur le serveur (8 workers)"
LI_EMB_WORKERS=8 .venv/bin/python scripts/act2/p10_fit.py --corpus p12 >> "$L" 2>&1 || { say "ECHEC encodage"; exit 1; }
say "refit V11 et V6 sur les vecteurs SERVEUR"
.venv/bin/python scripts/act2/p13_variants.py --corpus p12 --variantes V11,V6 >> "$L" 2>&1
say "CONTROLE TERMINE — attendu V11 perp 0.3884 · V6 perp 0.4711"
