"""Run the full MMR calculation once using values loaded from ``.env``.

This is a one-time DB batch helper. It reads raw player-game rows, calculates
full MMR per season with the stored baseline, and saves the results.

Usage::

    python scripts/calculate_baseline.py --season 2026 --baseline-version 20261117
    python scripts/run_mmr_once.py

Seasons come from each match's ``custom_match.season``. Every season is
calculated independently from the initial MMR. Baselines are not calculated here:
each season uses its active baseline from ``scripts/calculate_baseline.py``, or the
most recently saved active baseline when the season has none yet. Only baselines
made by ``scripts/calculate_baseline.py`` (``metadata.scope = all_guilds``) are used.

Existing results in the target guilds/seasons are replaced. Because the backend
owns results after service start, the batch stops when target results already exist
unless ``MMR_ALLOW_RECALCULATE=1`` is set.

Optional .env values::

    MMR_SEASON=2026             # omitted/empty means every season in the data
    MMR_GUILD_ID=your-guild-id  # omitted/empty means all guilds
    MMR_ALLOW_RECALCULATE=1     # replace existing results in the target range
    MMR_CALCULATION_ID=mmr-once-2026-all
    MMR_OUTPUT_FILE=./output/mmr-once.json
"""

from __future__ import annotations

import json
import os
from pathlib import Path
import re
import sys
from typing import Any

from sqlalchemy import create_engine, inspect

ROOT = Path(__file__).resolve().parents[1]
for _path in (ROOT / "src", ROOT / "tests"):
    if str(_path) not in sys.path:
        sys.path.insert(0, str(_path))

try:
    from dotenv import load_dotenv
except ImportError as exc:  # pragma: no cover - dependency is in requirements.txt
    raise SystemExit("python-dotenv is required. Run: pip install -r requirements.txt") from exc

load_dotenv(ROOT / ".env")

from mmr.gold.baseline import validate_baseline_payload
from mmr.gold.report import attach_position_report, build_user_position_report
from mmr.serving.service import NoValidMatchesError, calculate_full_mmr
from harness.config import get_output_dir
from harness.data_writer import save_mmr_results
from harness.db_test.config import (
    get_db_url,
    get_mmr_baseline_table,
    get_mmr_match_result_table,
    get_mmr_summary_table,
)
from harness.db_test.baseline_repository import (
    BASELINE_SCOPE_ALL_GUILDS,
    load_baseline_for_season,
)
from harness.db_test.repository import count_existing_results, load_match_dataframe_from_db
from harness.season import normalize_season


def main() -> None:
    import pandas as pd

    season_filter = os.environ.get("MMR_SEASON", "").strip() or None
    guild_id = os.environ.get("MMR_GUILD_ID", "").strip() or None
    scope_name = guild_id or "all"
    print(f"Loading raw MMR rows for guild_id={guild_id!r} ...")
    raw_df = load_match_dataframe_from_db(guild_id=guild_id)
    if raw_df.empty:
        raise SystemExit("No eligible player-game rows were found for MMR_GUILD_ID.")
    raw_df = raw_df.assign(season=normalize_season(raw_df))
    seasons = _target_seasons(raw_df, season_filter)
    raw_df = raw_df[raw_df["season"].isin(seasons)]
    calculation_id = os.environ.get("MMR_CALCULATION_ID", "").strip() or (
        f"mmr-once-{'+'.join(seasons)}-{scope_name}"
    )
    if season_filter is not None or guild_id is not None:
        print(
            "PARTIAL RUN: only "
            f"season={season_filter or 'all'!r}, guild_id={guild_id or 'all'!r} "
            "will be recalculated. Other seasons/guilds keep their existing rows."
        )
    # 5v5 검증 전 범위로 잡아, 경기가 전부 빠진 길드·시즌의 예전 행도 교체한다.
    replace_scopes = raw_df[["guild_id", "season"]].drop_duplicates().reset_index(drop=True)

    _assert_result_tables_ready()
    _assert_baseline_table_ready()
    _assert_recalculation_allowed(replace_scopes)
    # 계산 전에 모든 시즌의 baseline을 확인해, 중간에 baseline이 없어 멈추지 않게 한다.
    baselines = {season: _load_season_baseline(season) for season in seasons}

    season_runs = []
    for season in seasons:
        season_df = raw_df[raw_df["season"].eq(season)]
        season_run = None if season_df.empty else _calculate_season(
            season_df,
            season=season,
            baseline_payload=baselines[season],
            guild_id=guild_id,
            calculation_id=calculation_id,
        )
        if season_run is None:
            print(f"Skipped season {season!r}: no valid matches remain.")
            continue
        season_runs.append(season_run)
    if not season_runs:
        raise RuntimeError("No season has valid matches to calculate.")

    match_results = pd.concat([run["match_results"] for run in season_runs], ignore_index=True)
    user_summary = pd.concat([run["user_summary"] for run in season_runs], ignore_index=True)
    report = _build_report(
        season_runs=season_runs,
        calculation_id=calculation_id,
        guild_id=guild_id,
    )
    save_mmr_results(match_results, user_summary, sink="db", replace_scopes=replace_scopes)
    report["saved_to_db"] = True
    output_path = _write_report(report, calculation_id)
    print(f"Report: {output_path}")
    print("APPLIED: MMR results were written to the configured result tables.")


