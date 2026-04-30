"""ELO 기반 포지션별 MMR 갱신 파이프라인 (순수 함수 모듈).

기존 `10_compute_mmr_elo_pipeline.py` 의 계산 로직을 그대로 옮긴다.
**계산 결과(수치)는 변경하지 않는다** — 동일 시드/동일 클램프/동일 iterrows 순서.

Public:
    update_mmr_elo(df)              → (df_updated, summary_df_wide)
    make_summary_df_wide(df_updated)→ pivot 형식 wide summary

Private helpers:
    expected_performance, calculate_personal_factor, calculate_k_factor
"""

from __future__ import annotations

import numpy as np
import pandas as pd

# ==============================================================
# Tunable parameters (기존 노트북 값 그대로)
# ==============================================================

BASE_WIN: int = 20
BASE_LOSS: int = -15

ALPHA: float = 0.6   # 개인 기여도 반영
BETA: float = 0.4    # 상대 포지션 비교 지표 반영
GAMMA: float = 0.2   # ELO 기대성과 대비 실제성과 반영

INITIAL_MMR: int = 1300
MMR_MIN_CHANGE: int = -25
MMR_MAX_CHANGE: int = 30

MMR_K_DECAY_START: int = 1500
MMR_K_DECAY_RATE: float = 0.002
MMR_K_MIN: float = 0.35

DEFAULT_POSITIONS: tuple[str, ...] = (
    "TOP", "BOTTOM", "MIDDLE", "JUNGLE", "UTILITY",
)

REQUIRED_MMR_COLUMNS: tuple[str, ...] = (
    "played_at",
    "replay_code",
    "puuid",
    "position",
    "game_result",
    "game_impact_vs_opponent",
    "game_n_person_contribution",
)


# ==============================================================
# Helpers
# ==============================================================

def expected_performance(mmr_a: float, mmr_b: float) -> float:
    """ELO 기대 승률."""
    return 1 / (1 + 10 ** ((mmr_b - mmr_a) / 400))


def calculate_personal_factor(row: pd.Series, f1_mean: float, f2_mean: float) -> float:
    """개인 기여도 factor.

    - f1: game_n_person_contribution / 평균
    - f2: game_impact_vs_opponent / 평균 (NaN 시 1)
    각각 [0.5, 2] 로 클램프 후 (f1**ALPHA) * (f2**BETA).
    """
    f1 = row["game_n_person_contribution"] / f1_mean if f1_mean != 0 else 1

    if pd.isna(row["game_impact_vs_opponent"]) or f2_mean == 0:
        f2 = 1
    else:
        f2 = row["game_impact_vs_opponent"] / f2_mean

    f1 = np.clip(f1, 0.5, 2)
    f2 = np.clip(f2, 0.5, 2)

    return (f1 ** ALPHA) * (f2 ** BETA)


def calculate_k_factor(mmr: float) -> float:
    """MMR 이 높을수록 점수 변동폭 축소 (>= MMR_K_MIN)."""
    k = 1.0
    if mmr > MMR_K_DECAY_START:
        k = 1.0 - ((mmr - MMR_K_DECAY_START) * MMR_K_DECAY_RATE)
    return max(k, MMR_K_MIN)


def validate_mmr_input_matches(
    df: pd.DataFrame,
    positions: tuple[str, ...] = DEFAULT_POSITIONS,
    expected_players_per_game: int = 10,
) -> None:
    """Validate match structure before MMR calculation.

    Each match must contain exactly ten rows, exactly two rows per position,
    and each position pair must contain one winner and one loser.
    """
    missing_cols = [c for c in REQUIRED_MMR_COLUMNS if c not in df.columns]
    if missing_cols:
        raise ValueError(f"MMR input is missing required columns: {missing_cols}")

    if df.empty:
        raise ValueError("MMR input is empty.")

    game_counts = df.groupby("replay_code").size()
    invalid_games = game_counts[game_counts != expected_players_per_game]
    if not invalid_games.empty:
        sample = invalid_games.head().to_dict()
        raise ValueError(
            "Invalid MMR input: each replay_code must contain "
            f"{expected_players_per_game} rows. Invalid sample: {sample}"
        )

    invalid_results = df[~df["game_result"].isin([0, 1])]
    if not invalid_results.empty:
        sample = invalid_results[["replay_code", "puuid", "game_result"]].head().to_dict("records")
        raise ValueError(f"Invalid MMR input: game_result must be 0 or 1. Invalid sample: {sample}")

    duplicated_players = df[df.duplicated(["replay_code", "puuid"], keep=False)]
    if not duplicated_players.empty:
        sample = duplicated_players[["replay_code", "puuid"]].head().to_dict("records")
        raise ValueError(f"Invalid MMR input: duplicated player rows in a match. Invalid sample: {sample}")

    expected_index = pd.MultiIndex.from_product(
        [df["replay_code"].dropna().unique(), positions],
        names=["replay_code", "position"],
    )

    position_counts = (
        df.groupby(["replay_code", "position"])
        .size()
        .reindex(expected_index, fill_value=0)
    )
    invalid_position_counts = position_counts[position_counts != 2]
    if not invalid_position_counts.empty:
        sample = invalid_position_counts.head().to_dict()
        raise ValueError(
            "Invalid MMR input: each replay_code/position pair must contain "
            f"exactly 2 rows. Invalid sample: {sample}"
        )

    position_result_sums = (
        df.groupby(["replay_code", "position"])["game_result"]
        .sum()
        .reindex(expected_index)
    )
    invalid_position_results = position_result_sums[position_result_sums != 1]
    if not invalid_position_results.empty:
        sample = invalid_position_results.head().to_dict()
        raise ValueError(
            "Invalid MMR input: each replay_code/position pair must contain "
            f"one winner and one loser. Invalid sample: {sample}"
        )


