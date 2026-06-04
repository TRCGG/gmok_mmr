"""MMR 계산 결과 writer 모듈.

현재 테스트 흐름은 계산 결과를 PostgreSQL에 저장한다. 추후에는
``save_mmr_results``의 라우팅만 API 방식으로 바꾸고 계산 파이프라인은
그대로 유지할 수 있다.
"""

from __future__ import annotations

from datetime import UTC, datetime

import pandas as pd

from .config import (
    get_api_base_url,
    get_api_token,
    get_result_sink,
)
from .db_test.repository import save_mmr_results_to_db


def save_mmr_results(
    match_results: pd.DataFrame,
    user_summary: pd.DataFrame,
    sink: str | None = None,
) -> None:
    """row 단위 결과와 요약 결과를 설정된 저장 방식으로 저장한다."""
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
    """계산된 MMR 결과를 PostgreSQL 테이블에 추가 저장한다."""
    save_mmr_results_to_db(_stamp(match_results), _stamp(user_summary))


def _api_headers() -> dict[str, str]:
    token = get_api_token()
    headers = {"Content-Type": "application/json"}
    if token:
        headers["Authorization"] = f"Bearer {token}"
    return headers


def _save_results_to_api(match_results: pd.DataFrame, user_summary: pd.DataFrame) -> None:
    """계산된 MMR 결과를 백엔드 API로 전송한다."""
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
