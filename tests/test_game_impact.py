from __future__ import annotations

import numpy as np
import pandas as pd

from mmr.gold.baseline import (
    game_impact_baseline_from_payload,
    game_impact_baseline_to_payload,
)
from mmr.silver.game_impact import (
    GameImpactBaseline,
    ImpactRange,
    OutcomeNormalizationStats,
    apply_game_impact_baseline,
    apply_impact_range,
    apply_outcome_normalization_stats,
    compute_n_person_contribution,
    compute_raw_game_impact,
    compute_vs_opponent,
    derive_impact_range,
    derive_outcome_normalization_stats,
    normalize_by_position_outcome,
    normalize_minmax_0_100,
    resolve_position_weights,
)


def test_compute_raw_game_impact_uses_position_weights():
    df = pd.DataFrame(
        {
            "position": ["TOP", "JUG"],
            "kills": [10, 4],
            "assists": [2, 8],
        }
    )
    weights = pd.DataFrame(
        {
            "TOP": {"kills": 0.8, "assists": 0.2},
            "JUG": {"kills": 0.3, "assists": 0.7},
        }
    )

    out = compute_raw_game_impact(df, weights)

    assert out.tolist() == [8.4, 6.8]


def test_resolve_position_weights_uses_supplied_weights():
    df = pd.DataFrame(
        {
            "position": ["TOP", "TOP"],
            "game_result": [1, 0],
            "kills": [10, 1],
        }
    )
    weights = pd.DataFrame({"TOP": {"kills": 1.0}})

    out = resolve_position_weights(df, metrics=["kills"], position_weights=weights)

    assert out.equals(weights)
    assert out is not weights


def test_normalize_minmax_0_100_scales_bounds():
    out = normalize_minmax_0_100(pd.Series([10, 20, 30], name="score"))

    assert out.tolist() == [0.0, 50.0, 100.0]


