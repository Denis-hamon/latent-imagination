"""P12 — les gates D1..D5, lus sur le rejeu.

Un tour v39 = un patch COMPLET régénéré depuis le parent. Une transition est
donc une paire de tours consécutifs (a,b) DANS UNE MÊME trajectoire, et une
ligne du corpus est un couple (transition, test déclaré).

  persist = 1  le test déclaré était déjà rouge au tour a
  y       = 1  le test déclaré est rouge au tour b

Le script tourne sur un rejeu PARTIEL sans mentir : il imprime toujours
combien d'instances il a réellement lues.
"""
from __future__ import annotations

import json
import os
import statistics
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
# Meme fichier pour P12 et P14, pilote par variable d'environnement. Dupliquer
# aurait fait diverger les correctifs en silence — la lecon de p12_replay.py.
CORPUS = os.environ.get("LI_CORPUS", "p12")
D = ROOT / "data" / "landing" / "act2-pilot" / "night-harvest" / f"py-{CORPUS}"
SEL = {x["instance_id"]: x for x in json.loads((D / f"{CORPUS}-selection.json").read_text())}
# Le temoin de fidelite est une population SEPAREE : c'est sur lui que se lit D2
# (« si rien ne se resout, c'est le rejeu qui est casse »), jamais sur la
# population d'etude. D2 applique a la population d'etude etait un filtre de
# population deguise en controle de harnais — le defaut qui a coute P12.
TEMOINS = {i for i, x in SEL.items() if x.get("temoin")}
ETUDE = {i for i in SEL if i not in TEMOINS}


