"""Run the MMR calculation once using values loaded from ``.env``.

This is a one-time DB batch helper. It reads raw player-game rows, calculates
the baseline, saves it, calculates full MMR, and saves the results when both
the configured database tables are ready.

Usage::

    python scripts/run_mmr_once.py

Seasons come from each match's ``custom_match.season``. Every season is
calculated independently from the initial MMR with its own baseline.

Required .env values::

    MMR_BASELINE_VERSION=2026-09

Optional .env values::

    MMR_SEASON=2026             # omitted/empty means every season in the data
    MMR_GUILD_ID=your-guild-id  # omitted/empty means all guilds
    MMR_CALCULATION_ID=mmr-once-2026-09
    MMR_OUTPUT_FILE=./output/mmr-once.json
"""

from __future__ import annotations

import json
import math
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

from mmr.gold.baseline import calculate_service_baseline, service_baseline_to_payload
from mmr.gold.mmr import DEFAULT_POSITIONS
from mmr.gold.report import (
    attach_position_report,
    build_user_position_report,
    filter_active_guild_members,
)
from mmr.serving.service import calculate_full_mmr, build_base_feature_dataframe
from harness.config import get_output_dir
from harness.data_writer import save_mmr_results
from harness.db_test.config import (
    get_db_url,
    get_mmr_baseline_table,
    get_mmr_match_result_table,
    get_mmr_summary_table,
)
from harness.db_test.baseline_repository import save_mmr_baseline_to_db_test
from harness.db_test.repository import load_guild_members_for_mmr, load_match_dataframe_from_db