def test_normalize_by_position_outcome_returns_groupwise_scores():
    df = pd.DataFrame(
        {
            "position": ["TOP", "TOP", "TOP", "TOP", "JUG", "JUG"],
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


def test_compute_n_person_contribution_uses_whole_game_share():
    positions = ["TOP", "JUG", "MID", "ADC", "SUP"]
    impacts = {
        "TOP": (80, 20),
        "JUG": (10, 10),
        "MID": (20, 20),
        "ADC": (30, 30),
        "SUP": (40, 40),
    }
    rows = []
    for position in positions:
        for impact in impacts[position]:
            rows.append({
                "replay_code": "g1",
                "position": position,
                "game_impact_winloss_norm": impact,
            })
    df = pd.DataFrame(rows)

    out = compute_n_person_contribution(df)

    assert np.isclose(out.sum(), 10)
    expected = df["game_impact_winloss_norm"] / df["game_impact_winloss_norm"].sum() * 10
    assert np.allclose(out, expected)
    position_totals = out.groupby(df["position"]).sum()
    assert position_totals["TOP"] > position_totals["JUG"]


def test_compute_vs_opponent_matches_same_game_and_position():
    df = pd.DataFrame(
        {
            "replay_code": ["g1", "g1", "g1", "g1"],
            "position": ["TOP", "TOP", "JUG", "JUG"],
            "game_result": [1, 0, 1, 0],
            "game_impact_winloss_norm": [70, 30, 40, 60],
            "player_code": ["top_w", "top_l", "jg_w", "jg_l"],
        }
    )

    out = compute_vs_opponent(df)

    scores = dict(zip(df["player_code"], out))
    assert scores["top_w"] == 70
    assert scores["top_l"] == 30
    assert scores["jg_w"] == 40
    assert scores["jg_l"] == 60


def test_opponent_comparison_separates_guilds_with_same_replay_code():
    df = pd.DataFrame({
        "guild_id": ["guild-a", "guild-a", "guild-b", "guild-b"],
        "replay_code": ["shared"] * 4,
        "position": ["TOP"] * 4,
        "game_result": [1, 0, 1, 0],
        "game_impact_winloss_norm": [80, 20, 30, 70],
        "player_code": ["a-w", "a-l", "b-w", "b-l"],
    })

    assert compute_vs_opponent(df).tolist() == [80, 20, 30, 70]


def test_compute_vs_opponent_preserves_original_index():
    df = pd.DataFrame(
        {
            "replay_code": ["g1", "g1"],
            "position": ["TOP", "TOP"],
            "game_result": [1, 0],
            "game_impact_winloss_norm": [65, 35],
            "player_code": ["winner", "loser"],
        },
        index=[101, 205],
    )

    out = compute_vs_opponent(df)

    assert out.index.tolist() == [101, 205]
    assert out.loc[101] == 65
    assert out.loc[205] == 35


def test_apply_outcome_normalization_stats_uses_stored_bounds():
    df = pd.DataFrame(
        {
            "position": ["TOP", "TOP"],
            "game_result": [1, 0],
            "raw_game_impact": [15, 30],
        }
    )
    stats = {
        ("TOP", 1): OutcomeNormalizationStats(lower=10, upper=20),
        ("TOP", 0): OutcomeNormalizationStats(lower=20, upper=40),
    }

    out = apply_outcome_normalization_stats(df, stats)

    assert out.tolist() == [50.0, 50.0]


def test_apply_game_impact_baseline_builds_incremental_features():
    df = pd.DataFrame(
        {
            "replay_code": ["g1", "g1"],
            "position": ["TOP", "TOP"],
            "game_result": [1, 0],
            "kills": [10, 2],
            "assists": [0, 0],
            "player_code": ["winner", "loser"],
        }
    )
    baseline = GameImpactBaseline(
        position_weights=pd.DataFrame({"TOP": {"kills": 1.0, "assists": 0.0}}),
        outcome_stats={
            ("TOP", 1): OutcomeNormalizationStats(lower=0, upper=20),
            ("TOP", 0): OutcomeNormalizationStats(lower=0, upper=20),
        },
        impact_range=ImpactRange(lower=0, upper=20),
    )

    out = apply_game_impact_baseline(df, baseline)

    assert out["game_impact_winloss_norm"].tolist() == [50.0, 10.0]
    assert np.isclose(out["game_n_person_contribution"].sum(), 10)
    assert np.allclose(
        out["game_impact_vs_opponent"],
        [83.33333333333334, 16.666666666666668],
    )


def test_derive_outcome_normalization_stats_returns_position_result_keys():
    df = pd.DataFrame(
        {
            "position": ["TOP", "TOP", "TOP"],
            "game_result": [1, 1, 0],
            "raw_game_impact": [10, 20, 30],
        }
    )

    stats = derive_outcome_normalization_stats(df)

    assert ("TOP", 1) in stats
    assert ("TOP", 0) in stats
    assert stats[("TOP", 1)].lower < stats[("TOP", 1)].upper


# ---------------------------------------------------------------------------
# game_impact: 노트북처럼 시즌 전체 min/max 기준 0~100 (baseline에 저장)
# ---------------------------------------------------------------------------

def _history() -> pd.DataFrame:
    rows = []
    for game, (top_win, top_loss) in enumerate([(12, 3), (20, 8), (6, 1), (15, 9)]):
        for player, result, kills in (("w", 1, top_win), ("l", 0, top_loss)):
            rows.append({
                "replay_code": f"g{game}",
                "position": "TOP",
                "game_result": result,
                "kills": kills,
                "assists": 0,
                "player_code": f"{player}{game}",
            })
    return pd.DataFrame(rows)


def _history_baseline(history: pd.DataFrame) -> GameImpactBaseline:
    return GameImpactBaseline.from_history(
        history,
        metrics=["kills", "assists"],
        position_weights=pd.DataFrame({"TOP": {"kills": 1.0, "assists": 0.0}}),
    )


def test_impact_range_is_history_min_max():
    history = _history()

    baseline = _history_baseline(history)

    assert baseline.impact_range == ImpactRange(lower=1.0, upper=20.0)


def test_full_history_game_impact_matches_notebook_minmax():
    history = _history()
    baseline = _history_baseline(history)

    out = apply_game_impact_baseline(history, baseline)
    notebook = normalize_minmax_0_100(
        compute_raw_game_impact(history, baseline.position_weights)
    )

    assert np.allclose(out["game_impact"], notebook)


def test_single_match_game_impact_uses_season_scale_not_match_scale():
    history = _history()
    baseline = _history_baseline(history)
    full = apply_game_impact_baseline(history, baseline)

    single = apply_game_impact_baseline(history[history["replay_code"].eq("g0")], baseline)

    # 한 경기만 넣어도 시즌 전체 계산과 같은 점수가 나온다(10명 안 MinMax가 아님).
    assert np.allclose(single["game_impact"], full.loc[single.index, "game_impact"])
    assert not np.allclose(single["game_impact"], [100.0, 0.0])


def test_game_impact_outside_season_range_is_clipped():
    scored = apply_impact_range(pd.Series([0.0, 10.0, 30.0]), ImpactRange(lower=5.0, upper=25.0))

    assert scored.tolist() == [0.0, 25.0, 100.0]


def test_invalid_impact_range_returns_nan():
    scored = apply_impact_range(pd.Series([1.0, 2.0]), ImpactRange(lower=3.0, upper=3.0))

    assert scored.isna().all()
    # 유효한 raw 값이 없으면 범위도 NaN이다.
    assert np.isnan(derive_impact_range(pd.Series([np.nan, np.inf])).lower)


def test_impact_range_round_trips_through_payload():
    baseline = _history_baseline(_history())

    payload = game_impact_baseline_to_payload(baseline)
    restored = game_impact_baseline_from_payload(payload)

    assert payload["impact_range"] == {"lower": 1.0, "upper": 20.0}
    assert restored.impact_range == baseline.impact_range


def test_payload_without_impact_range_is_rejected():
    payload = game_impact_baseline_to_payload(_history_baseline(_history()))
    del payload["impact_range"]

    try:
        game_impact_baseline_from_payload(payload)
    except ValueError as exc:
        assert "impact_range" in str(exc)
    else:
        raise AssertionError("baseline without impact_range must be rejected")
