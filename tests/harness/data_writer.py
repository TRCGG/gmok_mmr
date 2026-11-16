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
    *,
    replace_scopes: pd.DataFrame | None = None,
) -> None:
    """row 단위 결과와 요약 결과를 설정된 저장 방식으로 저장한다.

    ``replace_scopes``는 DB 저장 시 교체할 ``(guild_id, season)`` 계산 대상 범위다.
    """
    sink = (sink or get_result_sink()).lower()
    if sink == "db":
        _save_results_to_db(match_results, user_summary, replace_scopes)
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
    # JSON 컬럼(예: position_report) 안의 실수도 고정 컬럼과 같은 자릿수로 맞춘다.
    for column in out.select_dtypes(include="object").columns:
        if out[column].map(lambda value: isinstance(value, dict)).any():
            out[column] = out[column].map(_round_nested)
    out["calculated_at"] = datetime.now(UTC)
    return out


def _round_nested(value):
    if isinstance(value, dict):
        return {key: _round_nested(item) for key, item in value.items()}
    if isinstance(value, list):
        return [_round_nested(item) for item in value]
    if isinstance(value, float):
        return round(value, 2)
    return value


def _save_results_to_db(
    match_results: pd.DataFrame,
    user_summary: pd.DataFrame,
    replace_scopes: pd.DataFrame | None = None,
) -> None:
    """계산된 MMR 결과를 PostgreSQL 테이블에 교체 저장한다."""
    save_mmr_results_to_db(
        _stamp(match_results),
        _stamp(user_summary),
        replace_scopes,
    )


def _api_headers() -> dict[str, str]:
    token = get_api_token()
    headers = {"Content-Type": "application/json"}
    if token:
        headers["Authorization"] = f"Bearer {token}"
    return headers


def _save_results_to_api(
    match_results: pd.DataFrame,
    user_summary: pd.DataFrame,
) -> None:
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
