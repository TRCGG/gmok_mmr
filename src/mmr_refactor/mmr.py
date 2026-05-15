"""ELO 기반 포지션별 MMR 갱신 모듈.

원본 notebook의 MMR 계산 흐름을 함수 단위로 분리한 코드다.
기본 설정에서는 원본 산식을 유지하고, 필요할 때 MMRSettings로 계산 정책을 주입할 수 있다.

공개 함수:
    update_mmr_elo(df) -> (df_updated, summary_df_wide)
    make_summary_df_wide(df_updated) -> pivot 형태의 요약 DataFrame

내부 helper:
    expected_performance, calculate_personal_factor, calculate_k_factor
"""

from __future__ import annotations

from dataclasses import dataclass, field

import numpy as np
import pandas as pd

# ==============================================================
# 조정 가능한 MMR 기본 설정값
# ==============================================================

BASE_WIN: int = 20
BASE_LOSS: int = -15

ALPHA: float = 0.6   # 개인 기여도 반영
BETA: float = 0.4    # 상대 선수 대비 지표 반영
GAMMA: float = 0.2   # ELO 기대 성과 대비 실제 성과 반영

INITIAL_MMR: int = 1300
MMR_MIN_CHANGE: int = -25
MMR_MAX_CHANGE: int = 30

MMR_K_DECAY_START: int = 1500
MMR_K_DECAY_RATE: float = 0.002
MMR_K_MIN: float = 0.35

DEFAULT_POSITIONS: tuple[str, ...] = (
    "TOP", "BOTTOM", "MIDDLE", "JUNGLE", "UTILITY",
)


@dataclass(frozen=True)
class MMRSettings:
    """MMR 계산에 사용하는 조정 가능한 설정값."""

    base_win: int = BASE_WIN
    base_loss: int = BASE_LOSS
    alpha: float = ALPHA
    beta: float = BETA
    gamma: float = GAMMA
    initial_mmr: int = INITIAL_MMR
    min_change: int = MMR_MIN_CHANGE
    max_change: int = MMR_MAX_CHANGE
    k_decay_start: int = MMR_K_DECAY_START
    k_decay_rate: float = MMR_K_DECAY_RATE
    k_min: float = MMR_K_MIN
    positions: tuple[str, ...] = DEFAULT_POSITIONS


DEFAULT_MMR_SETTINGS = MMRSettings()


@dataclass(frozen=True)
class MMRBaselineStats:
    """MMR 변동 factor 계산에 사용하는 전체 기준 통계."""

    f1_mean: float
    f2_mean: float

    @classmethod
    def from_df(cls, df: pd.DataFrame) -> "MMRBaselineStats":
        return cls(
            f1_mean=float(df["game_n_person_contribution"].mean()),
            f2_mean=float(df["game_impact_vs_opponent"].mean()),
        )


@dataclass
class MMRRuntimeState:
    """경기 순회 중 유지되는 플레이어별 포지션 MMR과 전적 상태."""

    player_pos_mmr: dict[str, dict[str, int]] = field(default_factory=dict)
    player_pos_record: dict[str, dict[str, dict[str, int]]] = field(default_factory=dict)

    def ensure_player_position(
        self,
        pid: str,
        pos: str,
        settings: MMRSettings = DEFAULT_MMR_SETTINGS,
    ) -> None:
        self.player_pos_mmr.setdefault(pid, {})
        self.player_pos_record.setdefault(pid, {})
        self.player_pos_mmr[pid].setdefault(pos, settings.initial_mmr)
        self.player_pos_record[pid].setdefault(pos, {"win": 0, "total": 0})

    def get_pos_mmr(
        self,
        pid: str,
        pos: str,
        settings: MMRSettings = DEFAULT_MMR_SETTINGS,
    ) -> int:
        self.ensure_player_position(pid, pos, settings=settings)
        return int(self.player_pos_mmr[pid][pos])

    def apply_result(self, pid: str, pos: str, result: int, new_mmr: int) -> int:
        self.player_pos_mmr[pid][pos] = int(new_mmr)
        self.player_pos_record[pid][pos]["total"] += 1

        if result == 1:
            self.player_pos_record[pid][pos]["win"] += 1

        return self.calculate_total_mmr(pid)

    def calculate_total_mmr(self, pid: str) -> int:
        pos_mmr = self.player_pos_mmr[pid]
        pos_record = self.player_pos_record[pid]

        weighted_sum = 0
        total_games = 0
        for pos in pos_mmr:
            games = pos_record[pos]["total"]
            weighted_sum += pos_mmr[pos] * games
            total_games += games

        if total_games == 0:
            return DEFAULT_MMR_SETTINGS.initial_mmr
        return int(round(weighted_sum / total_games))

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
# 보조 함수
# ==============================================================

