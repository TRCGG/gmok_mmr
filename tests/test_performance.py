from __future__ import annotations

import numpy as np
import pandas as pd

from mmr.silver.performance import (
    BLOW_CLIP,
    PERF_Z_CLIP,
    BlowoutBaseline,
    PerformanceBaseline,
    RobustParam,
    StandardizeParam,
    all_perf_metrics,
    apply_performance_features,
    compute_blowout,
    compute_perf_z,
    derive_blowout_baseline,
    derive_performance_baseline,
    position_metric_weights,
)


POSITIONS = ("TOP", "JUNGLE", "MIDDLE", "BOTTOM", "UTILITY")


def _perf_population(n_per_pos: int = 12) -> pd.DataFrame:
    """포지션별로 변화가 있는 합성 모집단."""
    rng = np.random.default_rng(7)
    rows = []
    metrics = all_perf_metrics()
    for pos in POSITIONS:
        for i in range(n_per_pos):
            row = {"custom_match_id": f"m{i}", "position": pos, "puuid": f"{pos}_{i}"}
            for m in metrics:
                row[m] = float(rng.integers(0, 1000))
            rows.append(row)
    return pd.DataFrame(rows)


def test_position_metric_weights_merges_common_laning_role():
    w = position_metric_weights("UTILITY")
    # 공통
    assert w["kda"] == 0.8
    # 라인전
    assert w["lane_gold_diff"] == 0.8
    # 포지션 특화
    assert w["vision_score"] == 0.7
    assert "damage_to_champions" not in w  # UTILITY 특화에는 없음


def test_derive_and_compute_perf_z_is_clipped_and_centered():
    df = _perf_population()
    baseline = derive_performance_baseline(df)
    perf_z = compute_perf_z(df, baseline)

    assert perf_z.name == "perf_z"
    assert perf_z.between(-PERF_Z_CLIP, PERF_Z_CLIP).all()
    # 전역 재표준화이므로 평균은 0 근처
    assert abs(perf_z.mean()) < 1e-6 or abs(perf_z.mean()) < 0.5


def test_compute_perf_z_is_deterministic_with_saved_baseline():
    df = _perf_population()
    baseline = derive_performance_baseline(df)

    a = compute_perf_z(df, baseline)
    b = compute_perf_z(df, baseline)
    pd.testing.assert_series_equal(a, b)


def test_higher_metrics_yield_higher_perf_z_within_position():
    # 같은 포지션에서 지표가 전반적으로 높은 행이 더 높은 perf_z
    rows = []
    for i in range(10):
        rows.append({
            "custom_match_id": f"m{i}", "position": "MIDDLE", "puuid": f"p{i}",
            "kda": float(i), "dpm": float(i * 100), "gold_per_min": float(i * 50),
            "lane_gold_diff": float(i * 200), "takedowns_before_15min": float(i),
            "turret_plates_destroyed": float(i), "damage_to_champions": float(i * 1000),
            "cs_per_min": float(i),
        })
    df = pd.DataFrame(rows)
    baseline = derive_performance_baseline(df)
    perf_z = compute_perf_z(df, baseline)

    assert perf_z.iloc[-1] > perf_z.iloc[0]


def test_compute_blowout_ranks_blowout_above_close_game():
    # m1: 큰 골드차 + 짧은 시간(압승),  m2: 작은 골드차 + 긴 시간(접전)
    rows = []
    for team, gold in (("blue", 20000), ("red", 5000)):
        rows.append({"custom_match_id": "m1", "game_team": team,
                     "gold_earned": gold, "game_duration": 15.0})
    for team, gold in (("blue", 12000), ("red", 11900)):
        rows.append({"custom_match_id": "m2", "game_team": team,
                     "gold_earned": gold, "game_duration": 45.0})
    df = pd.DataFrame(rows)

    baseline = derive_blowout_baseline(df)
    blow = compute_blowout(df, baseline)

    assert blow.between(-1, 1).all()
    m1 = blow[df["custom_match_id"] == "m1"].iloc[0]
    m2 = blow[df["custom_match_id"] == "m2"].iloc[0]
    assert m1 > m2


def test_apply_performance_features_adds_both_columns():
    perf_df = _perf_population()
    perf_df["game_team"] = np.where(perf_df.index % 2 == 0, "blue", "red")
    perf_df["gold_earned"] = 10000.0
    perf_df["game_duration"] = 30.0

    perf_baseline = derive_performance_baseline(perf_df)
    blow_baseline = derive_blowout_baseline(perf_df)

    out = apply_performance_features(perf_df, perf_baseline, blow_baseline)
    assert "perf_z" in out.columns
    assert "blow" in out.columns
    assert out["perf_z"].notna().all()


def test_blow_uses_clip_on_extreme_standardized_value():
    param = RobustParam(center=0.0, scale=1.0)
    stats = StandardizeParam(mean=0.0, std=1.0)
    baseline = BlowoutBaseline(gold_diff=param, duration=param, blow_raw_stats=stats)
    # 극단적으로 큰 골드차 → 표준화값이 BLOW_CLIP을 넘어도 tanh(BLOW_CLIP) 이하
    rows = [
        {"custom_match_id": "m1", "game_team": "blue", "gold_earned": 1e9, "game_duration": 1.0},
        {"custom_match_id": "m1", "game_team": "red", "gold_earned": 0.0, "game_duration": 1.0},
    ]
    blow = compute_blowout(pd.DataFrame(rows), baseline)
    assert blow.iloc[0] <= np.tanh(BLOW_CLIP) + 1e-9


def test_global_restandardization_does_not_bias_positions():
    """가정 검증: 전역 재표준화(3-1(3))가 포지션 편향을 만들지 않는다.

    모든 포지션에 통계적으로 동일한 분포를 주면, 포지션별 perf_z 평균이
    서로 크게 벌어지지 않아야 한다(robust_z가 포지션별 중앙값으로 센터링되므로).
    이 가정이 깨지면(특정 포지션이 체계적으로 높음) 포지션별 정규화로 전환해야 한다.
    """
    rng = np.random.default_rng(11)
    metrics = all_perf_metrics()
    rows = []
    for pos in POSITIONS:
        # 포지션마다 동일한 분포(같은 시드 흐름)에서 표본 추출
        for i in range(40):
            row = {"custom_match_id": f"m{i}", "position": pos, "puuid": f"{pos}_{i}"}
            for m in metrics:
                row[m] = float(rng.normal(500, 100))
            rows.append(row)
    df = pd.DataFrame(rows)

    baseline = derive_performance_baseline(df)
    df["perf_z"] = compute_perf_z(df, baseline)

    pos_means = df.groupby("position")["perf_z"].mean()
    # 포지션 간 평균 격차가 작아야 한다 (편향 없음)
    assert pos_means.max() - pos_means.min() < 0.5


def test_perf_baseline_skips_missing_metrics():
    # 일부 지표만 존재해도 동작 (누락 지표는 기여 0)
    df = pd.DataFrame({
        "custom_match_id": ["m1", "m1"],
        "position": ["TOP", "TOP"],
        "puuid": ["a", "b"],
        "kda": [5.0, 1.0],
    })
    baseline = derive_performance_baseline(df)
    assert isinstance(baseline, PerformanceBaseline)
    perf_z = compute_perf_z(df, baseline)
    assert perf_z.iloc[0] > perf_z.iloc[1]
