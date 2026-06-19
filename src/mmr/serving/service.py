"""HTTP API layer에서 재사용할 MMR 계산 서비스 함수 (v2).

와이어 계약(interface_spec.md)의 필드/포지션 표기를 내부 표준(DDL 컬럼명,
포지션 `TOP/JUNGLE/MIDDLE/BOTTOM/UTILITY`)으로 변환하는 어댑터를 한곳에 모은다.
"""

from __future__ import annotations

from datetime import UTC, datetime
from typing import Any

import pandas as pd

from ..gold.baseline import (
    blowout_baseline_from_payload,
    calculate_service_baseline,
    performance_baseline_from_payload,
    service_baseline_to_payload,
)
from ..silver.cleaning import clean_match_data, drop_invalid_matches
from ..silver.features import add_basic_features
from ..silver.performance import (
    BlowoutBaseline,
    PerformanceBaseline,
    apply_performance_features,
    derive_blowout_baseline,
    derive_performance_baseline,
)
from ..gold.mmr import (
    DEFAULT_MMR_SETTINGS,
    MMRRuntimeState,
    make_summary_df_wide,
    update_mmr_matches,
    update_single_match_mmr,
)


# 와이어 → 내부(DDL) 컬럼명 매핑
WIRE_TO_DDL_COLUMNS: dict[str, str] = {
    "kill": "kills",
    "death": "deaths",
    "assist": "assists",
    "gold": "gold_earned",
    "ccing": "cc_time",
    "time_played": "game_duration",
    "total_damage_champions": "damage_to_champions",
    "total_damage_taken": "damage_taken",
    "total_damage_dealt_to_buildings": "damage_to_turrets",
}

# 와이어 ↔ 내부 포지션 enum 매핑
WIRE_TO_INTERNAL_POSITION: dict[str, str] = {
    "TOP": "TOP",
    "JUG": "JUNGLE",
    "MID": "MIDDLE",
    "ADC": "BOTTOM",
    "SUP": "UTILITY",
}
INTERNAL_TO_WIRE_POSITION: dict[str, str] = {
    v: k for k, v in WIRE_TO_INTERNAL_POSITION.items()
}


def calculate_baseline_payload(payload: dict[str, Any]) -> dict[str, Any]:
    """시즌 전체 클랜 경기 payload를 받아 baseline payload를 반환한다."""
    matches = payload.get("matches")
    if not isinstance(matches, list) or not matches:
        raise ValueError("Payload must include non-empty 'matches' list.")

    feature_df = build_base_feature_dataframe(pd.DataFrame(matches))
    baseline = calculate_service_baseline(
        feature_df,
        baseline_version=payload.get("baseline_version"),
        season=payload.get("season"),
    )
    return service_baseline_to_payload(
        baseline,
        match_count=feature_df["custom_match_id"].nunique(),
        player_game_row_count=len(feature_df),
    )


def calculate_full_mmr(payload: dict[str, Any]) -> dict[str, Any]:
    """클랜 전체 경기 payload를 받아 전체 MMR 결과를 반환한다.

    baseline이 payload에 있으면 사용하고, 없으면 입력 데이터에서 학습한다.
    """
    matches = payload.get("matches")
    if not isinstance(matches, list) or not matches:
        raise ValueError("Payload must include non-empty 'matches' list.")

    feature_df = build_base_feature_dataframe(pd.DataFrame(matches))

    perf_baseline, blow_baseline = _resolve_baselines(payload, feature_df)
    feature_df = apply_performance_features(feature_df, perf_baseline, blow_baseline)

    mmr_df_updated = update_mmr_matches(feature_df, settings=DEFAULT_MMR_SETTINGS)
    summary_df = make_summary_df_wide(mmr_df_updated)

    return {
        "calculation_id": payload.get("calculation_id"),
        "guild_id": payload.get("guild_id"),
        "season": payload.get("season"),
        "baseline_version": payload.get("baseline_version"),
        "match_results": _match_result_records(mmr_df_updated),
        "user_summary": _summary_records(summary_df),
        "metadata": {
            "match_count": int(feature_df["custom_match_id"].nunique()),
            "player_game_row_count": int(len(feature_df)),
            "calculated_at": datetime.now(UTC).isoformat(),
        },
    }


