from __future__ import annotations

import numpy as np
import pandas as pd

from mmr_refactor.features import add_basic_features


def test_add_basic_features_creates_rate_and_efficiency_columns():
    df = pd.DataFrame(
        {
            "game_duration": [2.0],
            "deaths": [2],
            "kills": [4],
            "assists": [6],
            "gold": [1000],
            "damage_to_champions": [800],
            "damage_taken": [600],
            "cc_time": [20],
            "exp": [900],
            "damage_to_turrets": [200],
            "minions_killed": [10],
            "neutral_minions_killed": [4],
            "wards_placed": [6],
            "wards_killed": [2],
            "time_spent_dead": [30],
        }
    )

    out = add_basic_features(df)

    assert out["gold_per_min"].item() == 500
    assert out["dpm"].item() == 400
    assert out["damage_taken_per_min"].item() == 300
    assert out["cc_time_per_min"].item() == 10
    assert out["kda"].item() == 5
    assert out["damage_dealt_per_death"].item() == 400
    assert out["damage_taken_per_death"].item() == 300
    assert out["exp_per_min"].item() == 450
    assert out["damage_to_turrets_per_min"].item() == 100
    assert out["cs_per_min"].item() == 7
    assert out["wards_placed_per_min"].item() == 3
    assert out["wards_killed_per_min"].item() == 1
    assert out["dead_time_pct"].item() == 25


def test_add_basic_features_creates_lane_gold_diff_against_opponent():
    df = pd.DataFrame(
        {
            "replay_code": ["g1", "g1"],
            "position": ["TOP", "TOP"],
            "puuid": ["winner", "loser"],
            "game_duration": [2.0, 2.0],
            "deaths": [1, 1],
            "kills": [1, 1],
            "assists": [1, 1],
            "gold": [1200, 900],
            "damage_to_champions": [100, 100],
            "damage_taken": [100, 100],
            "cc_time": [10, 10],
        }
    )

    out = add_basic_features(df)

    assert out.loc[out["puuid"] == "winner", "lane_gold_diff"].item() == 300
    assert out.loc[out["puuid"] == "loser", "lane_gold_diff"].item() == -300


def test_add_basic_features_replaces_inf_when_duration_or_deaths_are_zero():
    df = pd.DataFrame(
        {
            "game_duration": [0],
            "deaths": [0],
            "kills": [1],
            "assists": [1],
            "gold": [1000],
            "damage_to_champions": [800],
            "damage_taken": [600],
            "cc_time": [20],
        }
    )

    out = add_basic_features(df)
    numeric = out.select_dtypes(include="number")

    assert not np.isinf(numeric.to_numpy()).any()
    assert not numeric.isna().any().any()
