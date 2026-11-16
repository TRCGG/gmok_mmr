"""DB baseline으로 한 시즌의 전체 MMR을 계산만 하는 확인용 스크립트.

주의:
    결과를 DB에 저장하지 않는다. 결과 저장은 ``scripts/run_mmr_once.py``로만 한다.

흐름:
    1. 원천 player-game 데이터를 DB에서 읽고 ``--season`` 경기만 고른다.
    2. ``mmr_baselines``에서 baseline을 읽는다. ``--baseline-version``이 없으면
       ``run_mmr_once.py``와 같은 규칙(그 시즌 활성 baseline, 없으면 가장 최근 저장된
       활성 baseline)을 쓴다.
    3. baseline을 검증(200판 이상, 퇴화 여부)한 뒤 전체 MMR을 계산하고 요약을 출력한다.
"""

from __future__ import annotations

import argparse
import os
from pathlib import Path
import sys

import pandas as pd

ROOT = Path(__file__).resolve().parents[2]
for _path in (ROOT / "src", ROOT / "tests"):
    if str(_path) not in sys.path:
        sys.path.insert(0, str(_path))

from mmr.gold.baseline import validate_baseline_payload
from mmr.serving.service import calculate_full_mmr
from harness.db_test.baseline_repository import (
    load_baseline_for_season,
    load_mmr_baseline_from_db_test,
)
from harness.db_test.repository import load_match_dataframe_from_db
from harness.db_test.run_logger import MMRTestRunLogger


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--season", required=True)
    parser.add_argument("--baseline-version", default=None)
    parser.add_argument("--guild-id", default=None)
    parser.add_argument("--calculation-id", default="db-test-full-mmr")
    args = parser.parse_args()

    season = args.season.strip()
    source_table = os.environ.get("MMR_PLAYER_GAME_TABLE", "player_game")

    if args.baseline_version is None:
        baseline_payload = load_baseline_for_season(season)
    else:
        baseline_payload = load_mmr_baseline_from_db_test(
            season=season,
            baseline_version=args.baseline_version,
            active_only=False,
        )
    try:
        validate_baseline_payload(baseline_payload)
    except ValueError as exc:
        raise SystemExit(str(exc)) from exc

    with MMRTestRunLogger(
        script_name="calculate_full_mmr_with_db_baseline",
        season=season,
        baseline_version=baseline_payload["baseline_version"],
        source_table=source_table,
    ) as logger:
        raw_df = load_match_dataframe_from_db(guild_id=args.guild_id)
        season_values = raw_df["season"].astype("string").str.strip()
        raw_df = raw_df[season_values.eq(season).fillna(False).astype(bool)]
        if raw_df.empty:
            raise SystemExit(f"No player-game rows found for season {season!r}.")

        result = calculate_full_mmr(
            {
                "calculation_id": args.calculation_id,
                "guild_id": args.guild_id,
                "season": season,
                "baseline_version": baseline_payload["baseline_version"],
                "mmr_baseline": baseline_payload["mmr_baseline"],
                "game_impact_baseline": baseline_payload["game_impact_baseline"],
                "matches": raw_df.to_dict(orient="records"),
            }
        )

        user_summary = pd.DataFrame(result["user_summary"])
        logger.set_counts(
            match_count=result["metadata"]["match_count"],
            player_game_row_count=result["metadata"]["player_game_row_count"],
            user_count=len(user_summary),
        )

    print(
        f"Calculated season {season!r} full MMR "
        f"with baseline {result['baseline_version']} "
        f"(baseline season {baseline_payload['season']!r}, "
        f"{result['metadata']['match_count']:,} matches, "
        f"{result['metadata']['player_game_row_count']:,} player-game rows, "
        f"{len(user_summary):,} users). Results were not saved."
    )


if __name__ == "__main__":
    main()
