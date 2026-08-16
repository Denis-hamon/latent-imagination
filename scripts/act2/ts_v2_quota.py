#!/usr/bin/env python3
"""Window coverage-ts-v2 — builder du quota : mutants sur les content-adapters
kimsufi, vérifiés zéro-appel (chaîne vitest distante : mutation → F2P nommés rouges →
gold reverdit, arbre propre). Les invalides sont ÉCARTÉS et journalisés
(discarded) — jamais de tâche inventée. Classe de difficulté VALIDÉE par le
difficulty-probe (1/2 réparé par l'auteur, règle fenêtre ebfe7acf).

Les 2 mutants du probe (region_sort_inverted, price_html_not_stripped) sont
inclus dans la table : leur chaîne est déjà prouvée, ils font partie du quota.

Sortie : data/landing/act2-pilot/ts-v2/{quota-tasks.json,discarded.jsonl}
Run: uv run python scripts/act2/ts_v2_quota.py
"""
from __future__ import annotations

import json
import subprocess
import sys
from datetime import UTC, datetime
from hashlib import sha256
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
Q = ROOT / "data" / "landing" / "act2-pilot" / "ts-v2"
HOST = "Kimsufi-standard"
REMOTE = "~/kimsufi-source/apps/site"
D = "src/content-adapters/drupal"

MUTANTS = [
    # --- classe du difficulty-probe (validée) ---
    {"task_id": "kimsufi__slider.region_sort_inverted",
     "file": f"{D}/transformers.ts", "spec": "transformers.slider",
     "replacements": [(
        "    (a, b) => getSlideRegionIndex(a) - getSlideRegionIndex(b)",
        "    (a, b) => getSlideRegionIndex(b) - getSlideRegionIndex(a)")],
     "problem": "Le tri des slides par index de région est inversé : ordre "
                "d'affichage inverse et enfants sans région remontés au début."},
    {"task_id": "kimsufi__slider.price_html_not_stripped",
     "file": f"{D}/transformers.ts", "spec": "transformers.slider",
     "replacements": [(
        "const priceValue = rawPriceHtml ? rawPriceHtml.replace(/<[^>]*>/g, '').trim() : '';",
        "const priceValue = rawPriceHtml ? rawPriceHtml.trim() : '';")],
     "problem": "Le prix du slider conserve ses balises HTML (<p>79,99 €</p> "
                "au lieu de 79,99 €)."},
    # --- quota additionnel, même classe ---
    {"task_id": "kimsufi__slider.highlight_case_sensitive",
     "file": f"{D}/transformers.ts", "spec": "transformers.slider",
     "replacements": [(
        "BAREMETAL_HIGHLIGHTED_RANGE_NAMES.includes(title.toLowerCase())",
        "BAREMETAL_HIGHLIGHTED_RANGE_NAMES.includes(title)")],
     "problem": "La détection de highlight par nom de gamme devient sensible à "
                "la casse : 'Starter' écrit autrement que dans la liste n'est "
                "plus highlighté."},
    {"task_id": "kimsufi__productlist.url_priority_inverted",
     "file": f"{D}/transformers.ts", "spec": "transformers.productlist",
     "replacements": [(
        "const rawUrl = ref.uri_static || ref.uri || ref.alias || '';",
        "const rawUrl = ref.uri || ref.uri_static || ref.alias || '';")],
     "problem": "L'URL de page produit préfère uri (brut) à uri_static (URL "
                "publique avec locale) : les liens produits pointent vers la "
                "mauvaise URL quand les deux existent."},
    {"task_id": "kimsufi__aiwf.component_id_is_type",
     "file": "src/content-adapters/aiwf/buildComponentsFromContent.ts",
     "spec": "buildComponentsFromContent",
     "replacements": [("    id: uuid,", "    id: entry.type,")],
     "problem": "Les composants legacy reçoivent leur TYPE comme id au lieu de "
                "l'UUID : collisions d'id quand deux composants du même type "
                "coexistent."},
    {"task_id": "kimsufi__aiwf.variant_default_lost",
     "file": "src/content-adapters/aiwf/buildComponentsFromContent.ts",
     "spec": "buildComponentsFromContent",
     "replacements": [(
        "    id: uuid,\n    type: entry.type,\n    variant: entry.variant || 'default',",
        "    id: uuid,\n    type: entry.type,\n    variant: entry.variant || '',")],
     "problem": "Le variant par défaut des composants legacy devient chaîne "
                "vide au lieu de 'default' : le rendu bascule sur un variant "
                "inconnu."},
    {"task_id": "kimsufi__catalog.universe_filter_drops_generic",
     "file": "src/content-adapters/aiwf/component-catalog.ts",
     "spec": "component-catalog",
     "replacements": [(
        "entry.availableUniverses.includes(universe) || entry.availableUniverses.includes('generic')",
        "entry.availableUniverses.includes(universe) && entry.availableUniverses.includes('generic')")],
     "problem": "Le filtre par univers du catalogue exige qu'un composant soit à "
                "la fois dans l'univers demandé ET générique : plus aucun "
                "composant générique n'est retourné pour un univers donné."},
    {"task_id": "kimsufi__aiwf.normalize_early_return_or",
     "file": "src/content-adapters/aiwf/normalize-content.ts",
     "spec": "normalize-content",
     "replacements": [(
        "if (!needsCamelConversion && !needsAlias) return content;",
        "if (!needsCamelConversion || !needsAlias) return content;")],
     "problem": "La normalisation des clés s'arrête dès qu'un seul des deux "
                "traitements (camelCase ou alias) est inutile : un contenu "
                "camelCase sans alias n'est plus converti en snake_case."},
    {"task_id": "kimsufi__seo.hreflangs_key_value_swapped",
     "file": "src/lib/seo/utils.ts", "spec": "src/lib/seo/utils",
     "replacements": [(
        "languages[hreflang] = href;",
        "languages[href] = hreflang;")],
     "problem": "hreflangsToLanguages échange clés et valeurs : le Record "
                "contient les URL comme clés et les codes langue comme valeurs."},
]


