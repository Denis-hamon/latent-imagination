"""Transport MCP stdio (JSON-RPC 2025-06-18) — même protocole que le serveur
live-testé scripts/mcp/ghost_server.py, outils alignés sur la v1 publique.

Run : python -m latent_gate.mcp_stdio
N'écrit jamais JSON ailleurs que sur stdout ; logs sur stderr.
"""

from __future__ import annotations

import json
import sys

from . import __version__, service

TOOLS = [
    {"name": "score_patch",
     "description": "Pré-vol d'un patch : énergie latente vers le but (si goal_text "
                    "fourni) × attracteur d'échecs, combinés (logreg λ=1), avec "
                    "ABSTENTION explicite quand la confiance est basse. Le diff est "
                    "scoré tel qu'émis. Advisory. exclude_task = LOAO anti-fuite.",
     "inputSchema": {"type": "object",
                     "properties": {
                         "state_text": {"type": "string",
                                        "description": "état courant réduit (problème + zone)"},
                         "diff_text": {"type": "string", "description": "diff tel qu'émis par le modèle"},
                         "goal_text": {"type": "string",
                                       "description": "destination : énoncé de tests / problème"},
                         "exclude_task": {"type": "string"}},
                     "required": ["state_text", "diff_text"]}},
    {"name": "risk_scan",
     "description": "Score goal-free de risque (failure-attractor, AUC 0.709 "
                    "mesuré LOAO) : proximité aux échecs passés vs succès passés. "
                    "Rang, pas verdict.",
     "inputSchema": {"type": "object",
                     "properties": {"state_text": {"type": "string"},
                                    "diff_text": {"type": "string"},
                                    "exclude_task": {"type": "string"}},
                     "required": ["state_text", "diff_text"]}},
    {"name": "near_misses",
     "description": "K patchs du pool les plus proches par état (dédup par tâche), "
                    "avec leur issue réelle mesurée. Pour informer, pas pour trancher.",
     "inputSchema": {"type": "object",
                     "properties": {"state_text": {"type": "string"},
                                    "k": {"type": "integer", "default": 3},
                                    "exclude_task": {"type": "string"}},
                     "required": ["state_text"]}},
    {"name": "report_outcome",
     "description": "Journalise l'issue réelle d'un patch scoré (append-only, hashé) "
                    "— alimente le pool par batch validé, jamais en ligne.",
     "inputSchema": {"type": "object",
                     "properties": {"call_id": {"type": "string"},
                                    "passed": {"type": "boolean"}},
                     "required": ["call_id", "passed"]}},
    {"name": "health",
     "description": "Statut du service, hash du pool et du modèle calibré.",
     "inputSchema": {"type": "object", "properties": {}}},
]


def _resp(i, result):
    return {"jsonrpc": "2.0", "id": i, "result": result}


def _err(i, code, msg):
    return {"jsonrpc": "2.0", "id": i, "error": {"code": code, "message": msg}}


def handle(msg: dict) -> dict | None:
    method, mid = msg.get("method"), msg.get("id")
    if method == "initialize":
        return _resp(mid, {"protocolVersion": "2025-06-18",
                           "capabilities": {"tools": {}},
                           "serverInfo": {"name": "latent-gate",
                                          "version": __version__}})
    if method == "notifications/initialized":
        return None
    if method == "tools/list":
        return _resp(mid, {"tools": TOOLS})
    if method == "tools/call":
        params = msg.get("params", {})
        name = params.get("name")
        args = params.get("arguments") or {}
        try:
            if name == "score_patch":
                out = service.score_patch(**args)
            elif name == "risk_scan":
                out = service.risk_scan(**args)
            elif name == "near_misses":
                out = service.near_misses(**args)
            elif name == "report_outcome":
                out = service.report_outcome(**args)
            elif name == "health":
                out = service.health()
            else:
                return _err(mid, -32601, f"unknown tool: {name}")
        except TypeError as exc:
            return _err(mid, -32602, f"bad arguments: {exc}")
        return _resp(mid, {"content": [{"type": "text",
                                        "text": json.dumps(out)}]})
    if mid is not None:
        return _err(mid, -32601, f"unknown method: {method}")
    return None


def main() -> int:
    service.health()  # précharge pool + encodeur avant la boucle
    while True:
        raw = sys.stdin.readline()
        if not raw:
            break
        try:
            msg = json.loads(raw.strip())
        except json.JSONDecodeError:
            continue
        try:
            out = handle(msg)
            if out is not None:
                sys.stdout.write(json.dumps(out) + "\n")
                sys.stdout.flush()
        except Exception as exc:  # le serveur ne doit jamais mourir sur un appel
            sys.stdout.write(json.dumps(
                _err(msg.get("id"), -32603, str(exc))) + "\n")
            sys.stdout.flush()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
