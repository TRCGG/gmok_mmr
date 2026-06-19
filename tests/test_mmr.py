from __future__ import annotations

import pandas as pd
import pytest

from mmr.gold.mmr import (
    DEFAULT_MMR_SETTINGS,
    INIT_MMR,
    K_BASE,
    MMRRuntimeState,
    MMRSettings,
    calculate_k_factor,
    expected_performance,
    update_mmr_elo,
    update_mmr_matches,
    update_single_match_mmr,
    validate_mmr_input_matches,
)


POSITIONS = ("TOP", "JUNGLE", "MIDDLE", "BOTTOM", "UTILITY")


def _match(
    match_id: str,
    date: str,
    blue_wins: bool = True,
    perf_z: float = 0.0,
    blow: float = 0.0,
) -> pd.DataFrame:
    rows = []
    for pos in POSITIONS:
        rows.append({
            "played_date": pd.Timestamp(date),
            "custom_match_id": match_id,
            "puuid": f"{pos.lower()}_blue",
            "position": pos,
            "game_team": "blue",
            "game_result": 1 if blue_wins else 0,
            "perf_z": perf_z,
            "blow": blow,
        })
        rows.append({
            "played_date": pd.Timestamp(date),
            "custom_match_id": match_id,
            "puuid": f"{pos.lower()}_red",
            "position": pos,
            "game_team": "red",
            "game_result": 0 if blue_wins else 1,
            "perf_z": perf_z,
            "blow": blow,
        })
    return pd.DataFrame(rows)


# ---------------- 보조 함수 ----------------

def test_expected_performance_is_even_for_equal_mmr():
    assert expected_performance(1500, 1500) == 0.5


def test_expected_performance_favors_higher_mmr():
    assert expected_performance(1700, 1500) > 0.5


def test_calculate_k_factor_provisional_multiplier():
    base = calculate_k_factor(0.0, 0.0, total_games_before=10, win=True)
    prov = calculate_k_factor(0.0, 0.0, total_games_before=0, win=True)
    assert base == K_BASE
    assert prov == K_BASE * DEFAULT_MMR_SETTINGS.prov_mult


def test_calculate_k_factor_performance_direction():
    win_good = calculate_k_factor(1.0, 0.0, total_games_before=10, win=True)
    win_flat = calculate_k_factor(0.0, 0.0, total_games_before=10, win=True)
    loss_good = calculate_k_factor(1.0, 0.0, total_games_before=10, win=False)
    assert win_good > win_flat   # 이긴 경기에 잘했으면 K↑
    assert loss_good < win_flat  # 진 경기에 잘했으면 K↓ (손실 완화)


def test_calculate_k_factor_blowout_direction():
    blowout = calculate_k_factor(0.0, 1.0, total_games_before=10, win=True)
    close = calculate_k_factor(0.0, -1.0, total_games_before=10, win=True)
    assert blowout > K_BASE > close


def test_calculate_k_factor_has_floor():
    settings = MMRSettings(k_base=1.0)
    k = calculate_k_factor(-5.0, -1.0, total_games_before=10, win=False, settings=settings)
    assert k == settings.k_min


# ---------------- 구조 검증 ----------------

def test_validate_accepts_valid_match():
    validate_mmr_input_matches(_match("g1", "2026-01-01 10:00:00"))


def test_validate_rejects_incomplete_match():
    df = _match("g1", "2026-01-01 10:00:00").iloc[:-1].copy()
    with pytest.raises(ValueError, match="each custom_match_id must contain 10 rows"):
        validate_mmr_input_matches(df)


def test_validate_rejects_position_without_winner_and_loser():
    df = _match("g1", "2026-01-01 10:00:00")
    df.loc[df["puuid"] == "top_red", "game_result"] = 1
    with pytest.raises(ValueError, match="one winner and one loser"):
        validate_mmr_input_matches(df)


def test_validate_rejects_non_uniform_team_result():
    # 포지션 구조(1승1패)는 유지하되 팀 단위 승패가 섞이면 거부(팀 평균 Elo 전제 위반)
    df = _match("g1", "2026-01-01 10:00:00", blue_wins=True)
    df.loc[df["puuid"] == "jungle_blue", "game_result"] = 0
    df.loc[df["puuid"] == "jungle_red", "game_result"] = 1
    with pytest.raises(ValueError, match="2 teams"):
        validate_mmr_input_matches(df)


# ---------------- Elo 갱신 ----------------

