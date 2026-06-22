"""HTTP API layer에서 재사용할 MMR 계산 서비스 함수."""

from __future__ import annotations

from datetime import UTC, datetime
from typing import Any

import pandas as pd

from ..gold.baseline import (
    calculate_service_baseline,
    game_impact_baseline_from_payload,
    service_baseline_to_payload,
)
from ..silver.features import BASE_METRICS, add_basic_features, select_available_metrics
from ..silver.game_impact import (
    apply_game_impact_baseline,
    compute_n_person_contribution,
    compute_raw_game_impact,
    compute_vs_opponent,
    normalize_by_position_outcome,
    normalize_minmax_0_100,
    resolve_position_weights,
)
from ..gold.mmr import (
    DEFAULT_MMR_SETTINGS,
    MMRBaselineStats,
    MMRRuntimeState,
    make_summary_df_wide,
    update_mmr_matches,
    update_single_match_mmr,
)
from ..silver.cleaning import clean_match_data, drop_invalid_matches


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
        match_count=feature_df["replay_code"].nunique(),
        player_game_row_count=len(feature_df),
    )


def calculate_full_mmr(payload: dict[str, Any]) -> dict[str, Any]:
    """클랜 전체 경기 payload를 받아 전체 MMR 결과를 반환한다."""
    matches = payload.get("matches")
    if not isinstance(matches, list) or not matches:
        raise ValueError("Payload must include non-empty 'matches' list.")

    mmr_baseline = _baseline_from_payload(payload.get("mmr_baseline"))
    game_impact_baseline = _game_impact_baseline_from_payload(
        payload.get("game_impact_baseline")
    )
    feature_df = build_feature_dataframe(
        pd.DataFrame(matches),
        baseline=game_impact_baseline,
    )
    mmr_df_updated = update_mmr_matches(
        feature_df,
        baseline=mmr_baseline,
        settings=DEFAULT_MMR_SETTINGS,
    )
    summary_df = make_summary_df_wide(mmr_df_updated)

    return {
        "calculation_id": payload.get("calculation_id"),
        "guild_id": payload.get("guild_id"),
        "season": payload.get("season"),
        "baseline_version": payload.get("baseline_version"),
        "match_results": _json_records(mmr_df_updated),
        "user_summary": _json_records(summary_df),
        "metadata": {
            "match_count": int(feature_df["replay_code"].nunique()),
            "player_game_row_count": int(len(feature_df)),
            "calculated_at": datetime.now(UTC).isoformat(),
        },
    }


def calculate_single_match_mmr(payload: dict[str, Any]) -> dict[str, Any]:
    """단일 경기 payload를 받아 해당 경기 MMR 결과를 반환한다.

    현재 운영 전 단계에서는 `matches` + `target_replay_code`가 있으면 전체 재계산
    기반으로 처리한다. `match_rows` 기반 증분 계산은 이미 MMR feature가 계산된
    row와 current state, baseline stats가 전달되는 경우만 지원한다.
    """
    match_rows = payload.get("match_rows")
    if not isinstance(match_rows, list) or not match_rows:
        raise ValueError("Payload must include non-empty 'match_rows' list.")

    state = _runtime_state_from_payload(payload.get("current_user_state", []))
    mmr_baseline = _baseline_from_payload(payload.get("baseline_stats"))
    game_impact_baseline = _game_impact_baseline_from_payload(
        payload.get("game_impact_baseline")
    )
    match_df = pd.DataFrame(match_rows)
    match_df = _normalize_source_columns(match_df)
    match_df = build_incremental_feature_dataframe(match_df, game_impact_baseline)

    result_df = update_single_match_mmr(
        match_df,
        state=state,
        baseline=mmr_baseline,
        settings=DEFAULT_MMR_SETTINGS,
    )

    return {
        "guild_id": payload.get("guild_id"),
        "season": payload.get("season"),
        "baseline_version": payload.get("baseline_version"),
        "replay_code": payload.get("replay_code") or _single_replay_code(result_df),
        "match_results": _json_records(result_df),
        "updated_user_summary": _state_summary_records(state),
        "metadata": {
            "calculated_at": datetime.now(UTC).isoformat(),
            "mode": "incremental",
        },
    }


def build_base_feature_dataframe(raw_df: pd.DataFrame) -> pd.DataFrame:
    """API raw match row를 기본 feature DataFrame으로 변환한다."""
    raw_df = _normalize_source_columns(raw_df)
    clean_df = clean_match_data(raw_df, convert_duration_to_minutes=True)
    clean_df = drop_invalid_matches(clean_df)
    if clean_df.empty:
        raise RuntimeError("유효한 경기가 없습니다. 모든 경기가 5v5 구조 검증에서 제외되었습니다.")
    return add_basic_features(clean_df)