def expected_performance(mmr_a: float, mmr_b: float) -> float:
    """ELO 기반 기대 승률."""
    return 1 / (1 + 10 ** ((mmr_b - mmr_a) / 400))


def calculate_personal_factor(
    row: pd.Series,
    f1_mean: float,
    f2_mean: float,
    settings: MMRSettings = DEFAULT_MMR_SETTINGS,
) -> float:
    """개인 기여도 factor.

    - f1: game_n_person_contribution / 평균
    - f2: game_impact_vs_opponent / 평균 (NaN이면 1)
    각각 [0.5, 2]로 클램프한 뒤 (f1**ALPHA) * (f2**BETA)를 반환한다.
    """
    f1 = row["game_n_person_contribution"] / f1_mean if f1_mean != 0 else 1

    if pd.isna(row["game_impact_vs_opponent"]) or f2_mean == 0:
        f2 = 1
    else:
        f2 = row["game_impact_vs_opponent"] / f2_mean

    f1 = np.clip(f1, 0.5, 2)
    f2 = np.clip(f2, 0.5, 2)

    return (f1 ** settings.alpha) * (f2 ** settings.beta)


def calculate_k_factor(
    mmr: float,
    settings: MMRSettings = DEFAULT_MMR_SETTINGS,
) -> float:
    """MMR이 높을수록 점수 변동폭을 축소한다 (>= MMR_K_MIN)."""
    k = 1.0
    if mmr > settings.k_decay_start:
        k = 1.0 - ((mmr - settings.k_decay_start) * settings.k_decay_rate)
    return max(k, settings.k_min)


