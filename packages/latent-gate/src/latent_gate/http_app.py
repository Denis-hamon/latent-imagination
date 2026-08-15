"""Entry HTTP : uvicorn latent_gate.http_app:app --host 0.0.0.0 --port 8080."""

from __future__ import annotations

import os

from fastapi import Depends, FastAPI, Header, HTTPException
from pydantic import BaseModel

from . import __version__, service

app = FastAPI(title="latent-gate", version=__version__)

_API_KEYS = {k.strip() for k in os.environ.get("LI_API_KEYS", "").split(",")
             if k.strip()}


def auth(x_api_key: str | None = Header(default=None)):
    """Obligatoire seulement si LI_API_KEYS est défini (prod)."""
    if _API_KEYS and x_api_key not in _API_KEYS:
        raise HTTPException(status_code=401, detail="invalid API key")


class ScoreReq(BaseModel):
    state_text: str
    diff_text: str
    goal_text: str | None = None
    exclude_task: str | None = None


class RiskReq(BaseModel):
    state_text: str
    diff_text: str
    exclude_task: str | None = None


class NearReq(BaseModel):
    state_text: str
    k: int = 3
    exclude_task: str | None = None


class OutcomeReq(BaseModel):
    call_id: str
    passed: bool


@app.get("/health")
def health():
    """Public : statut + hash pool/modèle (la claim publique est falsifiable)."""
    return service.health()


@app.get("/claims")
def claims():
    return service.claims()


@app.post("/v1/score_patch", dependencies=[Depends(auth)])
def score_patch(req: ScoreReq):
    return service.score_patch(req.state_text, req.diff_text, req.goal_text,
                               req.exclude_task)


@app.post("/v1/risk_scan", dependencies=[Depends(auth)])
def risk_scan(req: RiskReq):
    return service.risk_scan(req.state_text, req.diff_text, req.exclude_task)


@app.post("/v1/near_misses", dependencies=[Depends(auth)])
def near_misses(req: NearReq):
    return service.near_misses(req.state_text, req.k, req.exclude_task)


@app.post("/v1/report_outcome", dependencies=[Depends(auth)])
def report_outcome(req: OutcomeReq):
    return service.report_outcome(req.call_id, req.passed)
