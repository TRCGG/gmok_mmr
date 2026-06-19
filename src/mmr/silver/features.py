"""MMR 파이프라인 파생 feature 모듈 (v2, DDL 컬럼명 기준).

내부 표준 컬럼명은 ``mmr_participant_metric`` DDL을 따른다
(``custom_match_id``, ``gold_earned``, ``game_duration`` 등).

DDL 테이블은 ``gold_per_min``/``kda``/``lane_gold_diff`` 같은 파생 지표를 이미
보유하므로, 이미 존재하는 컬럼은 덮어쓰지 않고 **누락된 것만** 원시 지표에서 파생한다.
``game_duration`` 은 cleaning 단계에서 분(minute) 단위로 변환되었다고 가정한다.
"""

from __future__ import annotations

import numpy as np
import pandas as pd


# v2 퍼포먼스/승부격차 산정에 쓰이는, 파생이 필요할 수 있는 지표 목록
DERIVED_METRICS: tuple[str, ...] = (
    "gold_per_min",
    "dpm",
    "damage_taken_per_min",
    "cc_time_per_min",
    "exp_per_min",
    "damage_to_turrets_per_min",
    "cs_per_min",
    "wards_placed_per_min",
    "wards_killed_per_min",
    "kda",
    "damage_taken_per_death",
    "damage_dealt_per_death",
    "dead_time_pct",
    "lane_gold_diff",
)


def add_basic_features(df: pd.DataFrame) -> pd.DataFrame:
    """누락된 파생 feature를 DDL 컬럼명 기준으로 생성한다 (이미 있으면 보존)."""
    out = df.copy()
    duration = out["game_duration"].replace(0, np.nan)  # 분 단위 (cleaning 후)
    deaths_safe = out["deaths"].replace(0, 1) if "deaths" in out.columns else None

    def _ensure(col: str, series: pd.Series) -> None:
        if col not in out.columns:
            out[col] = series

    if "gold_earned" in out.columns:
        _ensure("gold_per_min", out["gold_earned"] / duration)
    if "damage_to_champions" in out.columns:
        _ensure("dpm", out["damage_to_champions"] / duration)
    if "damage_taken" in out.columns:
        _ensure("damage_taken_per_min", out["damage_taken"] / duration)
    if "cc_time" in out.columns:
        _ensure("cc_time_per_min", out["cc_time"] / duration)
    if "exp" in out.columns:
        _ensure("exp_per_min", out["exp"] / duration)
    if "damage_to_turrets" in out.columns:
        _ensure("damage_to_turrets_per_min", out["damage_to_turrets"] / duration)
    if {"minions_killed", "neutral_minions_killed"}.issubset(out.columns):
        _ensure(
            "cs_per_min",
            (out["minions_killed"] + out["neutral_minions_killed"]) / duration,
        )
    if "wards_placed" in out.columns:
        _ensure("wards_placed_per_min", out["wards_placed"] / duration)
    if "wards_killed" in out.columns:
        _ensure("wards_killed_per_min", out["wards_killed"] / duration)

    if deaths_safe is not None:
        if {"kills", "assists"}.issubset(out.columns):
            _ensure("kda", (out["kills"] + out["assists"]) / deaths_safe)
        if "damage_taken" in out.columns:
            _ensure("damage_taken_per_death", out["damage_taken"] / deaths_safe)
        if "damage_to_champions" in out.columns:
            _ensure("damage_dealt_per_death", out["damage_to_champions"] / deaths_safe)

    if "time_spent_dead" in out.columns:
        _ensure("dead_time_pct", out["time_spent_dead"] / (duration * 60) * 100)

    if "lane_gold_diff" not in out.columns and {
        "custom_match_id",
        "position",
        "puuid",
        "gold_earned",
    }.issubset(out.columns):
        out["lane_gold_diff"] = _compute_lane_gold_diff(out)

    out = out.replace([np.inf, -np.inf], np.nan)
    numeric_cols = out.select_dtypes(include="number").columns
    out[numeric_cols] = out[numeric_cols].fillna(0)
    return out


def _compute_lane_gold_diff(df: pd.DataFrame) -> pd.Series:
    """같은 경기, 같은 포지션 상대와의 gold_earned 차이를 반환한다."""
    grp = df.groupby(["custom_match_id", "position"])["gold_earned"]
    opponent_gold_sum = grp.transform("sum") - df["gold_earned"]
    opponent_count = grp.transform("count") - 1
    opponent_gold = opponent_gold_sum / opponent_count.replace(0, np.nan)
    return df["gold_earned"] - opponent_gold