def _target_seasons(raw_df, season_filter: str | None) -> list[str]:
    """계산할 시즌 목록을 경기의 custom_match.season 기준으로 정한다."""
    seasons = sorted(normalize_season(raw_df).unique())
    if season_filter is None:
        return seasons
    if season_filter not in seasons:
        raise SystemExit(f"No eligible matches were found for MMR_SEASON={season_filter!r}.")
    return [season_filter]


def _assert_recalculation_allowed(replace_scopes) -> None:
    """대상 범위에 이미 결과가 있으면 명시적으로 허용했을 때만 교체한다.

    서비스 시작 뒤에는 백엔드가 한 경기씩 이어서 계산하므로, 이 배치를 다시 돌리면
    그 결과(시즌 중 baseline 전환 이력 포함)를 현재 baseline 하나로 덮어쓰게 된다.
    """
    existing = count_existing_results(replace_scopes)
    if existing and os.environ.get("MMR_ALLOW_RECALCULATE", "").strip() != "1":
        raise SystemExit(
            f"{existing:,} result rows already exist in the target guilds/seasons. "
            "This batch would delete and recalculate them. Set MMR_ALLOW_RECALCULATE=1 "
            "only before service start (or to intentionally rebuild history)."
        )
    if existing:
        print(f"MMR_ALLOW_RECALCULATE=1: replacing {existing:,} existing result rows.")


def _load_season_baseline(season: str) -> dict[str, Any]:
    """시즌의 활성 baseline(없으면 가장 최근 저장된 활성 baseline)을 읽고 검증한다."""
    try:
        baseline_payload = load_baseline_for_season(season)
        validate_baseline_payload(baseline_payload)
    except ValueError as exc:
        raise SystemExit(f"Season {season!r}: {exc}") from exc
    version = baseline_payload["baseline_version"]
    if (baseline_payload.get("metadata") or {}).get("scope") != BASELINE_SCOPE_ALL_GUILDS:
        raise SystemExit(
            f"Season {season!r}: baseline {version!r} (season {baseline_payload['season']!r}) "
            "was made by an old path, not scripts/calculate_baseline.py. Recreate it with "
            "scripts/calculate_baseline.py before calculating MMR."
        )
    source = baseline_payload["season"]
    note = (
        ""
        if source == season
        else f" (season {season!r} has none yet; using latest saved baseline from season {source!r})"
    )
    print(f"Season {season!r} uses baseline {version!r}{note}.")
    return baseline_payload


