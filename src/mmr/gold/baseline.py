"""MMR 서비스 baseline(v2) 계산·직렬화 모듈.

baseline은 전체 모집단 표준화 기준을 고정 저장해, 증분(단일경기) 계산이 전체
재계산과 동일 결과를 내도록 한다(산식 문서 §3-1·§3-2, interface_spec §10).
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import UTC, datetime
from typing import Any

import pandas as pd

from ..silver.performance import (
    BlowoutBaseline,
    PerformanceBaseline,
    RobustParam,
    StandardizeParam,
    derive_blowout_baseline,
    derive_performance_baseline,
)


@dataclass(frozen=True)
class ServiceBaseline:
    """전체/증분 MMR 계산에 함께 쓰는 baseline 묶음."""

    baseline_version: str | None
    season: str | None
    performance_baseline: PerformanceBaseline
    blowout_baseline: BlowoutBaseline


def calculate_service_baseline(
    feature_df: pd.DataFrame,
    baseline_version: str | None = None,
    season: str | None = None,
) -> ServiceBaseline:
    """시즌 전체 player-game row로 perf·blowout baseline을 학습한다."""
    performance_baseline = derive_performance_baseline(feature_df)
    blowout_baseline = derive_blowout_baseline(feature_df)
    return ServiceBaseline(
        baseline_version=baseline_version,
        season=season,
        performance_baseline=performance_baseline,
        blowout_baseline=blowout_baseline,
    )


# ==============================================================
# 직렬화 / 역직렬화
# ==============================================================

def _robust_to_dict(param: RobustParam) -> dict[str, float]:
    return {"center": param.center, "scale": param.scale}


def _robust_from_dict(d: dict[str, Any]) -> RobustParam:
    return RobustParam(center=float(d["center"]), scale=float(d["scale"]))


def _std_to_dict(param: StandardizeParam) -> dict[str, float]:
    return {"mean": param.mean, "std": param.std}


def _std_from_dict(d: dict[str, Any]) -> StandardizeParam:
    return StandardizeParam(mean=float(d["mean"]), std=float(d["std"]))


def performance_baseline_to_payload(baseline: PerformanceBaseline) -> dict[str, Any]:
    return {
        "robust_params": [
            {"position": pos, "metric": metric, "center": p.center, "scale": p.scale}
            for (pos, metric), p in baseline.robust_params.items()
        ],
        "raw_perf_stats": _std_to_dict(baseline.raw_perf_stats),
    }


def performance_baseline_from_payload(payload: dict[str, Any]) -> PerformanceBaseline:
    robust_params: dict[tuple[str, str], RobustParam] = {}
    for row in payload.get("robust_params", []):
        robust_params[(row["position"], row["metric"])] = _robust_from_dict(row)
    return PerformanceBaseline(
        robust_params=robust_params,
        raw_perf_stats=_std_from_dict(payload["raw_perf_stats"]),
    )


def blowout_baseline_to_payload(baseline: BlowoutBaseline) -> dict[str, Any]:
    return {
        "gold_diff": _robust_to_dict(baseline.gold_diff),
        "duration": _robust_to_dict(baseline.duration),
        "blow_raw_stats": _std_to_dict(baseline.blow_raw_stats),
    }


def blowout_baseline_from_payload(payload: dict[str, Any]) -> BlowoutBaseline:
    return BlowoutBaseline(
        gold_diff=_robust_from_dict(payload["gold_diff"]),
        duration=_robust_from_dict(payload["duration"]),
        blow_raw_stats=_std_from_dict(payload["blow_raw_stats"]),
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
        "performance_baseline": performance_baseline_to_payload(baseline.performance_baseline),
        "blowout_baseline": blowout_baseline_to_payload(baseline.blowout_baseline),
        "metadata": {
            "match_count": int(match_count),
            "player_game_row_count": int(player_game_row_count),
            "calculated_at": datetime.now(UTC).isoformat(),
        },
    }