def main() -> None:
    import pandas as pd

    season_filter = os.environ.get("MMR_SEASON", "").strip() or None
    baseline_version = _required_env("MMR_BASELINE_VERSION")
    guild_id = os.environ.get("MMR_GUILD_ID", "").strip() or None
    scope_name = guild_id or "all"
    print(f"Loading raw MMR rows for guild_id={guild_id!r} ...")
    raw_df = load_match_dataframe_from_db(guild_id=guild_id)
    if raw_df.empty:
        raise SystemExit("No eligible player-game rows were found for MMR_GUILD_ID.")
    raw_df = raw_df.assign(season=_season_values(raw_df))
    seasons = _target_seasons(raw_df, season_filter)
    raw_df = raw_df[raw_df["season"].isin(seasons)]
    calculation_id = os.environ.get("MMR_CALCULATION_ID", "").strip() or (
        f"mmr-once-{'+'.join(seasons)}-{baseline_version}-{scope_name}"
    )
    if season_filter is not None or guild_id is not None:
        print(
            "PARTIAL RUN: only "
            f"season={season_filter or 'all'!r}, guild_id={guild_id or 'all'!r} "
            "will be recalculated. Other seasons/guilds keep their existing rows."
        )
    # 5v5 검증 전 범위로 잡아, 경기가 전부 빠진 길드·시즌의 예전 행도 교체한다.
    replace_scopes = raw_df[["guild_id", "season"]].drop_duplicates().reset_index(drop=True)

    # MMR은 부캐 매핑을 보지 않는다. 부캐도 실제 계정(player_code)으로 별도 MMR을 갖는다.
    raw_df = raw_df.assign(mmr_player_account=raw_df["player_code"])
    members = load_guild_members_for_mmr(guild_id=guild_id)

    _assert_result_tables_ready()
    _assert_baseline_table_ready()

    season_runs = []
    for season in seasons:
        season_df = raw_df[raw_df["season"].eq(season)]
        season_run = None if season_df.empty else _calculate_season(
            season_df,
            season=season,
            baseline_version=baseline_version,
            guild_id=guild_id,
            calculation_id=calculation_id,
            members=members,
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
    # 모든 시즌 계산이 끝난 뒤에 baseline을 저장해, 중간 실패 시 baseline만 바뀌지 않게 한다.
    for run in season_runs:
        save_mmr_baseline_to_db_test(run["baseline_payload"], is_active=True)
        print(
            "Saved baseline "
            f"{baseline_version!r} for season {run['season']!r} "
            f"(guild_id={guild_id!r})."
        )
    save_mmr_results(match_results, user_summary, sink="db", replace_scopes=replace_scopes)
    report["saved_to_db"] = True
    output_path = _write_report(report, calculation_id)
    print(f"Report: {output_path}")
    print("APPLIED: MMR results were written to the configured result tables.")


def _season_values(raw_df):
    """경기의 custom_match.season을 공백 없는 문자열로 맞추고 빈 값은 거부한다."""
    if "season" not in raw_df.columns:
        raise RuntimeError("Raw matches require custom_match.season values.")
    seasons = raw_df["season"]
    blank = seasons.isna() | seasons.astype(str).str.strip().eq("")
    if blank.any():
        missing = raw_df.loc[blank]
        sample = (
            missing["replay_code"].drop_duplicates().head(5).tolist()
            if "replay_code" in missing.columns
            else missing.index[:5].tolist()
        )
        raise RuntimeError(
            f"Raw matches require custom_match.season values. Missing for: {sample}"
        )
    return seasons.astype(str).str.strip()


def _target_seasons(raw_df, season_filter: str | None) -> list[str]:
    """계산할 시즌 목록을 경기의 custom_match.season 기준으로 정한다."""
    seasons = sorted(_season_values(raw_df).unique())
    if season_filter is None:
        return seasons
    if season_filter not in seasons:
        raise SystemExit(f"No eligible matches were found for MMR_SEASON={season_filter!r}.")
    return [season_filter]


def _calculate_season(
    season_df,
    *,
    season: str,
    baseline_version: str,
    guild_id: str | None,
    calculation_id: str,
    members,
) -> dict[str, Any] | None:
    """한 시즌을 초기 MMR부터 계산하고 결과·요약에 시즌을 붙인다.

    DB에 쓰지 않는다. baseline은 반환값으로 넘겨 모든 시즌 계산 후 저장한다.
    5v5 구조 검증을 통과한 경기가 없으면 ``None``을 반환한다.
    """
    try:
        feature_df = build_base_feature_dataframe(season_df)
    except RuntimeError as exc:
        print(f"Season {season!r}: {exc}")
        return None
    baseline = calculate_service_baseline(
        feature_df,
        baseline_version=baseline_version,
        season=season,
    )
    baseline_payload = service_baseline_to_payload(
        baseline,
        match_count=feature_df[["guild_id", "replay_code"]].drop_duplicates().shape[0],
        player_game_row_count=len(feature_df),
    )
    baseline_payload["metadata"]["guild_id"] = guild_id
    _assert_baseline_usable(baseline_payload, season)

    result = calculate_full_mmr(
        {
            "calculation_id": calculation_id,
            "guild_id": guild_id,
            "season": season,
            "baseline_version": baseline_version,
            "mmr_baseline": baseline_payload["mmr_baseline"],
            "game_impact_baseline": baseline_payload["game_impact_baseline"],
            "matches": season_df.to_dict(orient="records"),
        }
    )

    match_results = _prepare_match_results(result["match_results"], guild_id)
    all_players = _prepare_user_summary(result["user_summary"], match_results)
    position_summary = filter_active_guild_members(
        build_user_position_report(match_results), members
    )
    user_summary = attach_position_report(all_players, position_summary)
    _assert_active_members_found(match_results, user_summary, season)
    match_results = match_results.assign(season=season)
    user_summary = user_summary.assign(season=season)
    print(
        f"Calculated season {season!r}: "
        f"{result['metadata']['match_count']:,} matches, "
        f"{result['metadata']['player_game_row_count']:,} rows, "
        f"{len(user_summary):,} summary rows "
        f"({len(all_players) - len(user_summary):,} non-member players excluded)."
    )
    return {
        "season": season,
        "result": result,
        "baseline_payload": baseline_payload,
        "match_results": match_results,
        "user_summary": user_summary,
        "position_summary": position_summary.assign(season=season),
    }


def _assert_active_members_found(match_results, user_summary, season: str) -> None:
    """현재 길드원 판정이 통째로 실패해 요약을 비운 채 저장하지 않도록 막는다.

    해산 등으로 한 길드의 길드원이 0명일 수는 있으므로 경고만 하고, 시즌 전체
    요약이 0행이면 길드원 테이블 설정이나 status 판정 오류로 보고 중단한다.
    """
    if user_summary.empty:
        raise RuntimeError(
            f"Season {season!r} has no current guild members in the summary. "
            "Check MMR_GUILD_MEMBER_TABLE and guild_member.status before saving."
        )
    empty_guilds = sorted(
        set(match_results["guild_id"].astype(str)) - set(user_summary["guild_id"].astype(str))
    )
    if empty_guilds:
        print(
            f"WARNING: season {season!r} guilds with no current members in summary: "
            f"{empty_guilds}"
        )


def _assert_baseline_usable(baseline_payload: dict[str, Any], season: str) -> None:
    """표본이 부족해 퇴화한 baseline을 저장·사용하지 않도록 중단한다.

    포지션별 승·패 표본이 부족하면 Game Impact 가중치가 비고 MMR 변화량이 고정폭이
    된다. 그런 baseline이 활성화되면 백엔드도 같은 값으로 이후 경기를 계산한다.
    """
    weights = baseline_payload["game_impact_baseline"].get("position_weights") or {}
    mmr_baseline = baseline_payload["mmr_baseline"]
    problems = []
    missing_positions = [pos for pos in DEFAULT_POSITIONS if not weights.get(pos)]
    if missing_positions:
        problems.append(f"no Game Impact weights for {missing_positions}")
    for key in ("f1_mean", "f2_mean"):
        value = mmr_baseline.get(key)
        if value is None or not math.isfinite(value) or value == 0:
            problems.append(f"{key}={value!r}")
    for key in ("f1_position_mean", "f2_position_mean"):
        means = mmr_baseline.get(key) or {}
        bad = [pos for pos in DEFAULT_POSITIONS if not _is_finite(means.get(pos))]
        if bad:
            problems.append(f"{key} missing for {bad}")
    if problems:
        raise RuntimeError(
            f"Baseline for season {season!r} is unusable (too few matches): "
            + "; ".join(problems)
        )


def _is_finite(value: Any) -> bool:
    return isinstance(value, (int, float)) and math.isfinite(value)


def _required_env(name: str) -> str:
    value = os.environ.get(name, "").strip()
    if not value:
        raise SystemExit(f"Missing required .env value: {name}")
    return value


def _prepare_match_results(rows: list[dict[str, Any]], guild_id: str | None):
    import pandas as pd

    out = pd.DataFrame(rows)
    if out["guild_id"].isna().any():
        raise RuntimeError("Calculated matches contain missing guild_id values.")
    if guild_id is not None and not out["guild_id"].eq(guild_id).all():
        raise RuntimeError("Calculated matches contain a different guild_id than requested.")
    # MMR은 부캐 매핑을 보지 않으므로 귀속 계정은 항상 실제 참가 계정과 같아야 한다.
    if "mmr_player_account" in out.columns:
        mismatched = out[out["mmr_player_account"].ne(out["player_code"])]
        if not mismatched.empty:
            sample = mismatched[["guild_id", "replay_code", "player_code", "mmr_player_account"]]
            raise RuntimeError(
                "mmr_player_account must equal player_code (no alt-account mapping). "
                f"Sample: {sample.head().to_dict('records')}"
            )
    return out


def _prepare_user_summary(rows: list[dict[str, Any]], match_results):
    import pandas as pd

    out = pd.DataFrame(rows)
    if out[["guild_id", "player_code"]].isna().any().any():
        raise RuntimeError("Calculated summaries require guild_id and player_code.")
    key_column = "mmr_player_account" if "mmr_player_account" in match_results else "player_code"
    valid_keys = match_results[["guild_id", key_column]].drop_duplicates().rename(
        columns={key_column: "player_code"}
    )
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
        "baseline_version": season_runs[0]["result"].get("baseline_version"),
        "metadata": {
            "seasons": {
                run["season"]: {
                    **run["result"]["metadata"],
                    "user_count": int(run["user_summary"]["player_code"].nunique()),
                    "summary_row_count": len(run["user_summary"]),
                    "baseline_metadata": run["baseline_payload"]["metadata"],
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
        "season",
        "baseline_version",
        "is_active",
        "mmr_baseline",
        "game_impact_baseline",
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
            "replay_code", "player_code", "mmr_player_account", "guild_id", "season"
        },
        get_mmr_summary_table(): {"player_code", "guild_id", "season", "position_report"},
    }
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


def _validate_identifier(value: str) -> None:
    if not re.fullmatch(r"[A-Za-z_][A-Za-z0-9_]*", value):
        raise RuntimeError(f"Unsafe result table identifier: {value!r}")


def _safe_filename(value: str) -> str:
    return re.sub(r"[^A-Za-z0-9_.-]", "_", value)


if __name__ == "__main__":
    main()