def _calculate_season(
    season_df,
    *,
    season: str,
    baseline_payload: dict[str, Any],
    guild_id: str | None,
    calculation_id: str,
) -> dict[str, Any] | None:
    """한 시즌을 초기 MMR부터 저장된 baseline으로 계산하고 결과·요약에 시즌을 붙인다.

    DB에 쓰지 않는다. 5v5 구조 검증을 통과한 경기가 없으면 ``None``을 반환한다.
    """
    # 5v5 검증 통과 경기가 없는 경우만 건너뛴다. 계산 중 다른 오류는 그대로 중단한다.
    try:
        result = calculate_full_mmr(
            {
                "calculation_id": calculation_id,
                "guild_id": guild_id,
                "season": season,
                "baseline_version": baseline_payload["baseline_version"],
                "mmr_baseline": baseline_payload["mmr_baseline"],
                "game_impact_baseline": baseline_payload["game_impact_baseline"],
                "matches": season_df.to_dict(orient="records"),
            }
        )
    except NoValidMatchesError as exc:
        print(f"Season {season!r}: {exc}")
        return None

    match_results = _prepare_match_results(result["match_results"], guild_id)
    user_summary = _prepare_user_summary(result["user_summary"], match_results)
    # 탈퇴자도 계산하고 summary를 유지한다. 노출할 때 guild_member.status로 거른다.
    position_summary = build_user_position_report(match_results)
    user_summary = attach_position_report(user_summary, position_summary)
    _assert_summary_covers_all_players(match_results, user_summary, season)
    # 어느 baseline으로 계산했는지 결과 행마다 남긴다(새 시즌 초반에는 가장 최근 저장된 baseline).
    match_results = match_results.assign(
        season=season,
        baseline_season=baseline_payload["season"],
        baseline_version=baseline_payload["baseline_version"],
    )
    user_summary = user_summary.assign(season=season)
    print(
        f"Calculated season {season!r}: "
        f"{result['metadata']['match_count']:,} matches, "
        f"{result['metadata']['player_game_row_count']:,} rows, "
        f"{len(user_summary):,} summary rows."
    )
    return {
        "season": season,
        "result": result,
        "baseline_payload": baseline_payload,
        "match_results": match_results,
        "user_summary": user_summary,
        "position_summary": position_summary.assign(season=season),
    }


def _assert_summary_covers_all_players(match_results, user_summary, season: str) -> None:
    """summary가 결과 행이 있는 모든 계정(탈퇴자 포함)을 한 행씩 갖는지 확인한다."""
    expected = match_results[["guild_id", "player_code"]].drop_duplicates()
    actual = user_summary[["guild_id", "player_code"]].drop_duplicates()
    if len(expected) != len(user_summary) or len(actual) != len(user_summary):
        raise RuntimeError(
            f"Season {season!r}: summary has {len(user_summary):,} rows for "
            f"{len(expected):,} accounts with results."
        )
    # 결과가 있는 계정은 리포트도 있어야 한다. 키가 어긋나면 left join이 조용히 {}를 남긴다.
    empty_reports = int((~user_summary["position_report"].map(bool)).sum())
    if empty_reports:
        raise RuntimeError(
            f"Season {season!r}: {empty_reports:,} summary rows have an empty position_report."
        )


def _prepare_match_results(rows: list[dict[str, Any]], guild_id: str | None):
    import pandas as pd

    out = pd.DataFrame(rows)
    if out["guild_id"].isna().any():
        raise RuntimeError("Calculated matches contain missing guild_id values.")
    if guild_id is not None and not out["guild_id"].eq(guild_id).all():
        raise RuntimeError("Calculated matches contain a different guild_id than requested.")
    return out


def _prepare_user_summary(rows: list[dict[str, Any]], match_results):
    import pandas as pd

    out = pd.DataFrame(rows)
    if out[["guild_id", "player_code"]].isna().any().any():
        raise RuntimeError("Calculated summaries require guild_id and player_code.")
    valid_keys = match_results[["guild_id", "player_code"]].drop_duplicates()
    checked = out.merge(
        valid_keys,
        on=["guild_id", "player_code"],
        how="left",
        indicator=True,
        validate="one_to_one",
    )
    if checked["_merge"].ne("both").any():
        raise RuntimeError("Calculated summary contains a player/guild absent from matches.")
    return out