def sh_remote(cmd: str, timeout: int = 300) -> subprocess.CompletedProcess:
    return subprocess.run(["ssh", "-o", "ConnectTimeout=12", HOST, cmd],
                          capture_output=True, text=True, check=False, timeout=timeout)


def sh_local(cmd: list[str], timeout: int = 120) -> subprocess.CompletedProcess:
    return subprocess.run(cmd, capture_output=True, text=True, check=False, timeout=timeout)


def vitest_remote(spec: str) -> tuple[list[str], int, str]:
    r = sh_remote(f"cd {REMOTE} && ./node_modules/.bin/vitest run {spec} --reporter=json 2>/dev/null",
                  timeout=600)
    failed = []
    passed = 0
    try:
        raw = r.stdout
        d = json.loads(raw[raw.find("{"):])
        for tr in d.get("testResults", []):
            for a in tr.get("assertionResults", []):
                if a.get("status") == "failed":
                    failed.append(a.get("title", ""))
                else:
                    passed += 1
    except (json.JSONDecodeError, ValueError):
        pass
    return failed, passed, r.stdout[-300:]


def validate(m: dict) -> dict:
    st = sh_remote(f"cd {REMOTE} && git -C ~/kimsufi-source status --porcelain | head -1")
    if st.stdout.strip():
        return {"task_id": m["task_id"], "rejected": "worktree remote non propre"}
    orig_r = sh_remote(f"cd {REMOTE} && cat {m['file']}")
    if orig_r.returncode != 0:
        return {"task_id": m["task_id"], "rejected": "fichier illisible"}
    orig = orig_r.stdout
    bug = orig
    for old, new in m["replacements"]:
        if old not in bug:
            return {"task_id": m["task_id"], "rejected": "texte mutant introuvable"}
        bug = bug.replace(old, new, 1)
    tmp = Q / f".tmp-{m['task_id'][-18:]}.tsx"
    tmp.write_text(bug)
    up = sh_local(["scp", "-q", str(tmp), f"{HOST}:{REMOTE}/{m['file']}"], timeout=120)
    tmp.unlink(missing_ok=True)
    if up.returncode != 0:
        return {"task_id": m["task_id"], "rejected": "scp échoué"}
    failed, passed, tail = vitest_remote(m["spec"])
    sh_remote(f"cd {REMOTE} && git checkout -- {m['file']}")
    dirty = sh_remote(f"cd {REMOTE} && git -C ~/kimsufi-source status --porcelain | head -1")
    if dirty.stdout.strip():
        return {"task_id": m["task_id"], "rejected": "restauration remote a échoué"}
    if not failed:
        return {"task_id": m["task_id"], "rejected": "aucun test nommé ne casse",
                "raw_tail": tail}
    return {"task_id": m["task_id"], "ok": True, "buggy": bug,
            "f2p": sorted(failed), "p2p_n": passed,
            "file": m["file"], "spec": m["spec"], "problem": m["problem"]}


def main() -> int:
    Q.mkdir(parents=True, exist_ok=True)
    tasks, discarded = [], []
    for m in MUTANTS:
        print(f"validation {m['task_id']} …", flush=True)
        r = validate(m)
        if r.pop("ok", False):
            buggy_f = Q / f"{r['task_id'].replace('/', '_')}.buggy.py"
            buggy_f.write_text(r.pop("buggy"))
            tasks.append({
                "instance_id": r["task_id"], "repo": "kimsufi/site",
                "lang": "typescript", "test_runner": "vitest",
                "target": r["file"], "spec": r["spec"],
                "patch": "", "gold": "",
                "buggy_sha256": sha256(buggy_f.read_bytes()).hexdigest(),
                "f2p": r["f2p"], "p2p_n": r["p2p_n"], "problem": r["problem"],
                "campaign": "coverage-ts-2", "window": "coverage-ts-v2"})
            print(f"  OK : {len(r['f2p'])} F2P, {r['p2p_n']} P2P")
        else:
            discarded.append({**r, "discarded_at":
                              datetime.now(UTC).isoformat().replace("+00:00", "Z")})
            print(f"  ÉCARTÉ : {r.get('rejected')}")
    mani = {"window": "coverage-ts-v2",
            "difficulty_probe_ref": "data/landing/act2-pilot/coverage-ts-2/probe-verdict.json",
            "n_tasks": len(tasks), "tasks": tasks,
            "generated_at": datetime.now(UTC).isoformat().replace("+00:00", "Z")}
    (Q / "quota-tasks.json").write_text(json.dumps(mani, indent=1) + "\n")
    with (Q / "discarded.jsonl").open("w") as fh:
        for d in discarded:
            fh.write(json.dumps(d, ensure_ascii=False) + "\n")
    print(f"\nquota : {len(tasks)} validées / {len(MUTANTS)} candidates "
          f"({len(discarded)} écartées)")
    if len(tasks) < 10:
        print(f"SHORTFALL vs quota cible 10 : {10 - len(tasks)} — disclosure à la "
              f"frozen selection (un quota est un plafond)")
    return 0


if __name__ == "__main__":
    sys.exit(main())