def build_feature_dataframe(
    raw_df: pd.DataFrame,
    baseline=None,
) -> pd.DataFrame:
    """API raw match row를 MMR 계산 입력 DataFrame으로 변환한다."""
    feature_df = build_base_feature_dataframe(raw_df)

    if baseline is not None:
        return apply_game_impact_baseline(feature_df, baseline)

    metrics = select_available_metrics(feature_df, BASE_METRICS)
    if not metrics:
        raise RuntimeError("No usable metric columns were found for Game Impact calculation.")

    position_weights = resolve_position_weights(feature_df, metrics=metrics)
    feature_df["raw_game_impact"] = compute_raw_game_impact(feature_df, position_weights)
    feature_df["game_impact"] = normalize_minmax_0_100(feature_df["raw_game_impact"])
    feature_df["game_impact_winloss_norm"] = normalize_by_position_outcome(feature_df)
    feature_df["game_n_person_contribution"] = compute_n_person_contribution(feature_df)
    feature_df["game_impact_vs_opponent"] = compute_vs_opponent(feature_df)
    return feature_df


def build_incremental_feature_dataframe(
    raw_df: pd.DataFrame,
    baseline,
) -> pd.DataFrame:
    """단일 경기 raw row에 저장된 Game Impact baseline을 적용한다."""
    feature_df = build_base_feature_dataframe(raw_df)
    return apply_game_impact_baseline(feature_df, baseline)


def _normalize_source_columns(df: pd.DataFrame) -> pd.DataFrame:
    out = df.copy()
    if "gold" not in out.columns and "gold_earned" in out.columns:
        out = out.rename(columns={"gold_earned": "gold"})
    if "game_result" not in out.columns and "win" in out.columns:
        out["game_result"] = out["win"].astype(str).str.upper().map({"TRUE": 1, "FALSE": 0})
    return out


def _runtime_state_from_payload(rows: list[dict[str, Any]]) -> MMRRuntimeState:
    state = MMRRuntimeState()
    for row in rows:
        pid = row["puuid"]
        pos = row["position"]
        state.player_pos_mmr.setdefault(pid, {})[pos] = int(row.get("pos_mmr", 1300))
        state.player_pos_record.setdefault(pid, {})[pos] = {
            "win": int(row.get("pos_wins", 0)),
            "total": int(row.get("pos_games", 0)),
        }
    return state


def _baseline_from_payload(payload: dict[str, Any] | None) -> MMRBaselineStats:
    if not payload:
        raise ValueError("Incremental single-match calculation requires 'baseline_stats'.")
    return MMRBaselineStats(
        f1_mean=float(payload["f1_mean"]),
        f2_mean=float(payload["f2_mean"]),
        f1_position_mean={
            str(position): float(value)
            for position, value in payload.get("f1_position_mean", {}).items()
        },
        f2_position_mean={
            str(position): float(value)
            for position, value in payload.get("f2_position_mean", {}).items()
        },
    )


def _game_impact_baseline_from_payload(
    payload: dict[str, Any] | None,
) -> Any:
    if not payload:
        raise ValueError("MMR calculation requires 'game_impact_baseline'.")
    return game_impact_baseline_from_payload(payload)


def _state_summary_records(state: MMRRuntimeState) -> list[dict[str, Any]]:
    rows = []
    for pid, pos_mmr in state.player_pos_mmr.items():
        rows.append(
            {
                "puuid": pid,
                "total_mmr": state.calculate_total_mmr(pid),
                "positions": [
                    {
                        "position": pos,
                        "pos_mmr": mmr,
                        "pos_games": state.player_pos_record[pid][pos]["total"],
                        "pos_wins": state.player_pos_record[pid][pos]["win"],
                    }
                    for pos, mmr in pos_mmr.items()
                ],
            }
        )
    return rows


def _single_replay_code(df: pd.DataFrame) -> str | None:
    replay_codes = df["replay_code"].dropna().unique()
    if len(replay_codes) == 1:
        return str(replay_codes[0])
    return None


def _json_records(df: pd.DataFrame) -> list[dict[str, Any]]:
    out = df.copy()
    out = out.replace({pd.NA: None})
    return out.where(pd.notnull(out), None).to_dict(orient="records")