def _build_report(
    *,
    season_runs: list[dict[str, Any]],
    calculation_id: str,
    guild_id: str | None,
) -> dict[str, Any]:
    return {
        "calculation_id": calculation_id,
        "guild_id": guild_id,
        "seasons": [run["season"] for run in season_runs],
        "metadata": {
            "seasons": {
                run["season"]: {
                    **run["result"]["metadata"],
                    "user_count": int(run["user_summary"]["player_code"].nunique()),
                    "summary_row_count": len(run["user_summary"]),
                    "baseline_season": run["baseline_payload"]["season"],
                    "baseline_version": run["baseline_payload"]["baseline_version"],
                }
                for run in season_runs
            },
        },
        "match_results": [
            row for run in season_runs for row in run["match_results"].to_dict(orient="records")
        ],
        "user_summary": [
            row for run in season_runs for row in run["user_summary"].to_dict(orient="records")
        ],
        "position_summary": [
            row for run in season_runs for row in run["position_summary"].to_dict(orient="records")
        ],
    }


def _write_report(report: dict[str, Any], calculation_id: str) -> Path:
    configured_path = os.environ.get("MMR_OUTPUT_FILE", "").strip()
    if configured_path:
        output_path = Path(configured_path)
        if not output_path.is_absolute():
            output_path = ROOT / output_path
    else:
        output_path = get_output_dir() / f"{_safe_filename(calculation_id)}.json"

    output_path.parent.mkdir(parents=True, exist_ok=True)
    with output_path.open("w", encoding="utf-8") as file:
        json.dump(report, file, ensure_ascii=False, indent=2, default=_json_default)
    return output_path


def _json_default(value: Any) -> Any:
    """Keep numpy scalars numeric and serialize timestamps predictably."""
    if hasattr(value, "item"):
        return value.item()
    if hasattr(value, "isoformat"):
        return value.isoformat()
    return str(value)


def _assert_baseline_table_ready() -> None:
    table_name = get_mmr_baseline_table()
    _validate_identifier(table_name)
    engine = create_engine(get_db_url())
    required_columns = {
        "id",
        "season",
        "baseline_version",
        "is_active",
        "mmr_baseline",
        "game_impact_baseline",
        "metadata",
        "saved_at",
    }
    with engine.connect() as conn:
        inspector = inspect(conn)
        if not inspector.has_table(table_name):
            raise RuntimeError(
                f"Required baseline table does not exist: {table_name}. "
                "Apply migrations/db_test/001_create_mmr_baselines.sql first."
            )
        actual_columns = {column["name"] for column in inspector.get_columns(table_name)}
        missing = sorted(required_columns - actual_columns)
        if missing:
            raise RuntimeError(
                f"Baseline table {table_name} is missing columns: {missing}."
            )


def _assert_result_tables_ready() -> None:
    engine = create_engine(get_db_url())
    required = {
        get_mmr_match_result_table(): {
            "replay_code", "player_code", "guild_id", "season",
            "baseline_season", "baseline_version",
        },
        get_mmr_summary_table(): {"player_code", "guild_id", "season", "position_report"},
    }
    # 006에서 지운 컬럼이 남아 있으면 006을 다시 적용해야 한다. 그대로 저장하면 NULL이 쌓인다.
    removed = {get_mmr_match_result_table(): {"mmr_player_account"}}
    with engine.connect() as conn:
        inspector = inspect(conn)
        for table_name, required_columns in required.items():
            _validate_identifier(table_name)
            if not inspector.has_table(table_name):
                raise RuntimeError(f"Required result table does not exist: {table_name}")
            actual_columns = {column["name"] for column in inspector.get_columns(table_name)}
            missing = sorted(required_columns - actual_columns)
            if missing:
                raise RuntimeError(
                    f"Result table {table_name} is missing columns: {missing}. "
                    "Apply the result-table migrations first."
                )
            leftover = sorted(removed.get(table_name, set()) & actual_columns)
            if leftover:
                raise RuntimeError(
                    f"Result table {table_name} still has removed columns: {leftover}. "
                    "Re-apply migrations/006_mmr_report_season_baseline.sql first."
                )


def _validate_identifier(value: str) -> None:
    if not re.fullmatch(r"[A-Za-z_][A-Za-z0-9_]*", value):
        raise RuntimeError(f"Unsafe result table identifier: {value!r}")


def _safe_filename(value: str) -> str:
    return re.sub(r"[^A-Za-z0-9_.-]", "_", value)


if __name__ == "__main__":
    main()
