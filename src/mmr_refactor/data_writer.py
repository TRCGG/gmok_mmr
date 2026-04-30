"""MMR result writers.

Current test flow writes calculated outputs to PostgreSQL. The public
``save_mmr_results`` function can later route to the backend API without
changing the calculation pipeline.
"""

from __future__ import annotations

from datetime import UTC, datetime

import pandas as pd

from .config import (
    get_api_base_url,
    get_api_token,
    get_result_sink,
)
from .repository import save_mmr_results_to_db


def save_mmr_results(
    match_results: pd.DataFrame,
    user_summary: pd.DataFrame,
    sink: str | None = None,
) -> None:
    """Save row-level and summary MMR outputs to the configured destination."""
    sink = (sink or get_result_sink()).lower()
    if sink == "db":
        _save_results_to_db(match_results, user_summary)
        return
    if sink == "api":
        _save_results_to_api(match_results, user_summary)
        return
    raise ValueError(f"Unsupported MMR_RESULT_SINK: {sink!r}")


def _stamp(df: pd.DataFrame) -> pd.DataFrame:
    out = df.copy()
    out.columns = [str(c).lower() for c in out.columns]
    out = out.drop(columns=["player_game_id"], errors="ignore")
    float_cols = out.select_dtypes(include="floating").columns
    out[float_cols] = out[float_cols].round(2)
    out["calculated_at"] = datetime.now(UTC)
    return out


def _save_results_to_db(match_results: pd.DataFrame, user_summary: pd.DataFrame) -> None:
    """Append calculated MMR outputs to PostgreSQL tables."""
    save_mmr_results_to_db(_stamp(match_results), _stamp(user_summary))


def _api_headers() -> dict[str, str]:
    token = get_api_token()
    headers = {"Content-Type": "application/json"}
    if token:
        headers["Authorization"] = f"Bearer {token}"
    return headers


def _save_results_to_api(match_results: pd.DataFrame, user_summary: pd.DataFrame) -> None:
    """Post calculated MMR outputs to the backend API."""
    import requests

    payload = {
        "match_results": _stamp(match_results).to_dict(orient="records"),
        "user_summary": _stamp(user_summary).to_dict(orient="records"),
    }
    resp = requests.post(
        f"{get_api_base_url()}/v1/mmr/results",
        headers=_api_headers(),
        json=payload,
        timeout=60,
    )
    resp.raise_for_status()
