"""설정된 입력에서 출력 저장소까지 MMR 파이프라인을 실행한다.

기본 테스트 모드:
    DB raw data -> MMR pipeline -> DB result tables

향후 서비스 모드:
    Backend API raw data -> MMR pipeline -> Backend API result endpoint
"""

from __future__ import annotations

import argparse
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[2]
for _path in (ROOT / "src", ROOT / "tests"):
    if str(_path) not in sys.path:
        sys.path.insert(0, str(_path))

from mmr import (
    add_basic_features,
    BASE_METRICS,
    clean_match_data,
    compute_n_person_contribution,
    compute_raw_game_impact,
    compute_vs_opponent,
    normalize_by_position_outcome,
    normalize_minmax_0_100,
    resolve_position_weights,
    select_available_metrics,
    update_mmr_elo,
)
from harness.data_loader import load_match_dataframe
from harness.data_writer import save_mmr_results


def run_pipeline(
    source: str | None = None,
    sink: str | None = None,
    position_weights=None,
):
    raw_df = load_match_dataframe(source=source)
    clean_df = clean_match_data(raw_df, convert_duration_to_minutes=True)
    feature_df = add_basic_features(clean_df)

    metrics = select_available_metrics(feature_df, BASE_METRICS)
    if not metrics:
        raise RuntimeError("No usable metric columns were found for Game Impact calculation.")

    position_weights = resolve_position_weights(
        feature_df,
        metrics=metrics,
        position_weights=position_weights,
    )
    feature_df["raw_game_impact"] = compute_raw_game_impact(feature_df, position_weights)
    feature_df["game_impact"] = normalize_minmax_0_100(feature_df["raw_game_impact"])
    feature_df["game_impact_winloss_norm"] = normalize_by_position_outcome(feature_df)
    feature_df["game_n_person_contribution"] = compute_n_person_contribution(feature_df)
    feature_df["game_impact_vs_opponent"] = compute_vs_opponent(feature_df)

    mmr_df_updated, summary_df = update_mmr_elo(feature_df)
    save_mmr_results(mmr_df_updated, summary_df, sink=sink)
    return mmr_df_updated, summary_df


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--source", choices=["db", "api"], default=None)
    parser.add_argument("--sink", choices=["db", "api"], default=None)
    args = parser.parse_args()

    mmr_df_updated, summary_df = run_pipeline(source=args.source, sink=args.sink)
    print(f"Saved {len(mmr_df_updated):,} match rows and {len(summary_df):,} summary rows.")


if __name__ == "__main__":
    main()
