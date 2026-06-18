"""MMR 서비스 baseline 계산을 조립하는 모듈."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import UTC, datetime
from typing import Any

import pandas as pd

from ..silver.features import BASE_METRICS, select_available_metrics
from ..silver.game_impact import (
    GameImpactBaseline,
    OutcomeNormalizationStats,
    apply_game_impact_baseline,
)
from .mmr import MMRBaselineStats


@dataclass(frozen=True)
class ServiceBaseline:
    """전체/단일 MMR 계산에 함께 사용하는 baseline 묶음."""

    baseline_version: str | None
    season: str | None
    mmr_baseline: MMRBaselineStats
    game_impact_baseline: GameImpactBaseline


def calculate_service_baseline(
    feature_df: pd.DataFrame,
    baseline_version: str | None = None,
    season: str | None = None,
    metrics: list[str] | None = None,
) -> ServiceBaseline:
    """시즌 전체 계산 준비 완료 player-game row로 서비스 baseline을 만든다."""
    metrics = select_available_metrics(feature_df, BASE_METRICS if metrics is None else metrics)
    if not metrics:
        raise RuntimeError("No usable metric columns were found for baseline calculation.")

    game_impact_baseline = GameImpactBaseline.from_history(feature_df, metrics=metrics)
    baseline_feature_df = apply_game_impact_baseline(feature_df, game_impact_baseline)
    mmr_baseline = MMRBaselineStats.from_df(baseline_feature_df)

    return ServiceBaseline(
        baseline_version=baseline_version,
        season=season,
        mmr_baseline=mmr_baseline,
        game_impact_baseline=game_impact_baseline,
    )


def service_baseline_to_payload(
    baseline: ServiceBaseline,
    match_count: int,
    player_game_row_count: int,
) -> dict[str, Any]:
    """baseline 묶음을 API 응답 데이터로 직렬화한다."""
    return {
        "season": baseline.season,
        "baseline_version": baseline.baseline_version,
        "mmr_baseline": {
            "f1_mean": baseline.mmr_baseline.f1_mean,
            "f2_mean": baseline.mmr_baseline.f2_mean,
        },
        "game_impact_baseline": game_impact_baseline_to_payload(
            baseline.game_impact_baseline
        ),
        "metadata": {
            "match_count": int(match_count),
            "player_game_row_count": int(player_game_row_count),
            "calculated_at": datetime.now(UTC).isoformat(),
        },
    }


def game_impact_baseline_to_payload(baseline: GameImpactBaseline) -> dict[str, Any]:
    """GameImpactBaseline을 JSON 친화적인 딕셔너리로 직렬화한다."""
    return {
        "position_weights": baseline.position_weights.to_dict(),
        "outcome_stats": [
            {
                "position": position,
                "game_result": result,
                "lower": stats.lower,
                "upper": stats.upper,
            }
            for (position, result), stats in baseline.outcome_stats.items()
        ],
    }


def game_impact_baseline_from_payload(payload: dict[str, Any]) -> GameImpactBaseline:
    """API 데이터에서 GameImpactBaseline을 복원한다."""
    position_weights = pd.DataFrame(payload["position_weights"])
    outcome_stats: dict[tuple[str, int], OutcomeNormalizationStats] = {}
    for row in payload.get("outcome_stats", []):
        outcome_stats[(row["position"], int(row["game_result"]))] = OutcomeNormalizationStats(
            lower=float(row["lower"]),
            upper=float(row["upper"]),
        )
    return GameImpactBaseline(
        position_weights=position_weights,
        outcome_stats=outcome_stats,
    )
