"""임시 DB baseline 저장소.

주의:
    이 모듈은 백엔드 baseline 저장 API가 준비되기 전 DB 테스트만을 위한 코드다.
    운영 MMR 서비스 경로에 연결하지 말고, 백엔드 연동이 끝나면 삭제하거나 별도
    테스트 도구로 분리한다.
"""

from __future__ import annotations

import json
import os
import re
from typing import Any

from sqlalchemy import create_engine, text

from mmr_refactor.config import get_db_url


def get_db_test_mmr_baseline_table() -> str:
    """임시 DB 테스트용 baseline 테이블명을 반환한다."""
    return _safe_sql_identifier(os.environ.get("MMR_BASELINE_TABLE", "mmr_baselines"))


def save_mmr_baseline_to_db_test(
    baseline_payload: dict[str, Any],
    *,
    is_active: bool = True,
) -> None:
    """임시 DB 테스트용으로 계산된 baseline payload를 PostgreSQL에 저장한다."""
    season = baseline_payload.get("season")
    baseline_version = baseline_payload.get("baseline_version")
    if not season:
        raise ValueError("baseline payload must include 'season'.")
    if not baseline_version:
        raise ValueError("baseline payload must include 'baseline_version'.")

    metadata = baseline_payload.get("metadata") or {}
    table_name = get_db_test_mmr_baseline_table()
    engine = create_engine(get_db_url())

    with engine.begin() as conn:
        if is_active:
            conn.execute(
                text(f"UPDATE {table_name} SET is_active = false WHERE season = :season"),
                {"season": season},
            )

        conn.execute(
            text(
                f"""
                INSERT INTO {table_name} (
                    season,
                    baseline_version,
                    is_active,
                    mmr_baseline,
                    game_impact_baseline,
                    metadata,
                    match_count,
                    player_game_row_count,
                    calculated_at
                )
                VALUES (
                    :season,
                    :baseline_version,
                    :is_active,
                    CAST(:mmr_baseline AS jsonb),
                    CAST(:game_impact_baseline AS jsonb),
                    CAST(:metadata AS jsonb),
                    :match_count,
                    :player_game_row_count,
                    CAST(:calculated_at AS timestamptz)
                )
                ON CONFLICT (season, baseline_version) DO UPDATE SET
                    is_active = EXCLUDED.is_active,
                    mmr_baseline = EXCLUDED.mmr_baseline,
                    game_impact_baseline = EXCLUDED.game_impact_baseline,
                    metadata = EXCLUDED.metadata,
                    match_count = EXCLUDED.match_count,
                    player_game_row_count = EXCLUDED.player_game_row_count,
                    calculated_at = EXCLUDED.calculated_at,
                    saved_at = CURRENT_TIMESTAMP
                """
            ),
            {
                "season": season,
                "baseline_version": baseline_version,
                "is_active": is_active,
                "mmr_baseline": json.dumps(baseline_payload["mmr_baseline"]),
                "game_impact_baseline": json.dumps(
                    baseline_payload["game_impact_baseline"]
                ),
                "metadata": json.dumps(metadata),
                "match_count": metadata.get("match_count"),
                "player_game_row_count": metadata.get("player_game_row_count"),
                "calculated_at": metadata.get("calculated_at"),
            },
        )


def load_mmr_baseline_from_db_test(
    *,
    season: str,
    baseline_version: str | None = None,
    active_only: bool = True,
) -> dict[str, Any]:
    """임시 DB 테스트용으로 PostgreSQL에서 저장된 baseline payload를 읽는다."""
    table_name = get_db_test_mmr_baseline_table()
    engine = create_engine(get_db_url())
    where = ["season = :season"]
    params: dict[str, Any] = {"season": season}

    if baseline_version is not None:
        where.append("baseline_version = :baseline_version")
        params["baseline_version"] = baseline_version
    elif active_only:
        where.append("is_active = true")

    query = text(
        f"""
        SELECT
            season,
            baseline_version,
            mmr_baseline,
            game_impact_baseline,
            metadata
        FROM {table_name}
        WHERE {" AND ".join(where)}
        ORDER BY saved_at DESC
        LIMIT 1
        """
    )

    with engine.connect() as conn:
        row = conn.execute(query, params).mappings().first()

    if row is None:
        raise ValueError("No MMR baseline found for the requested condition.")

    metadata = _coerce_json(row["metadata"]) or {}
    return {
        "season": row["season"],
        "baseline_version": row["baseline_version"],
        "mmr_baseline": _coerce_json(row["mmr_baseline"]),
        "game_impact_baseline": _coerce_json(row["game_impact_baseline"]),
        "metadata": metadata,
    }


def _coerce_json(value: Any) -> Any:
    """DB driver가 문자열로 반환한 JSON 값을 Python 객체로 복원한다."""
    if isinstance(value, str):
        return json.loads(value)
    return value


def _safe_sql_identifier(value: str) -> str:
    """SQL 보간 전에 단순 테이블 식별자 형식인지 검증한다."""
    if not re.fullmatch(r"[A-Za-z_][A-Za-z0-9_]*", value):
        raise ValueError(f"Unsafe SQL identifier: {value!r}")
    return value
