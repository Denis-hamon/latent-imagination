"""Transport HTTP — API publique façon Context7 (REST, un endpoint par tool).

Run : uvicorn latent_gate.http_api:app --host 0.0.0.0 --port 8080
Auth : si LI_API_KEYS est défini (liste séparée par des virgules), X-API-Key
obligatoire sur /tools/* ; /health et /claims restent publics.
"""

from __future__ import annotations

import os
from pathlib import Path

from fastapi import Depends, FastAPI, Header, HTTPException
from pydantic import BaseModel, Field

from . import __version__, service

app = FastAPI(title="latent-gate", version=__version__)

_API_KEYS = {k.strip() for k in os.environ.get("LI_API_KEYS", "").split(",")
             if k.strip()}


def auth(x_api_key: str | None = Header(default=None)):
    if _API_KEYS and x_api_key not in _API_KEYS:
        raise HTTPException(status_code=401, detail="invalid API key")


class ScoreReq(BaseModel):
    state_text: str = Field(max_length=20000)
    diff_text: str = Field(max_length=20000)
    goal_text: str | None = Field(default=None, max_length=20000)
    exclude_task: str | None = None


class OutcomeReq(BaseModel):
    call_id: str = Field(max_length=64)
    passed: bool


class NearReq(BaseModel):
    state_text: str = Field(max_length=20000)
    k: int = Field(default=3, ge=1, le=10)
    exclude_task: str | None = None


@app.get("/health")
def health():
    return service.health()


@app.get("/claims")
def claims():
    """Les claims signés du service (falsifiable public claims) — si le fichier
    est présent dans public/claims.json il est servi verbatim, hash visible."""
    p = Path(__file__).resolve().parents[2] / "public" / "claims.json"
    if not p.is_file():
        raise HTTPException(404, "claims.json non encore publié")
    import json as _json
    return _json.loads(p.read_text())


@app.post("/tools/score_patch", dependencies=[Depends(auth)])
def t_score(req: ScoreReq):
    return service.score_patch(req.state_text, req.diff_text, req.goal_text,
                               req.exclude_task)


@app.post("/tools/risk_scan", dependencies=[Depends(auth)])
def t_risk(req: ScoreReq):
    return service.risk_scan(req.state_text, req.diff_text, req.exclude_task)


@app.post("/tools/near_misses", dependencies=[Depends(auth)])
def t_near(req: NearReq):
    return service.near_misses(req.state_text, req.k, req.exclude_task)


@app.post("/tools/report_outcome", dependencies=[Depends(auth)])
def t_outcome(req: OutcomeReq):
    return service.report_outcome(req.call_id, req.passed)
