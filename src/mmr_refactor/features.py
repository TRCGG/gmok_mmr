"""Feature engineering helpers for the MMR pipeline."""

from __future__ import annotations

import numpy as np
import pandas as pd


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


def add_basic_features(df: pd.DataFrame) -> pd.DataFrame:
    """Create DB-compatible derived features used by the MMR logic."""
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


def select_available_metrics(
    df: pd.DataFrame,
    metrics: list[str] | None = None,
) -> list[str]:
    """Return configured metric columns that exist in the given DataFrame."""
    metric_candidates = BASE_METRICS if metrics is None else metrics
    return [column for column in metric_candidates if column in df.columns]
