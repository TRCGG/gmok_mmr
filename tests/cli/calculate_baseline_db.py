"""DB 테스트용 baseline 계산 스크립트.

주의:
    백엔드 연동 전 DB 원천 데이터로 baseline 계산을 검증하기 위한 임시 스크립트다.
    운영 실행 경로가 아니며, 백엔드 baseline 저장 API가 준비되면 삭제하거나 별도
    테스트 도구로 분리한다.
"""

from __future__ import annotations

import argparse
import os
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[2]
for _path in (ROOT / "src", ROOT / "tests"):
    if str(_path) not in sys.path:
        sys.path.insert(0, str(_path))

from mmr.gold.baseline import calculate_service_baseline, service_baseline_to_payload
from mmr.serving.service import build_base_feature_dataframe
from harness.db_test.baseline_repository import save_mmr_baseline_to_db_test
from harness.db_test.repository import load_match_dataframe_from_db
from harness.db_test.run_logger import MMRTestRunLogger


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--season", required=True)
    parser.add_argument("--baseline-version", required=True)
    parser.add_argument("--guild-id", default=None)
    parser.add_argument("--inactive", action="store_true")
    args = parser.parse_args()

    source_table = os.environ.get("MMR_PLAYER_GAME_TABLE", "player_game")

    with MMRTestRunLogger(
        script_name="calculate_baseline_db",
        season=args.season,
        baseline_version=args.baseline_version,
        source_table=source_table,
    ) as logger:
        raw_df = load_match_dataframe_from_db(guild_id=args.guild_id)
        feature_df = build_base_feature_dataframe(raw_df)
        baseline = calculate_service_baseline(
            feature_df,
            baseline_version=args.baseline_version,
            season=args.season,
        )
        payload = service_baseline_to_payload(
            baseline,
            match_count=feature_df["replay_code"].nunique(),
            player_game_row_count=len(feature_df),
        )
        save_mmr_baseline_to_db_test(payload, is_active=not args.inactive)

        logger.set_counts(
            match_count=payload["metadata"]["match_count"],
            player_game_row_count=payload["metadata"]["player_game_row_count"],
        )

    print(
        "Saved DB test baseline "
        f"{args.baseline_version} for season {args.season} "
        f"({payload['metadata']['match_count']:,} matches, "
        f"{payload['metadata']['player_game_row_count']:,} player-game rows)."
    )


if __name__ == "__main__":
    main()
