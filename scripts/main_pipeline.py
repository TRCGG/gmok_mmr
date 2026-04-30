"""Run the MMR pipeline from configured input to configured output.

Default test mode:
    DB raw data -> MMR pipeline -> DB result tables

Future service mode:
    Backend API raw data -> MMR pipeline -> Backend API result endpoint
"""

from __future__ import annotations

import argparse
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[1]
SRC = ROOT / "src"
if str(SRC) not in sys.path:
    sys.path.insert(0, str(SRC))

import numpy as np

from mmr_refactor import (
    clean_match_data,
    compute_n_person_contribution,
    compute_raw_game_impact,
    compute_vs_opponent,
    derive_position_weights,
    load_match_dataframe,
    normalize_by_position_outcome,
    normalize_minmax_0_100,
    save_mmr_results,
    update_mmr_elo,
)


BASE_METRICS = [
    "kills",
    "deaths",
    "assists",
    "gold_per_min",
    "dpm",
    "damage_taken_per_min",
    "vision_score",
    "kda",
    "damage_taken_per_death",
    "damage_dealt_per_death",
    "cc_time_per_min",
]


def add_basic_features(df):
    """Create DB-compatible derived features used by the MMR notebook logic."""
    out = df.copy()
    duration = out["game_duration"].replace(0, np.nan)
    deaths = out["deaths"].replace(0, np.nan)

    out["gold_per_min"] = out["gold"] / duration
    out["dpm"] = out["damage_to_champions"] / duration
    out["damage_taken_per_min"] = out["damage_taken"] / duration
    out["cc_time_per_min"] = out["cc_time"] / duration
    out["kda"] = (out["kills"] + out["assists"]) / deaths
    out["damage_taken_per_death"] = out["damage_taken"] / deaths
    out["damage_dealt_per_death"] = out["damage_to_champions"] / deaths

    out = out.replace([np.inf, -np.inf], np.nan)
    numeric_cols = out.select_dtypes(include="number").columns
    out[numeric_cols] = out[numeric_cols].fillna(0)
    return out


def run_pipeline(source: str | None = None, sink: str | None = None):
    raw_df = load_match_dataframe(source=source)
    clean_df = clean_match_data(raw_df, convert_duration_to_minutes=True)
    feature_df = add_basic_features(clean_df)

    metrics = [c for c in BASE_METRICS if c in feature_df.columns]
    if not metrics:
        raise RuntimeError("No usable metric columns were found for Game Impact calculation.")

    position_weights = derive_position_weights(feature_df, metrics=metrics)
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