def main() -> int:
    files = sorted((D / f"{CORPUS}-replay").glob("*.json"))
    lignes, tours, insts, trajs = [], [], set(), 0
    # Ventilation temoin / etude : D2 se lit sur le premier, D2' sur le second.
    res_t, nt_t, res_e, nt_e = 0, 0, 0, 0
    verts_par_inst: dict[str, list[bool]] = {}
    n_instables, n_non_obs, n_non_conf, n_non_parse = 0, 0, 0, 0
    mesurees = []
    res_mesure, res_amont, accord = 0, 0, 0
    rangs = []   # position du 1er tour vert dans la trajectoire, normalisée

    n_ecartees = 0
    for f in files:
        d = json.loads(f.read_text())
        iid = d["instance_id"]
        # ECARTEE EN VOL : le rejeu a ouvert l'instance puis l'a rejetee (hors
        # gabarit). L'enregistrement n'a pas de `trajectories` et n'entre dans
        # aucun gate. P14 n'en avait aucune, ce chemin n'avait jamais servi et
        # P16 est tombe sur une KeyError. On la COMPTE, on ne la tait pas : une
        # instance ecartee en silence est une instance perdue sans trace.
        if "trajectories" not in d:
            n_ecartees += 1
            continue
        insts.add(iid)
        n_instables += len(d.get("instables") or [])
        decl = set(SEL[iid]["FAIL_TO_PASS"])

        for traj in d["trajectories"]:
            trajs += 1
            # Un tour n'entre dans le corpus que s'il a été MESURÉ : patch
            # réellement dans l'arbre (`applied`), sortie pytest parsée, et
            # tous les tests déclarés effectivement observés.
            ok = []
            for t in traj:
                # L'ordre compte : un tour non appliqué n'a JAMAIS été exécuté,
                # donc il n'a pas de `parsed`. Le tester d'abord le comptait
                # comme un échec de mesure au lieu d'un échec d'application.
                if not t.get("applied"):
                    n_non_conf += 1
                    continue
                if not t.get("parsed"):
                    n_non_parse += 1
                    continue
                if t.get("declares_non_observes"):
                    n_non_obs += 1
                    continue
                ok.append(t)

            verts = []
            for t in ok:
                fail = set(t["failed_all"])
                # « vert » = aucun test déclaré rouge ET aucun autre rouge. Ne
                # PAS comparer à `p2p` par égalité d'identifiant : les ids
                # tronqués par l'amont sont réparés à l'exécution, et le nom
                # observé diffère alors de celui de la sélection. La campagne
                # n'exécute que F2P ∪ P2P : tout rouge hors déclarés EST un P2P.
                vert = not fail
                verts.append(vert)
                verts_par_inst.setdefault(iid, []).append(vert)
                if iid in TEMOINS:
                    nt_t += 1; res_t += vert
                else:
                    nt_e += 1; res_e += vert
                res_mesure += vert
                res_amont += bool(t.get("resolved_upstream"))
                accord += (vert == bool(t.get("resolved_upstream")))
                tours.append(t)
            if verts:
                mesurees.append(traj)
                if any(verts):
                    rangs.append(verts.index(True) / max(1, len(verts) - 1))

            for a, b in zip(ok, ok[1:]):
                ra, rb = set(a["failed_all"]), set(b["failed_all"])
                for test in sorted(decl):
                    lignes.append({"persist": int(test in ra), "y": int(test in rb),
                                   "inst": iid, "test": test})

    n = len(lignes)
    persist0 = sum(1 for r in lignes if r["persist"] == 0)
    y1 = sum(1 for r in lignes if r["y"] == 1)
    nt = len(tours)
    total_tours = n_non_parse + n_non_conf + n_non_obs + nt

    def pct(a, b): return 100.0 * a / b if b else 0.0

    # --- quantites propres aux amendements P14 -------------------------------
    # Paires aveugles : (positif, negatif) d'une MEME instance a persist EGAL.
    # C'est ce que la metrique consomme reellement — gater dessus plutot que sur
    # un taux marginal est ce que D4 aurait du faire des le depart.
    par_inst: dict[str, list[dict]] = {}
    for r in lignes:
        par_inst.setdefault(r["inst"], []).append(r)
    paires_aveugles = 0
    for iid, rs in par_inst.items():
        if iid in TEMOINS:
            continue                      # le temoin ne nourrit pas la mesure
        pos = [r for r in rs if r["y"] == 1]
        neg = [r for r in rs if r["y"] == 0]
        paires_aveugles += sum(1 for a in pos for b in neg
                               if a["persist"] == b["persist"])

    # Issue mixte : l'instance a produit au moins un tour vert ET un non-vert.
    # Une instance a issue unique ne peut produire aucune paire, dans les deux sens.
    etude_mesurees = [i for i in verts_par_inst if i not in TEMOINS]
    mixtes = [i for i in etude_mesurees if len(set(verts_par_inst[i])) > 1]

    print(f"REJEU LU : {len(insts)}/{len(SEL)} instances · {trajs} trajectoires · {nt} tours retenus")
    print(f"  dont témoin de fidélité {len([i for i in insts if i in TEMOINS])}/{len(TEMOINS)}"
          f" · population d'étude {len([i for i in insts if i in ETUDE])}/{len(ETUDE)}")
    print(f"  tours écartés : {n_non_conf} non conformes · {n_non_parse} non parsés · "
          f"{n_non_obs} test déclaré non observé  (sur {total_tours})")
    if n_ecartees:
        print(f"  instances écartées EN VOL (hors gabarit, sans trajectoire) : {n_ecartees}")
    print(f"  parents instables (double passe) : {n_instables}")
    print()
    print(f"D1 volume        {n} paires test×tour · {len(insts)} instances"
          f"    {'OK' if n >= 700 and len(insts) >= 70 else 'NON'}   (≥700 · ≥70)")
    if CORPUS == "p12":
        print(f"D2 résolution    {pct(res_mesure, nt):.1f} %   mesuré"
              f"    {'OK' if pct(res_mesure, nt) >= 70 else 'NON'}   (≥70 %)")
    else:
        # Amendement n°1 : D2 est un controle de FIDELITE DU HARNAIS, il se lit
        # sur le temoin. Sur la population d'etude il devient un gate de VARIANCE.
        print(f"D2 fidélité      {pct(res_t, nt_t):.1f} %   sur le témoin ({nt_t} tours)"
              f"    {'OK' if pct(res_t, nt_t) >= 70 else 'NON'}   (≥70 %)")
        print(f"D2′ variance     {pct(len(mixtes), len(etude_mesurees)):.1f} %   "
              f"d'instances à issue mixte ({len(mixtes)}/{len(etude_mesurees)})"
              f"    {'OK' if pct(len(mixtes), len(etude_mesurees)) >= 60 else 'NON'}   (≥60 %)")
        print(f"     étude       {pct(res_e, nt_e):.1f} %   de tours verts sur la population "
              f"d'étude (descriptif, PAS un gate)")
    print(f"     amont       {pct(res_amont, nt):.1f} %   étiqueté · accord mesuré↔amont "
          f"{pct(accord, nt):.1f} %")
    print(f"D3 persist=0     {pct(persist0, n):.1f} %"
          f"    {'OK' if pct(persist0, n) >= 80 else 'NON'}   (≥80 %)")
    if CORPUS == "p12":
        print(f"D4 y=1           {pct(y1, n):.1f} %   ({y1} positifs)"
              f"    {'OK' if 3 <= pct(y1, n) <= 15 else 'NON'}   (3–15 %)")
        # Controle positif du compteur de paires : sur P12 il DOIT rendre 121,
        # la valeur publiee dans window-p13-verdict.md. Un compteur non controle
        # ne prouve rien quand il rendra un nombre sur P14.
        print(f"     paires aveugles {paires_aveugles}"
              f"    {'OK' if paires_aveugles == 121 else 'ÉCART'}   (contrôle : 121 publié)")
    else:
        # Amendement n°3 : la bande 3-15 % mesure une propriete que P14 INVERSE
        # volontairement. La garder ferait echouer le gate parce que le corpus
        # reussit ce pour quoi il a ete concu. Reporte, plus gate.
        print(f"D4 y=1           {pct(y1, n):.1f} %   ({y1} positifs)"
              f"    —    (reporté, PLUS un gate : bande calibrée sur P12)")
        print(f"D4′ paires aveug {paires_aveugles} paires"
              f"    {'OK' if paires_aveugles >= 121 else 'NON'}   (≥121, valeur publiée de P12)")
    print(f"D5 intégrité     {pct(nt, total_tours):.1f} %"
          f"    {'OK' if pct(nt, total_tours) >= 90 else 'NON'}   (≥90 %)")
    if rangs:
        print()
        print(f"position du 1er tour vert (0 = déjà vert au tour 1) : médiane {statistics.median(rangs):.2f}"
              f" · trajectoires mesurées jamais vertes {len(mesurees) - len(rangs)}/{len(mesurees)}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
