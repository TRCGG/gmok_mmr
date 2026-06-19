from __future__ import annotations

import numpy as np
import pandas as pd

from mmr.gold.baseline import (
    blowout_baseline_from_payload,
    blowout_baseline_to_payload,
    calculate_service_baseline,
    performance_baseline_from_payload,
    performance_baseline_to_payload,
    service_baseline_to_payload,
)
from mmr.silver.performance import all_perf_metrics, compute_blowout, compute_perf_z


POSITIONS = ("TOP", "JUNGLE", "MIDDLE", "BOTTOM", "UTILITY")


def _feature_df(n_matches: int = 6) -> pd.DataFrame:
    rng = np.random.default_rng(3)
    rows = []
    metrics = all_perf_metrics()
    for g in range(n_matches):
        for pos in POSITIONS:
            for team in ("blue", "red"):
                row = {
                    "custom_match_id": f"g{g}",
                    "position": pos,
                    "game_team": team,
                    "puuid": f"{pos}_{team}_{g}",
                    "gold_earned": float(rng.integers(8000, 20000)),
                    "game_duration": float(rng.integers(15, 45)),
                }
                for m in metrics:
                    row.setdefault(m, float(rng.integers(0, 1000)))
                rows.append(row)
    return pd.DataFrame(rows)


def test_calculate_service_baseline_returns_serializable_payload():
    df = _feature_df()
    baseline = calculate_service_baseline(df, baseline_version="2026-06", season="2026")
    payload = service_baseline_to_payload(baseline, match_count=6, player_game_row_count=len(df))

    assert payload["baseline_version"] == "2026-06"
    assert payload["season"] == "2026"
    assert payload["performance_baseline"]["robust_params"]
    assert "mean" in payload["performance_baseline"]["raw_perf_stats"]
    assert "gold_diff" in payload["blowout_baseline"]
    assert payload["metadata"]["match_count"] == 6


def test_performance_baseline_payload_roundtrip_reproduces_perf_z():
    df = _feature_df()
    baseline = calculate_service_baseline(df)

    payload = performance_baseline_to_payload(baseline.performance_baseline)
    restored = performance_baseline_from_payload(payload)

    a = compute_perf_z(df, baseline.performance_baseline)
    b = compute_perf_z(df, restored)
    pd.testing.assert_series_equal(a, b)


def test_blowout_baseline_payload_roundtrip_reproduces_blow():
    df = _feature_df()
    baseline = calculate_service_baseline(df)

    payload = blowout_baseline_to_payload(baseline.blowout_baseline)
    restored = blowout_baseline_from_payload(payload)

    a = compute_blowout(df, baseline.blowout_baseline)
    b = compute_blowout(df, restored)
    pd.testing.assert_series_equal(a, b)
