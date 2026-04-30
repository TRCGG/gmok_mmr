from __future__ import annotations

import numpy as np
import pandas as pd

from mmr_refactor.game_impact import (
    compute_n_person_contribution,
    compute_raw_game_impact,
    compute_vs_opponent,
    normalize_by_position_outcome,
    normalize_minmax_0_100,
)


def test_compute_raw_game_impact_uses_position_weights():
    df = pd.DataFrame(
        {
            "position": ["TOP", "JUNGLE"],
            "kills": [10, 4],
            "assists": [2, 8],
        }
    )
    weights = pd.DataFrame(
        {
            "TOP": {"kills": 0.8, "assists": 0.2},
            "JUNGLE": {"kills": 0.3, "assists": 0.7},
        }
    )

    out = compute_raw_game_impact(df, weights)

    assert out.tolist() == [8.4, 6.8]


def test_normalize_minmax_0_100_scales_bounds():
    out = normalize_minmax_0_100(pd.Series([10, 20, 30], name="score"))

    assert out.tolist() == [0.0, 50.0, 100.0]


def test_normalize_by_position_outcome_returns_groupwise_scores():
    df = pd.DataFrame(
        {
            "position": ["TOP", "TOP", "TOP", "TOP", "JUNGLE", "JUNGLE"],
            "game_result": [1, 1, 0, 0, 1, 1],
            "raw_game_impact": [10, 20, 30, 40, 1, 2],
        }
    )

    out = normalize_by_position_outcome(df, max_quantiles=10)

    assert out.notna().all()
    assert out.between(0, 100).all()
    assert out.name == "game_impact_winloss_norm"


def test_compute_n_person_contribution_sums_to_ten_per_game():
    df = pd.DataFrame(
        {
            "replay_code": ["g1", "g1", "g2", "g2"],
            "game_impact_winloss_norm": [25, 75, 10, 30],
        }
    )

    out = compute_n_person_contribution(df)

    assert np.isclose(out[df["replay_code"] == "g1"].sum(), 10)
    assert np.isclose(out[df["replay_code"] == "g2"].sum(), 10)


def test_compute_vs_opponent_matches_same_game_and_position():
    df = pd.DataFrame(
        {
            "replay_code": ["g1", "g1", "g1", "g1"],
            "position": ["TOP", "TOP", "JUNGLE", "JUNGLE"],
            "game_result": [1, 0, 1, 0],
            "game_impact_winloss_norm": [70, 30, 40, 60],
            "puuid": ["top_w", "top_l", "jg_w", "jg_l"],
        }
    )

    out = compute_vs_opponent(df)

    scores = dict(zip(df["puuid"], out))
    assert scores["top_w"] == 70
    assert scores["top_l"] == 30
    assert scores["jg_w"] == 40
    assert scores["jg_l"] == 60
