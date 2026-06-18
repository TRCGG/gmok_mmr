from __future__ import annotations

import pandas as pd

from mmr.gold.baseline import (
    calculate_service_baseline,
    service_baseline_to_payload,
)


def test_calculate_service_baseline_returns_serializable_payload():
    df = pd.DataFrame(
        {
            "replay_code": ["g1", "g1", "g2", "g2", "g3", "g3"],
            "position": ["TOP"] * 6,
            "game_result": [1, 0, 1, 0, 1, 0],
            "kills": [10, 2, 8, 3, 9, 1],
            "puuid": ["p1", "p2", "p3", "p4", "p5", "p6"],
        }
    )

    baseline = calculate_service_baseline(
        df,
        baseline_version="2026-06",
        season="2026",
        metrics=["kills"],
    )
    payload = service_baseline_to_payload(
        baseline,
        match_count=3,
        player_game_row_count=6,
    )

    assert payload["baseline_version"] == "2026-06"
    assert payload["season"] == "2026"
    assert "f1_mean" in payload["mmr_baseline"]
    assert "TOP" in payload["game_impact_baseline"]["position_weights"]
    assert payload["game_impact_baseline"]["outcome_stats"]
