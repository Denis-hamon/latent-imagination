#!/usr/bin/env python3
"""GHOST MCP — transport Streamable-HTTP (installation à la Context7 : une URL).

Même moteur que ghost_server.py (stdio) : world model goal-free sur pool v8,
abstention calibrée (régime LOAO acc 0.952 [0.773,0.992] @10 % de couverture),
contrat multi-LLM (reporter / grounded_by), capture flywheel.

Démarrage serveur (sur le node) :
    .venv/bin/python ghost_http_server.py
Env : GHOST_HOST (défaut 0.0.0.0), GHOST_PORT (défaut 8093),
      GHOST_TOKEN (optionnel : s'il est posé, le serveur EXIGE un bearer
      token valide — fail-closed : si la lib ne sait pas l'appliquer, le
      serveur refuse de démarrer plutôt que servir « protégé » en nom seul).

Côté client — l'installation tient en une ligne, comme Context7 :
    claude mcp add --transport http ghost http://<host>:8093/mcp
    # ou dans mcpServers : {"ghost": {"url": "http://<host>:8093/mcp"}}
    # avec token : header Authorization: Bearer <GHOST_TOKEN>
"""
from __future__ import annotations

import importlib.util
import json
import os
import sys
from pathlib import Path

from mcp.server.mcpserver import MCPServer

HERE = Path(__file__).resolve().parent
_spec = importlib.util.spec_from_file_location("ghost_server", HERE / "ghost_server.py")
gs = importlib.util.module_from_spec(_spec)
sys.modules["ghost_server"] = gs
_spec.loader.exec_module(gs)

INSTRUCTIONS = """\
GHOST — le fantôme de chaque run passé note votre brouillon de patch.

Usage recommandé, dans l'ordre :
1. preflight_patch(repo_path, diff_text) — contrôles déterministes GRATUITS
   (le diff s'applique ? ça compile ?). À lancer avant tout le reste.
2. risk_scan(state_text, diff_text, reporter=<votre identité>,
   exclude_task=<tâche en cours si connue>) — score goal-free du risque.
   Réponses possibles : low_risk / high_risk / abstain.
   IMPORTANT : "abstain" signifie que le modèle n'est PAS assez sûr pour
   trancher (il ne prédit que dans un régime mesuré à acc ≥ 0.95). Sur
   abstain, décidez via vos tests, pas via ce score.
3. Faites tourner les vrais tests.
4. report_outcome(call_id, passed, reporter, grounded_by) — renvoyez l'issue
   GROUNDÉE (résultat d'exécution, jamais votre avis). Chaque issue groundée
   renforce le world model.

Advisory only : aucun outil ne remplace l'exécution des tests."""

HOST = os.environ.get("GHOST_HOST", "0.0.0.0")
PORT = int(os.environ.get("GHOST_PORT", "8093"))
TOKEN = os.environ.get("GHOST_TOKEN", "")


def verify_bearer(authorization: str | None) -> bool:
    """Délègue à la vérification pure de ghost_server (testée sans lib MCP)."""
    return gs.verify_bearer_token(authorization, TOKEN)


mcp_kwargs: dict = {
    "title": "GHOST MCP",
    "description": "Le fantôme de chaque run passé note votre brouillon de patch "
                   "(world model goal-free, abstention calibrée).",
    "instructions": INSTRUCTIONS,
}
if TOKEN:
    # Fail-closed wiring : si la version de la lib ne supporte pas le
    # token_verifier attendu, on refuse de démarrer plutôt que de servir
    # non protégé en silence (doctrine : degrade-with-disclosure jamais
    # silencieuse sur la sécurité).
    try:
        mcp = MCPServer("ghost", token_verifier=lambda auth: verify_bearer(auth), **mcp_kwargs)
    except TypeError as exc:
        raise SystemExit(
            "GHOST_TOKEN posé mais cette version de la lib ne supporte pas "
            f"token_verifier ({exc}) — refus de démarrer non protégé. "
            "Mettre la lib à jour ou retirer GHOST_TOKEN (réseau interne seulement)."
        ) from exc
