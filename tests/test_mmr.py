from __future__ import annotations

import numpy as np
import pandas as pd

from mmr_refactor.mmr import (
    calculate_k_factor,
    expected_performance,
    make_summary_df_wide,
    update_mmr_elo,
)


def _minimal_mmr_input() -> pd.DataFrame:
    return pd.DataFrame(
        [
            {
                "played_at": pd.Timestamp("2026-01-01 10:00:00"),
                "replay_code": "g1",
                "puuid": "winner",
                "position": "TOP",
                "game_result": 1,
                "game_n_person_contribution": 1.2,
                "game_impact_vs_opponent": 70.0,
            },
            {
                "played_at": pd.Timestamp("2026-01-01 10:00:00"),
                "replay_code": "g1",
                "puuid": "loser",
                "position": "TOP",
                "game_result": 0,
                "game_n_person_contribution": 0.8,
                "game_impact_vs_opponent": 30.0,
            },
        ]
    )


def test_expected_performance_is_even_for_equal_mmr():
    assert expected_performance(1300, 1300) == 0.5


def test_calculate_k_factor_decays_but_has_floor():
    assert calculate_k_factor(1300) == 1.0
    assert calculate_k_factor(1600) < 1.0
    assert calculate_k_factor(9999) == 0.35


def test_update_mmr_elo_creates_expected_columns_and_direction():
    updated, summary = update_mmr_elo(_minimal_mmr_input())

    assert {"mmr_change", "pos_cumulative_mmr", "total_mmr"}.issubset(updated.columns)
    assert updated.loc[updated["puuid"] == "winner", "mmr_change"].item() > 0
    assert updated.loc[updated["puuid"] == "loser", "mmr_change"].item() < 0
    assert summary["puuid"].tolist() == ["winner", "loser"]


def test_make_summary_df_wide_contains_position_columns():
    updated, _ = update_mmr_elo(_minimal_mmr_input())
    summary = make_summary_df_wide(updated)

    assert "TOP_mmr" in summary.columns
    assert "TOP_winrate" in summary.columns
    assert "TOP_games" in summary.columns
    assert np.isclose(summary.loc[summary["puuid"] == "winner", "overall_winrate"].item(), 100)