def validate_mmr_input_matches(
    df: pd.DataFrame,
    positions: tuple[str, ...] = DEFAULT_POSITIONS,
    expected_players_per_game: int = 10,
) -> None:
    """MMR 계산 전에 경기 구조를 검증한다.

    각 경기는 정확히 10개 row를 가져야 하며, 포지션별로 정확히 2개 row와
    승자 1명, 패자 1명을 가져야 한다.
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
# Wide 요약 생성
# ==============================================================

def make_summary_df_wide(
    mmr_df_updated: pd.DataFrame,
    positions: tuple[str, ...] = DEFAULT_POSITIONS,
) -> pd.DataFrame:
    """puuid별 total_mmr / 포지션별 mmr, games, winrate를 wide 형태로 정리한다."""
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
# 메인 MMR 갱신 로직: ELO + 개인 factor + 상대 factor
# ==============================================================

def _apply_mmr_game(
    game_df: pd.DataFrame,
    state: MMRRuntimeState,
    baseline: MMRBaselineStats,
    settings: MMRSettings = DEFAULT_MMR_SETTINGS,
) -> list[pd.Series]:
    """단일 경기 DataFrame을 현재 상태에 적용하고 갱신 row 목록을 반환한다."""
    pre_mmr: dict[tuple[str, str], int] = {}
    game_updates = []
    updated_rows: list[pd.Series] = []

    # 경기 시작 전 MMR snapshot
    for _, row in game_df.iterrows():
        pid = row["puuid"]
        pos = row["position"]
        pre_mmr[(pid, pos)] = state.get_pos_mmr(pid, pos, settings=settings)

    # 각 플레이어의 변동량 계산
    for _, row in game_df.iterrows():
        pid = row["puuid"]
        pos = row["position"]
        current_mmr = pre_mmr[(pid, pos)]

        opponent_df = game_df[
            (game_df["position"] == pos) & (game_df["puuid"] != pid)
        ]

        opponent_mmr = settings.initial_mmr
        if not opponent_df.empty:
            opp_id = opponent_df.iloc[0]["puuid"]
            opponent_mmr = pre_mmr.get((opp_id, pos), settings.initial_mmr)

        expected = expected_performance(current_mmr, opponent_mmr)

        actual = (
            row["game_impact_vs_opponent"] / 100
            if not pd.isna(row["game_impact_vs_opponent"])
            else expected
        )

        relative_factor = actual / expected if expected > 0 else 1
        personal_factor = calculate_personal_factor(
            row,
            baseline.f1_mean,
            baseline.f2_mean,
            settings=settings,
        )
        final_factor = personal_factor * (relative_factor ** settings.gamma)

        k = calculate_k_factor(current_mmr, settings=settings)

        if row["game_result"] == 1:
            delta = settings.base_win * final_factor * k
            delta = np.clip(max(delta, 12), 12, settings.max_change)
        else:
            delta = settings.base_loss * final_factor * k
            delta = np.clip(min(delta, -12), settings.min_change, -12)

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
        row_copy["total_mmr"] = state.apply_result(pid, pos, int(result), new_mmr)
        updated_rows.append(row_copy)

    return updated_rows


def update_mmr_matches(
    df: pd.DataFrame,
    state: MMRRuntimeState | None = None,
    baseline: MMRBaselineStats | None = None,
    settings: MMRSettings = DEFAULT_MMR_SETTINGS,
    validate: bool = True,
) -> pd.DataFrame:
    """여러 경기를 시간순으로 적용하고 row 단위 MMR 결과를 반환한다."""
    if validate:
        validate_mmr_input_matches(df, positions=settings.positions)

    df = df.sort_values(by=["played_at", "replay_code", "puuid"]).copy()
    state = state or MMRRuntimeState()
    baseline = baseline or MMRBaselineStats.from_df(df)

    updated_rows: list[pd.Series] = []
    for _, game_df in df.groupby("replay_code", sort=False):
        updated_rows.extend(
            _apply_mmr_game(
                game_df,
                state=state,
                baseline=baseline,
                settings=settings,
            )
        )

    return pd.DataFrame(updated_rows)


def update_single_match_mmr(
    match_df: pd.DataFrame,
    state: MMRRuntimeState,
    baseline: MMRBaselineStats,
    settings: MMRSettings = DEFAULT_MMR_SETTINGS,
) -> pd.DataFrame:
    """기존 상태에 단일 경기 하나를 적용하고 row 단위 MMR 결과를 반환한다."""
    validate_mmr_input_matches(match_df, positions=settings.positions)
    replay_codes = match_df["replay_code"].dropna().unique()
    if len(replay_codes) != 1:
        raise ValueError(
            "Single match MMR input must contain exactly one replay_code. "
            f"Got: {list(replay_codes)}"
        )

    match_df = match_df.sort_values(by=["played_at", "replay_code", "puuid"]).copy()
    return pd.DataFrame(
        _apply_mmr_game(
            match_df,
            state=state,
            baseline=baseline,
            settings=settings,
        )
    )


def update_mmr_elo(
    df: pd.DataFrame,
    settings: MMRSettings = DEFAULT_MMR_SETTINGS,
) -> tuple[pd.DataFrame, pd.DataFrame]:
    """게임 단위로 순회하며 (puuid x position) MMR을 갱신한다.

    NOTE: 입력 df에는 ``played_at``, ``replay_code``, ``puuid``, ``position``,
    ``game_result``, ``game_impact_vs_opponent``, ``game_n_person_contribution``
    컬럼이 필요하다.

    반환:
        (mmr_df_updated, summary_df_wide)
    """
    mmr_df_updated = update_mmr_matches(df, settings=settings)
    summary_df = make_summary_df_wide(mmr_df_updated, positions=settings.positions)

    return mmr_df_updated, summary_df
