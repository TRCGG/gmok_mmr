"""FastAPI entrypoint for the MMR calculation service."""

from __future__ import annotations

from typing import Any

from fastapi import FastAPI, HTTPException

from .service import calculate_full_mmr, calculate_single_match_mmr


app = FastAPI(title="GMOK MMR Service", version="0.1.0")


@app.get("/health")
def health() -> dict[str, str]:
    return {"status": "ok"}


@app.post("/v1/mmr/recalculate")
def recalculate(payload: dict[str, Any]) -> dict[str, Any]:
    try:
        return calculate_full_mmr(payload)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    except Exception as exc:
        raise HTTPException(status_code=500, detail=f"MMR calculation failed: {exc}") from exc


@app.post("/v1/mmr/matches/calculate")
def calculate_match(payload: dict[str, Any]) -> dict[str, Any]:
    try:
        return calculate_single_match_mmr(payload)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    except Exception as exc:
        raise HTTPException(status_code=500, detail=f"MMR calculation failed: {exc}") from exc
