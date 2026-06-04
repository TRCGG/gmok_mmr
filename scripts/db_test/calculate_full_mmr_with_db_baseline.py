"""DB 테스트용 전체 MMR 계산 스크립트.

주의:
    이 스크립트는 백엔드가 baseline을 저장/전달하기 전까지 DB로 전체 흐름을
    검증하기 위한 임시 코드다. 운영 실행 경로가 아니며, 백엔드 연동이 끝나면
    삭제하거나 별도 테스트 도구로 분리한다.

흐름:
    1. 원천 player-game 데이터를 DB에서 읽는다.
    2. DB 테스트용 baseline 테이블에서 baseline payload를 읽는다.
    3. 기존 MMR service 함수에 baseline을 주입해 전체 MMR을 계산한다.
    4. --save-results 옵션이 있을 때만 기존 DB 결과 테이블에 저장한다.
"""

from __future__ import annotations

import argparse
from pathlib import Path
import sys

import pandas as pd

ROOT = Path(__file__).resolve().parents[2]
SRC = ROOT / "src"
if str(SRC) not in sys.path:
    sys.path.insert(0, str(SRC))

from mmr_refactor.data_writer import save_mmr_results
from mmr_refactor.db_test.baseline_repository import load_mmr_baseline_from_db_test
from mmr_refactor.db_test.repository import load_match_dataframe_from_db
from mmr_refactor.service import calculate_full_mmr


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--season", required=True)
    parser.add_argument("--baseline-version", default=None)
    parser.add_argument("--guild-id", default=None)
    parser.add_argument("--calculation-id", default="db-test-full-mmr")
    parser.add_argument("--save-results", action="store_true")
    args = parser.parse_args()

    baseline_payload = load_mmr_baseline_from_db_test(
        season=args.season,
        baseline_version=args.baseline_version,
        active_only=args.baseline_version is None,
    )

    raw_df = load_match_dataframe_from_db()
    if args.guild_id is not None:
        raw_df = raw_df[raw_df["guild_id"].astype(str) == str(args.guild_id)].copy()
    if raw_df.empty:
        raise RuntimeError("No player-game rows found for full MMR DB test.")

    result = calculate_full_mmr(
        {
            "calculation_id": args.calculation_id,
            "guild_id": args.guild_id,
            "season": args.season,
            "baseline_version": baseline_payload["baseline_version"],
            "mmr_baseline": baseline_payload["mmr_baseline"],
            "game_impact_baseline": baseline_payload["game_impact_baseline"],
            "matches": raw_df.to_dict(orient="records"),
        }
    )

    match_results = pd.DataFrame(result["match_results"])
    user_summary = pd.DataFrame(result["user_summary"])

    if args.save_results:
        save_mmr_results(match_results, user_summary, sink="db")

    print(
        "Calculated DB test full MMR "
        f"with baseline {result['baseline_version']} "
        f"({result['metadata']['match_count']:,} matches, "
        f"{result['metadata']['player_game_row_count']:,} player-game rows, "
        f"{len(user_summary):,} users)."
    )
    if not args.save_results:
        print("Results were not saved. Pass --save-results to write DB result tables.")


if __name__ == "__main__":
    main()
