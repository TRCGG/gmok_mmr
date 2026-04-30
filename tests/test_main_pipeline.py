from __future__ import annotations

import numpy as np
import pandas as pd

from main_pipeline import add_basic_features


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
