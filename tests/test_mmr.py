from __future__ import annotations

import numpy as np
import pandas as pd
import pytest

from mmr.gold.mmr import (
    DEFAULT_MMR_SETTINGS,
    MMRBaselineStats,
    MMRRuntimeState,
    MMRSettings,
    calculate_k_factor,
    calculate_personal_factor,
    expected_performance,
    make_summary_df_wide,
    update_mmr_elo,
    update_mmr_matches,
    update_single_match_mmr,
    validate_mmr_input_matches,
)


POSITIONS = ("TOP", "JUNGLE", "MIDDLE", "BOTTOM", "UTILITY")


def _valid_mmr_input() -> pd.DataFrame:
    rows = []
    for pos in POSITIONS:
        rows.append(
            {
                "played_at": pd.Timestamp("2026-01-01 10:00:00"),
                "replay_code": "g1",
                "puuid": f"{pos.lower()}_winner",
                "position": pos,
                "game_result": 1,
                "game_n_person_contribution": 1.2,
                "game_impact_vs_opponent": 70.0,
            }
        )
        rows.append(
            {
                "played_at": pd.Timestamp("2026-01-01 10:00:00"),
                "replay_code": "g1",
                "puuid": f"{pos.lower()}_loser",
                "position": pos,
                "game_result": 0,
                "game_n_person_contribution": 0.8,
                "game_impact_vs_opponent": 30.0,
            }
        )
    return pd.DataFrame(rows)


def test_expected_performance_is_even_for_equal_mmr():
    assert expected_performance(1300, 1300) == 0.5


def test_calculate_k_factor_decays_but_has_floor():
    assert calculate_k_factor(1300) == 1.0
    assert calculate_k_factor(1600) < 1.0
    assert calculate_k_factor(9999) == 0.35


def test_calculate_k_factor_accepts_custom_settings():
    settings = MMRSettings(k_decay_start=1000, k_decay_rate=0.01, k_min=0.2)

    assert calculate_k_factor(1100, settings=settings) == 0.2


def test_calculate_personal_factor_prefers_position_baseline():
    row = pd.Series({
        "position": "UTILITY",
        "game_n_person_contribution": 1.2,
        "game_impact_vs_opponent": 55.0,
    })

    overall_based = calculate_personal_factor(row, f1_mean=1.0, f2_mean=50.0)
    position_based = calculate_personal_factor(
        row,
        f1_mean=1.0,
        f2_mean=50.0,
        f1_position_mean={"UTILITY": 1.2},
        f2_position_mean={"UTILITY": 55.0},
    )

    assert position_based == pytest.approx(1.0)
    assert overall_based > position_based


def test_validate_mmr_input_matches_accepts_valid_ten_player_match():
    validate_mmr_input_matches(_valid_mmr_input())


def test_validate_mmr_input_matches_rejects_incomplete_match():
    df = _valid_mmr_input().iloc[:-1].copy()

    with pytest.raises(ValueError, match="each replay_code must contain 10 rows"):
        validate_mmr_input_matches(df)


def test_validate_mmr_input_matches_rejects_position_without_winner_and_loser():
    df = _valid_mmr_input()
    df.loc[df["puuid"] == "top_loser", "game_result"] = 1

    with pytest.raises(ValueError, match="one winner and one loser"):
        validate_mmr_input_matches(df)


def test_update_mmr_elo_creates_expected_columns_and_direction():
    updated, summary = update_mmr_elo(_valid_mmr_input())

    assert {"mmr_change", "pos_cumulative_mmr", "total_mmr"}.issubset(updated.columns)
    assert updated.loc[updated["puuid"] == "top_winner", "mmr_change"].item() > 0
    assert updated.loc[updated["puuid"] == "top_loser", "mmr_change"].item() < 0
    assert {"top_winner", "top_loser"}.issubset(set(summary["puuid"]))


def test_update_mmr_elo_accepts_custom_settings():
    settings = MMRSettings(
        initial_mmr=DEFAULT_MMR_SETTINGS.initial_mmr + 100,
        positions=POSITIONS,
    )

    updated, _ = update_mmr_elo(_valid_mmr_input(), settings=settings)

    assert updated["pre_game_pos_mmr"].eq(settings.initial_mmr).all()


def test_update_mmr_matches_matches_update_mmr_elo_rows():
    df = _valid_mmr_input()

    updated_from_core = update_mmr_matches(df)
    updated_from_public, _ = update_mmr_elo(df)

    pd.testing.assert_frame_equal(
        updated_from_core.reset_index(drop=True),
        updated_from_public.reset_index(drop=True),
    )


def test_update_single_match_mmr_uses_runtime_state_and_baseline():
    df = _valid_mmr_input()
    state = MMRRuntimeState()
    baseline = MMRBaselineStats.from_df(df)

    single_updated = update_single_match_mmr(df, state=state, baseline=baseline)
    full_updated, _ = update_mmr_elo(df)

    pd.testing.assert_frame_equal(
        single_updated.reset_index(drop=True),
        full_updated.reset_index(drop=True),
    )
    assert state.player_pos_record["top_winner"]["TOP"]["total"] == 1
    assert state.player_pos_mmr["top_winner"]["TOP"] == single_updated.loc[
        single_updated["puuid"] == "top_winner",
        "pos_cumulative_mmr",
    ].item()


def test_make_summary_df_wide_contains_position_columns():
    updated, _ = update_mmr_elo(_valid_mmr_input())
    summary = make_summary_df_wide(updated)

    assert "TOP_mmr" in summary.columns
    assert "TOP_winrate" in summary.columns
    assert "TOP_games" in summary.columns
    assert np.isclose(summary.loc[summary["puuid"] == "top_winner", "overall_winrate"].item(), 100)
