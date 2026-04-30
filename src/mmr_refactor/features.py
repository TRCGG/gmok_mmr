"""Feature engineering helpers for the MMR pipeline."""

from __future__ import annotations

import numpy as np
import pandas as pd


BASE_METRICS = [
    "kills",
    "deaths",
    "assists",
    "gold_per_min",
    "exp_per_min",
    "dpm",
    "damage_to_turrets_per_min",
    "damage_taken_per_min",
    "vision_score",
    "cs_per_min",
    "kda",
    "damage_taken_per_death",
    "damage_dealt_per_death",
    "wards_placed_per_min",
    "wards_killed_per_min",
    "cc_time_per_min",
    "heal_on_teammates",
    "shield_on_teammates",
    "lane_gold_diff",
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

    if "exp" in out.columns:
        out["exp_per_min"] = out["exp"] / duration
    if "damage_to_turrets" in out.columns:
        out["damage_to_turrets_per_min"] = out["damage_to_turrets"] / duration
    if {"minions_killed", "neutral_minions_killed"}.issubset(out.columns):
        out["cs_per_min"] = (
            out["minions_killed"] + out["neutral_minions_killed"]
        ) / duration
    if "wards_placed" in out.columns:
        out["wards_placed_per_min"] = out["wards_placed"] / duration
    if "wards_killed" in out.columns:
        out["wards_killed_per_min"] = out["wards_killed"] / duration
    if "time_spent_dead" in out.columns:
        out["dead_time_pct"] = out["time_spent_dead"] / (duration * 60) * 100

    if "lane_gold_diff" not in out.columns and {
        "replay_code",
        "position",
        "puuid",
        "gold",
    }.issubset(out.columns):
        out["lane_gold_diff"] = _compute_lane_gold_diff(out)

    out = out.replace([np.inf, -np.inf], np.nan)
    numeric_cols = out.select_dtypes(include="number").columns
    out[numeric_cols] = out[numeric_cols].fillna(0)
    return out


def _compute_lane_gold_diff(df: pd.DataFrame) -> pd.Series:
    """Return gold difference against the same-game same-position opponent."""
    opponent_gold_sum = df.groupby(["replay_code", "position"])["gold"].transform("sum") - df["gold"]
    opponent_count = df.groupby(["replay_code", "position"])["gold"].transform("count") - 1
    opponent_gold = opponent_gold_sum / opponent_count.replace(0, np.nan)
    return df["gold"] - opponent_gold


def select_available_metrics(
    df: pd.DataFrame,
    metrics: list[str] | None = None,
) -> list[str]:
    """Return configured metric columns that exist in the given DataFrame."""
    metric_candidates = BASE_METRICS if metrics is None else metrics
    return [column for column in metric_candidates if column in df.columns]
