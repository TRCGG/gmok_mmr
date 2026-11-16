"""MMR baseline DB 저장소(``mmr_baselines``).

데이터팀이 로컬에서 수동 실행하는 ``scripts/calculate_baseline.py``(저장)와
``scripts/run_mmr_once.py``(조회)가 사용한다. 운영 패키지(``src/mmr``)에서는
사용하지 않는다.
"""

from __future__ import annotations

import json
from typing import Any

from sqlalchemy import create_engine, text

from mmr.gold.baseline import validate_baseline_payload

from .config import get_db_url, get_mmr_baseline_table

# calculate_baseline.py가 만든 baseline임을 나타내는 metadata 표식.
# 예전 경로(시즌 구분 없는 CLI, 단일 길드 run_mmr_once)로 만든 행에는 없다.
BASELINE_SCOPE_ALL_GUILDS = "all_guilds"


def get_db_test_mmr_baseline_table() -> str:
    """임시 DB 테스트용 baseline 테이블명을 반환한다."""
    return get_mmr_baseline_table()


def save_mmr_baseline_to_db_test(
    baseline_payload: dict[str, Any],
    *,
    is_active: bool = True,
) -> None:
    """검증된 baseline payload를 새 (season, baseline_version) 행으로 저장한다.

    같은 (season, baseline_version)이 이미 있으면 덮어쓰지 않고 ``ValueError``를 낸다.
    결과 행의 ``baseline_version`` 기록이 실제로 쓴 baseline을 계속 가리키게 하기
    위해서다. 활성으로 저장하면 같은 시즌의 기존 활성 행은 같은 트랜잭션에서
    비활성화된다(오류 시 함께 롤백).
    """
    validate_baseline_payload(baseline_payload)
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

        inserted = conn.execute(
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
                ON CONFLICT (season, baseline_version) DO NOTHING
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
        if inserted.rowcount == 0:
            raise ValueError(
                f"Baseline {baseline_version!r} for season {season!r} already exists. "
                "Use a new --baseline-version; existing baselines are never overwritten."
            )


def baseline_version_exists(season: str, baseline_version: str) -> bool:
    """같은 (season, baseline_version) baseline이 이미 저장돼 있는지 확인한다."""
    table_name = get_db_test_mmr_baseline_table()
    engine = create_engine(get_db_url())
    query = text(
        f"SELECT 1 FROM {table_name} "
        "WHERE season = :season AND baseline_version = :baseline_version"
    )
    with engine.connect() as conn:
        params = {"season": season, "baseline_version": baseline_version}
        return conn.execute(query, params).first() is not None


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


BASELINE_FOR_SEASON_SQL = """
        SELECT season, baseline_version, mmr_baseline, game_impact_baseline, metadata
        FROM {table_name}
        WHERE is_active = true
        ORDER BY (season = :season) DESC, saved_at DESC, id DESC
        LIMIT 1
        """


def load_baseline_for_season(season: str) -> dict[str, Any]:
    """시즌 계산에 쓸 활성 baseline을 읽는다.

    그 시즌의 활성 baseline이 있으면 그것을, 아직 없으면(새 시즌 초반, 200판 미만)
    시즌과 관계없이 가장 최근에 저장된(``saved_at``) 활성 baseline을 쓴다. 시즌
    문자열은 비교하지 않는다. 반환값의 ``season``은 baseline이 만들어진 시즌이다.
    """
    table_name = get_db_test_mmr_baseline_table()
    engine = create_engine(get_db_url())
    query = text(BASELINE_FOR_SEASON_SQL.format(table_name=table_name))
    with engine.connect() as conn:
        row = conn.execute(query, {"season": season}).mappings().first()

    if row is None:
        raise ValueError(
            f"No active MMR baseline exists (needed for season {season!r}). "
            "Run scripts/calculate_baseline.py first."
        )
    return {
        "season": row["season"],
        "baseline_version": row["baseline_version"],
        "mmr_baseline": _coerce_json(row["mmr_baseline"]),
        "game_impact_baseline": _coerce_json(row["game_impact_baseline"]),
        "metadata": _coerce_json(row["metadata"]) or {},
    }


def _coerce_json(value: Any) -> Any:
    """DB driver가 문자열로 반환한 JSON 값을 Python 객체로 복원한다."""
    if isinstance(value, str):
        return json.loads(value)
    return value