def calculate_single_match_mmr(payload: dict[str, Any]) -> dict[str, Any]:
    """단일 경기 payload를 받아 증분 MMR 결과를 반환한다."""
    match_rows = payload.get("match_rows")
    if not isinstance(match_rows, list) or not match_rows:
        raise ValueError("Payload must include non-empty 'match_rows' list.")

    perf_baseline = _require_performance_baseline(payload.get("performance_baseline"))
    blow_baseline = _require_blowout_baseline(payload.get("blowout_baseline"))
    state = _runtime_state_from_payload(payload.get("pre_match_user_summary", []))

    feature_df = build_base_feature_dataframe(pd.DataFrame(match_rows))
    feature_df = apply_performance_features(feature_df, perf_baseline, blow_baseline)

    result_df = update_single_match_mmr(
        feature_df,
        state=state,
        settings=DEFAULT_MMR_SETTINGS,
    )

    return {
        "guild_id": payload.get("guild_id"),
        "season": payload.get("season"),
        "calculation_id": payload.get("calculation_id"),
        "baseline_version": payload.get("baseline_version"),
        "custom_match_id": payload.get("custom_match_id") or _single_match_id(result_df),
        "match_results": _match_result_records(result_df),
        "updated_user_summary": _state_summary_records(state),
        "metadata": {
            "calculated_at": datetime.now(UTC).isoformat(),
            "mode": "incremental",
        },
    }


# ==============================================================
# feature build
# ==============================================================

def build_base_feature_dataframe(raw_df: pd.DataFrame) -> pd.DataFrame:
    """API raw match row를 기본 feature DataFrame으로 변환한다."""
    raw_df = _normalize_source_columns(raw_df)
    clean_df = clean_match_data(raw_df, convert_duration_to_minutes=True)
    clean_df = drop_invalid_matches(clean_df)
    if clean_df.empty:
        raise RuntimeError("유효한 경기가 없습니다. 모든 경기가 5v5 구조 검증에서 제외되었습니다.")
    return add_basic_features(clean_df)


def _resolve_baselines(
    payload: dict[str, Any],
    feature_df: pd.DataFrame,
) -> tuple[PerformanceBaseline, BlowoutBaseline]:
    perf_payload = payload.get("performance_baseline")
    blow_payload = payload.get("blowout_baseline")
    if perf_payload and blow_payload:
        return (
            performance_baseline_from_payload(perf_payload),
            blowout_baseline_from_payload(blow_payload),
        )
    return (
        derive_performance_baseline(feature_df),
        derive_blowout_baseline(feature_df),
    )


# ==============================================================
# 와이어 ↔ 내부 변환
# ==============================================================

def _normalize_source_columns(df: pd.DataFrame) -> pd.DataFrame:
    """와이어 필드명/포지션 enum을 내부 표준으로 변환한다 (멱등)."""
    out = df.copy()

    rename = {
        src: dst
        for src, dst in WIRE_TO_DDL_COLUMNS.items()
        if src in out.columns and dst not in out.columns
    }
    if rename:
        out = out.rename(columns=rename)

    if "game_result" not in out.columns and "win" in out.columns:
        out["game_result"] = out["win"].astype(str).str.upper().map({"TRUE": 1, "FALSE": 0})

    if "position" in out.columns:
        out["position"] = out["position"].map(
            lambda p: WIRE_TO_INTERNAL_POSITION.get(p, p)
        )

    return out