# ==============================================================
# Wide summary (per-player x per-position pivot)
# ==============================================================

def make_summary_df_wide(
    mmr_df_updated: pd.DataFrame,
    positions: tuple[str, ...] = DEFAULT_POSITIONS,
) -> pd.DataFrame:
    """puuid 별 total_mmr / 포지션별 mmr·games·winrate 를 wide 로 정리."""
    pos_last = (
        mmr_df_updated
        .sort_values(by=["played_at", "replay_code"])
        .groupby(["puuid", "position"], as_index=False)
        .tail(1)
        [["puuid", "position", "pos_cumulative_mmr"]]
        .rename(columns={"pos_cumulative_mmr": "pos_mmr"})
    )

    pos_stats = (
        mmr_df_updated
        .groupby(["puuid", "position"], as_index=False)
        .agg(
            pos_games=("game_result", "count"),
            pos_wins=("game_result", "sum"),
        )
    )
    pos_stats["pos_winrate"] = (pos_stats["pos_wins"] / pos_stats["pos_games"] * 100).round(2)

    pos_summary = pos_last.merge(pos_stats, on=["puuid", "position"], how="outer")

    mmr_wide = pos_summary.pivot(index="puuid", columns="position", values="pos_mmr")
    winrate_wide = pos_summary.pivot(index="puuid", columns="position", values="pos_winrate")
    games_wide = pos_summary.pivot(index="puuid", columns="position", values="pos_games")

    mmr_wide.columns = [f"{c}_mmr" for c in mmr_wide.columns]
    winrate_wide.columns = [f"{c}_winrate" for c in winrate_wide.columns]
    games_wide.columns = [f"{c}_games" for c in games_wide.columns]

    overall_summary = (
        mmr_df_updated
        .groupby("puuid", as_index=False)
        .agg(
            total_games=("game_result", "count"),
            total_wins=("game_result", "sum"),
        )
    )
    overall_summary["overall_winrate"] = (
        overall_summary["total_wins"] / overall_summary["total_games"] * 100
    ).round(2)

    total_mmr_df = (
        mmr_df_updated
        .sort_values(by=["played_at", "replay_code"])
        .groupby("puuid", as_index=False)
        .tail(1)
        [["puuid", "total_mmr"]]
    )

    overall_summary = overall_summary.merge(total_mmr_df, on="puuid", how="left").drop(columns="total_wins")

    summary_df = (
        overall_summary
        .merge(mmr_wide, on="puuid", how="left")
        .merge(winrate_wide, on="puuid", how="left")
        .merge(games_wide, on="puuid", how="left")
    )

    for pos in positions:
        if f"{pos}_mmr" not in summary_df.columns:
            summary_df[f"{pos}_mmr"] = np.nan
        if f"{pos}_winrate" not in summary_df.columns:
            summary_df[f"{pos}_winrate"] = np.nan
        if f"{pos}_games" not in summary_df.columns:
            summary_df[f"{pos}_games"] = 0

    ordered_cols = ["puuid", "total_mmr", "total_games", "overall_winrate"]
    for pos in positions:
        ordered_cols += [f"{pos}_mmr", f"{pos}_winrate", f"{pos}_games"]

    return (
        summary_df[ordered_cols]
        .sort_values(by="total_mmr", ascending=False)
        .reset_index(drop=True)
    )


