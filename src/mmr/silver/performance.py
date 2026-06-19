"""퍼포먼스 점수(perf_z) · 승부격차(blowout) 산정 모듈 (순수 함수).

MMR 산식 v2의 silver 계층. 산식 문서(`docs/MMR_산식_문서.md`) §3-1·§3-2를 구현한다.

- ``perf_z``  : 포지션별 robust z-score 가중합을 전역 재표준화한 개인 퍼포먼스 점수.
- ``blow``    : 경기 단위 승부격차 강도(−1~+1).

증분(단일경기) 계산이 전체 재계산과 동일 결과를 내도록, 표준화 기준값은
``PerformanceBaseline`` / ``BlowoutBaseline`` 에 저장해 두고 재사용한다.
"""

from __future__ import annotations

from dataclasses import dataclass

import numpy as np
import pandas as pd


# =====================================================
# 퍼포먼스 지표 가중치 (산식 문서 §3-1)
# =====================================================

COMMON_WEIGHTS: dict[str, float] = {
    "kda": 0.8,
    "dpm": 0.5,
    "gold_per_min": 0.4,
}

LANING_WEIGHTS: dict[str, float] = {
    "lane_gold_diff": 0.8,
    "takedowns_before_15min": 0.7,
    "turret_plates_destroyed": 0.4,
}

ROLE_WEIGHTS: dict[str, dict[str, float]] = {
    "TOP": {"damage_to_champions": 0.4, "damage_self_mitigated": 0.3},
    "JUNGLE": {"damage_to_objectives": 0.7, "dragon_kills": 0.4, "vision_score": 0.3},
    "MIDDLE": {"damage_to_champions": 0.6, "cs_per_min": 0.3},
    "BOTTOM": {"damage_to_champions": 0.7, "cs_per_min": 0.4},
    "UTILITY": {
        "vision_score": 0.7,
        "heal_on_teammates": 0.3,
        "shield_on_teammates": 0.3,
        "cc_time": 0.3,
    },
}

ROBUST_CLIP: float = 3.0   # robust z-score clip 범위
PERF_Z_CLIP: float = 2.5   # 재표준화 후 perf_z clip 범위
BLOW_CLIP: float = 3.0     # blow_raw 표준화 후 tanh 입력 clip 범위


def position_metric_weights(position: str) -> dict[str, float]:
    """해당 포지션에 적용할 (공통 ∪ 라인전 ∪ 포지션특화) 지표→가중치 맵."""
    weights = dict(COMMON_WEIGHTS)
    weights.update(LANING_WEIGHTS)
    weights.update(ROLE_WEIGHTS.get(position, {}))
    return weights


def all_perf_metrics() -> list[str]:
    """v2 퍼포먼스 산정에 쓰이는 모든 지표 컬럼 목록(중복 제거)."""
    seen: dict[str, None] = {}
    for metric in (*COMMON_WEIGHTS, *LANING_WEIGHTS):
        seen.setdefault(metric, None)
    for role in ROLE_WEIGHTS.values():
        for metric in role:
            seen.setdefault(metric, None)
    return list(seen)


# =====================================================
# robust / 전역 표준화 헬퍼
# =====================================================

@dataclass(frozen=True)
class RobustParam:
    """robust z-score 기준값: center(중앙값)와 scale(IQR, 0이면 std/1.0 대체)."""

    center: float
    scale: float


def _derive_robust_param(values: pd.Series) -> RobustParam:
    """시리즈에서 robust 기준값(중앙값/IQR)을 만든다. IQR=0이면 std, 그것도 0이면 1.0."""
    clean = values.replace([np.inf, -np.inf], np.nan).dropna()
    if clean.empty:
        return RobustParam(center=0.0, scale=1.0)

    center = float(clean.median())
    iqr = float(clean.quantile(0.75) - clean.quantile(0.25))
    if iqr > 0:
        scale = iqr
    else:
        std = float(clean.std(ddof=0))
        scale = std if std > 0 else 1.0
    return RobustParam(center=center, scale=scale)


def _robust_z(values: pd.Series, param: RobustParam, clip: float = ROBUST_CLIP) -> pd.Series:
    z = (values - param.center) / param.scale
    return z.clip(-clip, clip)


@dataclass(frozen=True)
class StandardizeParam:
    """전역 표준화 기준값(mean/std)."""

    mean: float
    std: float


def _derive_standardize_param(values: pd.Series) -> StandardizeParam:
    clean = values.replace([np.inf, -np.inf], np.nan).dropna()
    if clean.empty:
        return StandardizeParam(mean=0.0, std=1.0)
    mean = float(clean.mean())
    std = float(clean.std(ddof=0))
    return StandardizeParam(mean=mean, std=std if std > 0 else 1.0)


def _standardize(values: pd.Series, param: StandardizeParam) -> pd.Series:
    return (values - param.mean) / param.std


# =====================================================
# 1) 퍼포먼스 점수 perf_z (산식 문서 §3-1)
# =====================================================

@dataclass(frozen=True)
class PerformanceBaseline:
    """perf_z 산정 기준값.

    robust_params: {(position, metric): RobustParam} — 포지션별·지표별 robust 기준
    raw_perf_stats: 전역 raw_perf 재표준화 기준(mean/std)
    """

    robust_params: dict[tuple[str, str], RobustParam]
    raw_perf_stats: StandardizeParam