def test_update_mmr_elo_direction_and_columns():
    updated, summary = update_mmr_elo(_match("g1", "2026-01-01 10:00:00"))

    assert {"mmr_change", "total_mmr", "pos_cumulative_mmr", "expected_score", "k_factor"}.issubset(updated.columns)
    assert updated.loc[updated["puuid"] == "top_blue", "mmr_change"].item() > 0
    assert updated.loc[updated["puuid"] == "top_red", "mmr_change"].item() < 0
    # 첫 경기(배치 ×1.5), E=0.5, blow=perf=0 → Δ = 32·1.5·0.5 = ±24
    assert updated.loc[updated["puuid"] == "top_blue", "mmr_change"].item() == 24
    assert updated.loc[updated["puuid"] == "top_red", "mmr_change"].item() == -24


def test_delta_applied_to_total_and_line_equally():
    updated, _ = update_mmr_elo(_match("g1", "2026-01-01 10:00:00"))
    blue = updated[updated["puuid"] == "top_blue"].iloc[0]
    assert blue["total_mmr"] == INIT_MMR + 24
    assert blue["pos_cumulative_mmr"] == INIT_MMR + 24


def test_provisional_multiplier_increases_first_game_delta():
    # 첫 경기는 배치 보정(×1.5)으로 Δ가 더 크다: 32*1.5*0.5 = 24
    updated, _ = update_mmr_elo(_match("g1", "2026-01-01 10:00:00"))
    assert updated.loc[updated["puuid"] == "top_blue", "mmr_change"].item() == 24


def test_single_match_matches_full_recompute():
    df = pd.concat([
        _match("g1", "2026-01-01 10:00:00", blue_wins=True),
        _match("g2", "2026-01-02 10:00:00", blue_wins=False),
    ], ignore_index=True)

    full = update_mmr_matches(df)

    state = MMRRuntimeState()
    part1 = update_single_match_mmr(_match("g1", "2026-01-01 10:00:00", blue_wins=True), state=state)
    part2 = update_single_match_mmr(_match("g2", "2026-01-02 10:00:00", blue_wins=False), state=state)
    incremental = pd.concat([part1, part2], ignore_index=True)

    key = ["custom_match_id", "puuid"]
    full_sorted = full.sort_values(key).reset_index(drop=True)
    inc_sorted = incremental.sort_values(key).reset_index(drop=True)
    pd.testing.assert_series_equal(
        full_sorted["total_mmr"], inc_sorted["total_mmr"], check_names=False
    )
    pd.testing.assert_series_equal(
        full_sorted["pos_cumulative_mmr"], inc_sorted["pos_cumulative_mmr"], check_names=False
    )


def test_make_summary_has_ranked_flag_and_position_columns():
    # 같은 플레이어가 20경기 이상 → is_ranked True
    matches = [
        _match(f"g{i}", f"2026-01-{i + 1:02d} 10:00:00", blue_wins=(i % 2 == 0))
        for i in range(21)
    ]
    df = pd.concat(matches, ignore_index=True)
    updated, summary = update_mmr_elo(df)

    assert "TOP_mmr" in summary.columns
    assert "is_ranked" in summary.columns
    assert "main_position" in summary.columns
    top_blue = summary[summary["puuid"] == "top_blue"].iloc[0]
    assert top_blue["total_games"] == 21
    assert bool(top_blue["is_ranked"]) is True


def test_make_summary_marks_provisional_under_cut():
    updated, summary = update_mmr_elo(_match("g1", "2026-01-01 10:00:00"))
    assert bool(summary["is_ranked"].iloc[0]) is False


def test_provisional_uses_total_games_not_position_games():
    """배치 보정(×1.5)은 해당 포지션 경기수가 아니라 total 누적경기 기준이어야 한다.

    top_blue: total 10경기(모두 다른 포지션) → 이번 TOP 경기는 비배치(K=32).
    jungle_blue: 신규(total 0) → 배치(K=48).
    """
    state = MMRRuntimeState()
    state.ensure_player("top_blue")
    state.total_games["top_blue"] = 10  # TOP 라인 경기수는 0이지만 total은 10

    updated = update_single_match_mmr(_match("g1", "2026-01-01 10:00:00"), state=state)

    top = updated[updated["puuid"] == "top_blue"].iloc[0]
    jungle = updated[updated["puuid"] == "jungle_blue"].iloc[0]
    assert top["k_factor"] == K_BASE                                  # 비배치
    assert jungle["k_factor"] == K_BASE * DEFAULT_MMR_SETTINGS.prov_mult  # 배치