# ==============================================================
# Main MMR update (ELO + personal factor + relative factor)
# ==============================================================

def update_mmr_elo(df: pd.DataFrame) -> tuple[pd.DataFrame, pd.DataFrame]:
    """게임 단위로 순회하며 (puuid x position) MMR 을 갱신한다.

    NOTE: 입력 df 는 ``played_at``, ``replay_code``, ``puuid``, ``position``,
    ``game_result``, ``game_impact_vs_opponent``, ``game_n_person_contribution``
    컬럼이 필요하다.

    Returns:
        (mmr_df_updated, summary_df_wide)
    """
    validate_mmr_input_matches(df)
    df = df.sort_values(by=["played_at", "replay_code", "puuid"]).copy()

    player_pos_mmr: dict[str, dict[str, int]] = {}
    player_pos_record: dict[str, dict[str, dict[str, int]]] = {}
    updated_rows: list[pd.Series] = []

    f1_mean = df["game_n_person_contribution"].mean()
    f2_mean = df["game_impact_vs_opponent"].mean()

    for _, game_df in df.groupby("replay_code", sort=False):
        pre_mmr: dict[tuple[str, str], int] = {}
        game_updates = []

        # 경기 시작 전 MMR snapshot
        for _, row in game_df.iterrows():
            pid = row["puuid"]
            pos = row["position"]

            player_pos_mmr.setdefault(pid, {})
            player_pos_record.setdefault(pid, {})

            player_pos_mmr[pid].setdefault(pos, INITIAL_MMR)
            player_pos_record[pid].setdefault(pos, {"win": 0, "total": 0})

            pre_mmr[(pid, pos)] = int(player_pos_mmr[pid][pos])

        # 각 플레이어 변화량 계산
        for _, row in game_df.iterrows():
            pid = row["puuid"]
            pos = row["position"]
            current_mmr = pre_mmr[(pid, pos)]

            opponent_df = game_df[
                (game_df["position"] == pos) & (game_df["puuid"] != pid)
            ]

            opponent_mmr = INITIAL_MMR
            if not opponent_df.empty:
                opp_id = opponent_df.iloc[0]["puuid"]
                opponent_mmr = pre_mmr.get((opp_id, pos), INITIAL_MMR)

            expected = expected_performance(current_mmr, opponent_mmr)

            actual = (
                row["game_impact_vs_opponent"] / 100
                if not pd.isna(row["game_impact_vs_opponent"])
                else expected
            )

            relative_factor = actual / expected if expected > 0 else 1
            personal_factor = calculate_personal_factor(row, f1_mean, f2_mean)
            final_factor = personal_factor * (relative_factor ** GAMMA)

            k = calculate_k_factor(current_mmr)

            if row["game_result"] == 1:
                delta = BASE_WIN * final_factor * k
                delta = np.clip(max(delta, 12), 12, MMR_MAX_CHANGE)
            else:
                delta = BASE_LOSS * final_factor * k
                delta = np.clip(min(delta, -12), MMR_MIN_CHANGE, -12)

            delta = int(round(delta))
            new_mmr = int(current_mmr + delta)

            row_copy = row.copy()
            row_copy["pre_game_pos_mmr"] = int(current_mmr)
            row_copy["expected_score"] = round(expected, 4)
            row_copy["actual_score"] = round(actual, 4)
            row_copy["relative_factor"] = round(relative_factor, 4)
            row_copy["personal_factor"] = round(personal_factor, 4)
            row_copy["final_factor"] = round(final_factor, 4)
            row_copy["mmr_change"] = int(delta)
            row_copy["pos_cumulative_mmr"] = int(new_mmr)

            game_updates.append((pid, pos, row["game_result"], new_mmr, row_copy))

        # 경기 결과 반영
        for pid, pos, result, new_mmr, row_copy in game_updates:
            player_pos_mmr[pid][pos] = new_mmr
            player_pos_record[pid][pos]["total"] += 1

            if result == 1:
                player_pos_record[pid][pos]["win"] += 1

            pos_mmr = player_pos_mmr[pid]
            pos_record = player_pos_record[pid]

            weighted_sum = 0
            total_games = 0
            for p in pos_mmr:
                g = pos_record[p]["total"]
                weighted_sum += pos_mmr[p] * g
                total_games += g

            total_mmr = int(round(weighted_sum / total_games)) if total_games > 0 else INITIAL_MMR

            row_copy["total_mmr"] = total_mmr
            updated_rows.append(row_copy)

    mmr_df_updated = pd.DataFrame(updated_rows)
    summary_df = make_summary_df_wide(mmr_df_updated)

    return mmr_df_updated, summary_df