def _compute_raw_perf(
    df: pd.DataFrame,
    robust_params: dict[tuple[str, str], RobustParam],
    position_col: str = "position",
) -> pd.Series:
    """저장된 robust 기준으로 row별 raw_perf(가중 robust_z 합)를 계산한다."""
    raw = pd.Series(0.0, index=df.index)
    for pos, group_idx in df.groupby(position_col).groups.items():
        idx = pd.Index(group_idx)
        weights = position_metric_weights(str(pos))
        pos_raw = pd.Series(0.0, index=idx)
        for metric, weight in weights.items():
            if metric not in df.columns:
                continue
            param = robust_params.get((str(pos), metric))
            if param is None:
                continue
            pos_raw = pos_raw + weight * _robust_z(df.loc[idx, metric], param)
        raw.loc[idx] = pos_raw
    return raw


def derive_performance_baseline(
    df: pd.DataFrame,
    position_col: str = "position",
) -> PerformanceBaseline:
    """이력 데이터에서 perf_z 산정 기준값을 학습한다."""
    robust_params: dict[tuple[str, str], RobustParam] = {}
    for pos, group in df.groupby(position_col):
        weights = position_metric_weights(str(pos))
        for metric in weights:
            if metric not in df.columns:
                continue
            robust_params[(str(pos), metric)] = _derive_robust_param(group[metric])

    raw_perf = _compute_raw_perf(df, robust_params, position_col=position_col)
    raw_perf_stats = _derive_standardize_param(raw_perf)
    return PerformanceBaseline(robust_params=robust_params, raw_perf_stats=raw_perf_stats)


def compute_perf_z(
    df: pd.DataFrame,
    baseline: PerformanceBaseline,
    position_col: str = "position",
) -> pd.Series:
    """저장된 baseline으로 row별 perf_z를 계산한다([−2.5, 2.5] clip)."""
    raw_perf = _compute_raw_perf(df, baseline.robust_params, position_col=position_col)
    perf_z = _standardize(raw_perf, baseline.raw_perf_stats).clip(-PERF_Z_CLIP, PERF_Z_CLIP)
    return perf_z.rename("perf_z")


# =====================================================
# 2) 승부격차 blow (산식 문서 §3-2)
# =====================================================

@dataclass(frozen=True)
class BlowoutBaseline:
    """blow 산정 기준값."""

    gold_diff: RobustParam
    duration: RobustParam
    blow_raw_stats: StandardizeParam


def _match_gold_diff_and_duration(
    df: pd.DataFrame,
    match_col: str = "custom_match_id",
    team_col: str = "game_team",
    gold_col: str = "gold_earned",
    duration_col: str = "game_duration",
) -> pd.DataFrame:
    """경기별 |팀 골드차|와 게임시간을 반환한다 (index=match_id)."""
    team_gold = df.groupby([match_col, team_col])[gold_col].sum()
    gold_diff = team_gold.groupby(level=0).agg(lambda s: abs(s.iloc[0] - s.iloc[-1]))
    duration = df.groupby(match_col)[duration_col].first()
    return pd.DataFrame({"gold_diff": gold_diff, "duration": duration})


def derive_blowout_baseline(
    df: pd.DataFrame,
    match_col: str = "custom_match_id",
    team_col: str = "game_team",
    gold_col: str = "gold_earned",
    duration_col: str = "game_duration",
) -> BlowoutBaseline:
    """이력 데이터에서 blow 산정 기준값을 학습한다."""
    match_df = _match_gold_diff_and_duration(
        df, match_col=match_col, team_col=team_col, gold_col=gold_col, duration_col=duration_col
    )
    gold_param = _derive_robust_param(match_df["gold_diff"])
    dur_param = _derive_robust_param(match_df["duration"])

    blow_raw = (
        _robust_z(match_df["gold_diff"], gold_param)
        - _robust_z(match_df["duration"], dur_param)
    )
    blow_raw_stats = _derive_standardize_param(blow_raw)
    return BlowoutBaseline(
        gold_diff=gold_param,
        duration=dur_param,
        blow_raw_stats=blow_raw_stats,
    )


def compute_blowout(
    df: pd.DataFrame,
    baseline: BlowoutBaseline,
    match_col: str = "custom_match_id",
    team_col: str = "game_team",
    gold_col: str = "gold_earned",
    duration_col: str = "game_duration",
) -> pd.Series:
    """저장된 baseline으로 경기별 blow를 계산해 각 row에 broadcast한다([−1, 1])."""
    match_df = _match_gold_diff_and_duration(
        df, match_col=match_col, team_col=team_col, gold_col=gold_col, duration_col=duration_col
    )
    blow_raw = (
        _robust_z(match_df["gold_diff"], baseline.gold_diff)
        - _robust_z(match_df["duration"], baseline.duration)
    )
    blow = np.tanh(
        _standardize(blow_raw, baseline.blow_raw_stats).clip(-BLOW_CLIP, BLOW_CLIP)
    )
    return df[match_col].map(blow).rename("blow")


# =====================================================
# 3) 통합 적용
# =====================================================

def apply_performance_features(
    df: pd.DataFrame,
    perf_baseline: PerformanceBaseline,
    blow_baseline: BlowoutBaseline,
) -> pd.DataFrame:
    """저장된 baseline으로 perf_z·blow 컬럼을 채운 복사본을 반환한다."""
    out = df.copy()
    out["perf_z"] = compute_perf_z(out, perf_baseline)
    out["blow"] = compute_blowout(out, blow_baseline)
    return out
