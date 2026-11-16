"""MMR 서비스 baseline 계산을 조립하는 모듈."""

from __future__ import annotations

from dataclasses import dataclass
import math
import numbers
from datetime import UTC, datetime
from typing import Any

import pandas as pd

from ..silver.features import BASE_METRICS, select_available_metrics
from ..silver.game_impact import (
    GameImpactBaseline,
    ImpactRange,
    OutcomeNormalizationStats,
    apply_game_impact_baseline,
)
from .mmr import DEFAULT_POSITIONS, MMRBaselineStats


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
            "f1_position_mean": baseline.mmr_baseline.f1_position_mean,
            "f2_position_mean": baseline.mmr_baseline.f2_position_mean,
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
        "impact_range": {
            "lower": baseline.impact_range.lower,
            "upper": baseline.impact_range.upper,
        },
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
    impact_range = payload.get("impact_range")
    if not impact_range:
        raise ValueError(
            "game_impact_baseline has no impact_range. "
            "Recreate the baseline with scripts/calculate_baseline.py."
        )
    return GameImpactBaseline(
        position_weights=position_weights,
        outcome_stats=outcome_stats,
        impact_range=ImpactRange(
            lower=float(impact_range["lower"]),
            upper=float(impact_range["upper"]),
        ),
    )


# baseline을 새로 계산할 때 필요한 시즌 최소 경기 수.
MIN_BASELINE_MATCHES = 200


def validate_baseline_payload(
    baseline_payload: dict[str, Any],
    *,
    min_matches: int = MIN_BASELINE_MATCHES,
) -> None:
    """표본이 부족하거나 퇴화한 baseline을 저장·사용하지 않도록 검증한다.

    포지션별 승·패 표본이 부족하면 Game Impact 가중치나 정규화 기준이 비고 MMR
    변화량이 고정폭이 된다. 그런 baseline이 활성화되면 이후 모든 경기가 같은 값으로
    계산된다. 문제가 있으면 ``ValueError``를 낸다.
    """
    problems = []
    match_count = (baseline_payload.get("metadata") or {}).get("match_count")
    if not _is_integer(match_count):
        problems.append(f"match_count={match_count!r} is not an integer")
    elif match_count < min_matches:
        problems.append(f"match_count={match_count} < {min_matches}")

    game_impact = baseline_payload.get("game_impact_baseline") or {}
    weights = game_impact.get("position_weights") or {}
    for pos in DEFAULT_POSITIONS:
        values = list((weights.get(pos) or {}).values())
        if not values:
            problems.append(f"no Game Impact weights for {pos}")
        elif not all(_is_finite(value) for value in values) or sum(values) <= 0:
            problems.append(f"invalid Game Impact weights for {pos}")

    covered = {
        (row.get("position"), row.get("game_result"))
        for row in game_impact.get("outcome_stats") or []
        if _is_finite(row.get("lower"))
        and _is_finite(row.get("upper"))
        and row["upper"] > row["lower"]
    }
    missing_outcomes = [
        f"{pos}/{result}"
        for pos in DEFAULT_POSITIONS
        for result in (0, 1)
        if (pos, result) not in covered
    ]
    if missing_outcomes:
        problems.append(f"no outcome_stats for {missing_outcomes}")

    impact_range = game_impact.get("impact_range") or {}
    lower, upper = impact_range.get("lower"), impact_range.get("upper")
    if not (_is_finite(lower) and _is_finite(upper) and upper > lower):
        problems.append(f"invalid game_impact impact_range={impact_range!r}")

    mmr_baseline = baseline_payload.get("mmr_baseline") or {}
    for key in ("f1_mean", "f2_mean"):
        value = mmr_baseline.get(key)
        if not _is_finite(value) or value == 0:
            problems.append(f"{key}={value!r}")
    for key in ("f1_position_mean", "f2_position_mean"):
        means = mmr_baseline.get(key) or {}
        bad = [pos for pos in DEFAULT_POSITIONS if not _is_finite(means.get(pos))]
        if bad:
            problems.append(f"{key} missing for {bad}")

    if problems:
        raise ValueError(
            f"Baseline for season {baseline_payload.get('season')!r} is unusable: "
            + "; ".join(problems)
        )


def _is_integer(value: Any) -> bool:
    return isinstance(value, numbers.Integral) and not isinstance(value, bool)


def _is_finite(value: Any) -> bool:
    return (
        isinstance(value, numbers.Real)
        and not isinstance(value, bool)
        and math.isfinite(value)
    )