def _runtime_state_from_payload(rows: list[dict[str, Any]]) -> MMRRuntimeState:
    """pre_match_user_summary로 런타임 상태를 복원한다.

    v2 종합 MMR은 독립 누적기라, total_mmr/total_games/total_wins가 함께 필요하다.
    누락 시 신규(init_mmr, 0, 0)로 간주한다.
    """
    init = DEFAULT_MMR_SETTINGS.init_mmr
    state = MMRRuntimeState()
    for row in rows:
        pid = row["puuid"]
        state.ensure_player(pid)
        state.total_mmr[pid] = int(row.get("total_mmr", init))
        state.total_games[pid] = int(row.get("total_games", 0))
        state.total_wins[pid] = int(row.get("total_wins", 0))
        for pos_state in row.get("positions", []):
            pos = WIRE_TO_INTERNAL_POSITION.get(pos_state["position"], pos_state["position"])
            state.line_mmr[pid][pos] = int(pos_state.get("pos_mmr", init))
            state.line_games[pid][pos] = int(pos_state.get("pos_games", 0))
            state.line_wins[pid][pos] = int(pos_state.get("pos_wins", 0))
    return state


def _require_performance_baseline(payload: dict[str, Any] | None) -> PerformanceBaseline:
    if not payload:
        raise ValueError("MMR calculation requires 'performance_baseline'.")
    return performance_baseline_from_payload(payload)


def _require_blowout_baseline(payload: dict[str, Any] | None) -> BlowoutBaseline:
    if not payload:
        raise ValueError("MMR calculation requires 'blowout_baseline'.")
    return blowout_baseline_from_payload(payload)


def _state_summary_records(state: MMRRuntimeState) -> list[dict[str, Any]]:
    rows = []
    for pid in state.total_mmr:
        rows.append(
            {
                "puuid": pid,
                "total_mmr": int(state.total_mmr[pid]),
                "total_games": int(state.total_games.get(pid, 0)),
                "total_wins": int(state.total_wins.get(pid, 0)),
                "positions": [
                    {
                        "position": INTERNAL_TO_WIRE_POSITION.get(pos, pos),
                        "pos_mmr": int(mmr),
                        "pos_games": int(state.line_games[pid].get(pos, 0)),
                        "pos_wins": int(state.line_wins[pid].get(pos, 0)),
                    }
                    for pos, mmr in state.line_mmr[pid].items()
                ],
            }
        )
    return rows


# 응답에 노출할 match_results 컬럼
_MATCH_RESULT_COLUMNS: tuple[str, ...] = (
    "custom_match_id", "match_participant_id", "puuid", "position", "game_team",
    "game_result", "perf_z", "blow", "pre_game_mmr", "pre_game_pos_mmr",
    "team_mmr", "expected_score", "actual_score", "k_factor", "mmr_change",
    "total_mmr", "pos_cumulative_mmr",
)


def _match_result_records(df: pd.DataFrame) -> list[dict[str, Any]]:
    out = df.copy()
    if "position" in out.columns:
        out["position"] = out["position"].map(
            lambda p: INTERNAL_TO_WIRE_POSITION.get(p, p)
        )
    cols = [c for c in _MATCH_RESULT_COLUMNS if c in out.columns]
    return _json_records(out[cols])


def _summary_records(df: pd.DataFrame) -> list[dict[str, Any]]:
    out = df.copy()
    if "main_position" in out.columns:
        out["main_position"] = out["main_position"].map(
            lambda p: INTERNAL_TO_WIRE_POSITION.get(p, p) if isinstance(p, str) else p
        )
    return _json_records(out)


def _single_match_id(df: pd.DataFrame) -> str | None:
    ids = df["custom_match_id"].dropna().unique()
    if len(ids) == 1:
        return str(ids[0])
    return None


def _json_records(df: pd.DataFrame) -> list[dict[str, Any]]:
    out = df.copy()
    out = out.replace({pd.NA: None})
    return out.where(pd.notnull(out), None).to_dict(orient="records")
