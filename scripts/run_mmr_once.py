"""Run the MMR calculation once using values loaded from ``.env``.

This is a one-time DB batch helper. It reads raw player-game rows, calculates
the baseline, saves it, calculates full MMR, and saves the results when both
the configured database tables are ready.

Usage::

    python scripts/run_mmr_once.py

Required .env values::

    MMR_SEASON=2026-S1
    MMR_BASELINE_VERSION=2026-09

Optional .env values::

    MMR_GUILD_ID=your-guild-id  # omitted/empty means all guilds

Optional .env values::

    MMR_CALCULATION_ID=mmr-once-2026-09
    MMR_OUTPUT_FILE=./output/mmr-once.json
"""

from __future__ import annotations

import json
import os
from pathlib import Path
import re
import sys
from typing import Any

from sqlalchemy import bindparam, create_engine, inspect, text

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
from harness.db_test.account_mapping import attach_mmr_player_account, reject_duplicate_mmr_accounts
from harness.db_test.repository import load_guild_members_for_mmr, load_match_dataframe_from_db


def main() -> None:
    season = _required_env("MMR_SEASON")
    baseline_version = _required_env("MMR_BASELINE_VERSION")
    guild_id = os.environ.get("MMR_GUILD_ID", "").strip() or None
    scope_name = guild_id or "all"
    calculation_id = os.environ.get("MMR_CALCULATION_ID", "").strip() or (
        f"mmr-once-{season}-{baseline_version}-{scope_name}"
    )
    print(f"Loading raw MMR rows for guild_id={guild_id!r} ...")
    raw_df = load_match_dataframe_from_db(guild_id=guild_id)
    if raw_df.empty:
        raise SystemExit("No eligible player-game rows were found for MMR_GUILD_ID.")

    members = load_guild_members_for_mmr(guild_id=guild_id)
    raw_df = attach_mmr_player_account(raw_df, members)
    raw_df, rejected_matches = reject_duplicate_mmr_accounts(raw_df)
    if raw_df.empty:
        raise RuntimeError("No valid matches remain after MMR account conflict checks.")

    _assert_result_tables_ready()
    _assert_no_existing_matches(guild_id, raw_df)
    _assert_baseline_table_ready()

    feature_df = build_base_feature_dataframe(raw_df)
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

    save_mmr_baseline_to_db_test(baseline_payload, is_active=True)
    print(
        "Saved baseline "
        f"{baseline_version!r} for season {season!r} "
        f"(guild_id={guild_id!r})."
    )

    result = calculate_full_mmr(
        {
            "calculation_id": calculation_id,
            "guild_id": guild_id,
            "season": season,
            "baseline_version": baseline_version,
            "mmr_baseline": baseline_payload["mmr_baseline"],
            "game_impact_baseline": baseline_payload["game_impact_baseline"],
            "matches": raw_df.to_dict(orient="records"),
        }
    )

    match_results = _prepare_match_results(result["match_results"], guild_id)
    user_summary = _prepare_user_summary(result["user_summary"], match_results)
    report = _build_report(
        result=result,
        baseline_payload=baseline_payload,
        calculation_id=calculation_id,
        guild_id=guild_id,
        match_results=match_results,
        user_summary=user_summary,
        rejected_matches=rejected_matches,
    )
    print(
        "Calculated "
        f"{report['metadata']['match_count']:,} matches, "
        f"{report['metadata']['player_game_row_count']:,} rows, "
        f"{report['metadata']['user_count']:,} users."
    )
    if rejected_matches:
        print(f"Rejected {len(rejected_matches):,} matches with duplicate MMR accounts.")
    save_mmr_results(match_results, user_summary, sink="db")
    report["saved_to_db"] = True
    output_path = _write_report(report, calculation_id)
    print(f"Report: {output_path}")
    print("APPLIED: MMR results were written to the configured result tables.")


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
    result: dict[str, Any],
    baseline_payload: dict[str, Any],
    calculation_id: str,
    guild_id: str | None,
    match_results,
    user_summary,
    rejected_matches: list[dict[str, Any]],
) -> dict[str, Any]:
    return {
        "calculation_id": calculation_id,
        "guild_id": guild_id,
        "season": result.get("season"),
        "baseline_version": result.get("baseline_version"),
        "metadata": {
            **result["metadata"],
            "user_count": int(user_summary["player_code"].nunique()),
            "summary_row_count": len(user_summary),
            "rejected_match_count": len(rejected_matches),
        },
        "baseline_metadata": baseline_payload["metadata"],
        "match_results": match_results.to_dict(orient="records"),
        "user_summary": user_summary.to_dict(orient="records"),
        "rejected_matches": rejected_matches,
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
        get_mmr_match_result_table(): {"replay_code", "player_code", "mmr_player_account", "guild_id"},
        get_mmr_summary_table(): {"player_code", "guild_id"},
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


def _assert_no_existing_matches(guild_id: str | None, match_results) -> None:
    table_name = get_mmr_match_result_table()
    _validate_identifier(table_name)
    replay_codes = sorted(set(match_results["replay_code"].dropna().astype(str)))
    if not replay_codes:
        raise RuntimeError("Calculated results contain no replay_code values.")

    if guild_id is not None:
        query = text(
            f"""
            SELECT guild_id, replay_code
            FROM {table_name}
            WHERE guild_id = :guild_id
              AND replay_code IN :replay_codes
            """
        ).bindparams(bindparam("replay_codes", expanding=True))
        params = {"guild_id": guild_id, "replay_codes": replay_codes}
    else:
        query = text(
            f"""
            SELECT guild_id, replay_code
            FROM {table_name}
            WHERE replay_code IN :replay_codes
            """
        ).bindparams(bindparam("replay_codes", expanding=True))
        params = {"replay_codes": replay_codes}

    guild_values = (
        match_results["guild_id"]
        if "guild_id" in match_results.columns
        else [None] * len(match_results)
    )
    expected_pairs = {
        (
            None if _is_missing(guild) else str(guild),
            str(replay_code),
        )
        for guild, replay_code in zip(
            guild_values,
            match_results["replay_code"],
        )
    }

    engine = create_engine(get_db_url())
    with engine.connect() as conn:
        existing = {
            (
                None if row[0] is None else str(row[0]),
                str(row[1]),
            )
            for row in conn.execute(query, params)
            if (
                None if row[0] is None else str(row[0]),
                str(row[1]),
            ) in expected_pairs
        }

    if existing:
        sample = ", ".join(
            f"{pair[0] or '<NULL>'}/{pair[1]}"
            for pair in sorted(existing, key=lambda pair: (pair[0] or "", pair[1]))[:5]
        )
        raise RuntimeError(
            "Refusing to append duplicate MMR results for replay_code(s): "
            f"{sample}. Existing rows: {len(existing):,}."
        )


def _is_missing(value: Any) -> bool:
    return value is None or (isinstance(value, float) and value != value)


def _validate_identifier(value: str) -> None:
    if not re.fullmatch(r"[A-Za-z_][A-Za-z0-9_]*", value):
        raise RuntimeError(f"Unsafe result table identifier: {value!r}")


def _safe_filename(value: str) -> str:
    return re.sub(r"[^A-Za-z0-9_.-]", "_", value)


if __name__ == "__main__":
    main()
