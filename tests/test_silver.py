from __future__ import annotations

import numpy as np
import pandas as pd

from mmr.silver import add_basic_features, clean_match_data, filter_eligible, find_rows_with_na


def test_filter_eligible_drops_ineligible_and_deleted():
    df = pd.DataFrame({
        "puuid": ["a", "b", "c"],
        "is_mmr_eligible": [True, False, True],
        "is_deleted": [False, False, True],
    })
    out = filter_eligible(df)
    assert out["puuid"].tolist() == ["a"]


def test_clean_match_data_filters_dedups_and_converts():
    df = pd.DataFrame(
        [
            {"puuid": "p1", "win": True, "game_duration": 120,
             "is_mmr_eligible": True, "is_deleted": False,
             "heal_on_teammates": None, "shield_on_teammates": None},
            {"puuid": "p1", "win": True, "game_duration": 120,
             "is_mmr_eligible": True, "is_deleted": False,
             "heal_on_teammates": None, "shield_on_teammates": None},
            {"puuid": "p2", "win": False, "game_duration": 90,
             "is_mmr_eligible": True, "is_deleted": False,
             "heal_on_teammates": 7, "shield_on_teammates": 3},
        ]
    )
    out = clean_match_data(df)

    assert len(out) == 2
    assert "win" not in out.columns
    assert out.loc[out["puuid"] == "p1", "game_result"].item() == 1
    assert out.loc[out["puuid"] == "p2", "game_result"].item() == 0
    assert out.loc[out["puuid"] == "p1", "game_duration"].item() == 2.0
    assert out.loc[out["puuid"] == "p1", "heal_on_teammates"].item() == 0


def test_add_basic_features_creates_rate_and_efficiency_columns():
    df = pd.DataFrame(
        {
            "game_duration": [2.0],
            "deaths": [2],
            "kills": [4],
            "assists": [6],
            "gold_earned": [1000],
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


def test_add_basic_features_does_not_overwrite_existing_ddl_columns():
    df = pd.DataFrame({
        "game_duration": [2.0],
        "deaths": [2],
        "kills": [4],
        "assists": [6],
        "gold_earned": [1000],
        "gold_per_min": [999.0],  # 이미 DDL 값 존재 → 보존
    })
    out = add_basic_features(df)
    assert out["gold_per_min"].item() == 999.0


def test_add_basic_features_lane_gold_diff_against_opponent():
    df = pd.DataFrame(
        {
            "custom_match_id": ["g1", "g1"],
            "position": ["TOP", "TOP"],
            "puuid": ["winner", "loser"],
            "game_duration": [2.0, 2.0],
            "deaths": [1, 1],
            "kills": [1, 1],
            "assists": [1, 1],
            "gold_earned": [1200, 900],
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
            "gold_earned": [1000],
            "damage_to_champions": [800],
            "damage_taken": [600],
            "cc_time": [20],
        }
    )

    out = add_basic_features(df)
    numeric = out.select_dtypes(include="number")

    assert not np.isinf(numeric.to_numpy()).any()
    assert not numeric.isna().any().any()


def test_find_rows_with_na_ignores_excluded_columns():
    df = pd.DataFrame(
        {
            "puuid": ["p1", "p2", "p3"],
            "kills": [1, None, 3],
            "dragon_kills": [None, None, None],
        }
    )

    out = find_rows_with_na(df, na_exclude_cols=("dragon_kills",))

    assert out["puuid"].tolist() == ["p2"]