else:
    mcp = MCPServer("ghost", **mcp_kwargs)
    print("[ghost] AVERTISSEMENT : GHOST_TOKEN absent — serveur SANS auth, "
          "réseau interne uniquement (README sécurité).", file=sys.stderr, flush=True)


def _run(name: str, args: dict) -> str:
    out = gs.call_tool(name, args)
    return out if isinstance(out, str) else json.dumps(out)


@mcp.tool()
def risk_scan(state_text: str, diff_text: str, exclude_task: str = "",
              reporter: str = "") -> str:
    """Le fantôme de chaque run passé note votre brouillon de diff.

    Compare le patch à la géométrie des issues antérieures : distance au plus
    proche ÉCHEC passé moins distance au plus proche SUCCÈS passé
    (failure-attractor, goal-free — aucun gold requis). Verdict rendu seulement
    dans le régime calibré (acc mesurée ≥ 0.95), sinon répond "abstain" :
    le fantôme se tait quand il ne sait pas.
    state_text = énoncé du problème/code buggué ; diff_text = diff candidat ;
    exclude_task = identifiant de tâche à retirer du pool (anti-fuite) ;
    reporter = votre identité de LLM/agent (stratification du renforcement).
    Renvoie un call_id : utilisez-le dans report_outcome après exécution."""
    return _run("risk_scan", {"state_text": state_text, "diff_text": diff_text,
                              "exclude_task": exclude_task, "reporter": reporter})


@mcp.tool()
def preflight_patch(repo_path: str, diff_text: str,
                    state_files: list[str] | None = None) -> str:
    """Contrôles DÉTERMINISTES gratuits avant exécution : git-apply-check
    (malformations, chemins), py_compile du résultat (syntaxe),
    application inversée après vérification. Zéro token LLM.
    C'est le tool à appeler AVANT d'investir dans un run de tests."""
    return _run("preflight_patch", {"repo_path": repo_path, "diff_text": diff_text,
                                    "state_files": state_files or []})


@mcp.tool()
def near_mis_patches(state_text: str, diff_text: str, goal_text: str,
                     k: int = 3) -> str:
    """Retourne les k patchs du pool les plus proches en latent, avec leur
    issue réelle d'exécution (succès/échec), pour informer un choix au lieu
    d'un verdict."""
    return _run("near_mis_patches", {"state_text": state_text, "diff_text": diff_text,
                                     "goal_text": goal_text, "k": k})


@mcp.tool()
def report_outcome(call_id: str, passed: bool, reporter: str = "",
                   grounded_by: str = "") -> str:
    """Journalise le résultat RÉEL d'un patch évalué (issue groundée : tests
    exécutés — pas l'avis du modèle). reporter = auteur du patch ;
    grounded_by = méthode de mesure (ex. 'pytest-f2p', 'ci', 'human').
    Les issues non groundées sont rejetées du renforcement."""
    return _run("report_outcome", {"call_id": call_id, "passed": passed,
                                   "reporter": reporter, "grounded_by": grounded_by})


@mcp.tool()
def assess_patch(state_text: str, diff_text: str, goal_text: str) -> str:
    """Mode HARNESS/ÉVALUATION seulement : énergie latente goal-bound
    (nécessite le texte du but — indisponible en production). Advisory."""
    return _run("assess_patch", {"state_text": state_text, "diff_text": diff_text,
                                 "goal_text": goal_text})


def main() -> int:
    # poids + pool + calibration chargés avant de servir (latence premier appel)
    gs._ensure_model()
    gs._load_pool()
    gs._load_risk_calib()
    print(f"[ghost] serving http://{HOST}:{PORT}/mcp (pool {gs.POOL_JSON.name}, "
          f"stateless)", file=sys.stderr, flush=True)
    mcp.run(transport="streamable-http", host=HOST, port=PORT, stateless_http=True)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
