"""팀 평균 Elo 기반 MMR 갱신 모듈 (v2).

MMR 산식 문서(`docs/MMR_산식_문서.md`) §3-3·§3-4·§3-5를 구현한다.

핵심:
    - 경기를 ``played_date`` 순으로 한 판씩 처리한다.
    - 각 팀 5인의 현재 종합 MMR 평균으로 Elo 기대승률을 구한다.
    - K = K_BASE × 배치 × 퍼포먼스(perf_z) × 승부격차(blow) 보정.
    - Δ = K·(s − E) 를 종합 MMR과 해당 포지션 라인 MMR에 **동시** 누적한다.

공개 함수:
    update_mmr_elo(df) -> (df_updated, summary_df_wide)
    update_mmr_matches(df, ...) -> df_updated
    update_single_match_mmr(match_df, state, settings) -> df_updated
    make_summary_df_wide(df_updated) -> 요약 DataFrame
"""

from __future__ import annotations

from dataclasses import dataclass, field

import numpy as np
import pandas as pd

# ==============================================================
# 하이퍼파라미터 (산식 문서 §2)
# ==============================================================

INIT_MMR: int = 1500       # 신규 플레이어 시작 MMR
K_BASE: float = 32.0       # 기본 K-factor
SCALE: float = 400.0       # Elo 로지스틱 스케일
PERF_GAIN: float = 0.35    # 퍼포먼스 K 조정 최대비율 (±35%)
BLOWOUT_GAIN: float = 0.25 # 승부격차 K 조정 최대비율 (±25%)
PROV_GAMES: int = 10       # 배치(provisional) 경기 수
PROV_MULT: float = 1.5     # 배치 기간 K 배수
K_MIN: float = 4.0         # K 하한
CUT: int = 20              # 정식 랭킹 최소 경기수

DEFAULT_POSITIONS: tuple[str, ...] = (
    "TOP", "BOTTOM", "MIDDLE", "JUNGLE", "UTILITY",
)


@dataclass(frozen=True)
class MMRSettings:
    """MMR 계산에 사용하는 조정 가능한 설정값 (산식 문서 §5)."""

    init_mmr: int = INIT_MMR
    k_base: float = K_BASE
    scale: float = SCALE
    perf_gain: float = PERF_GAIN
    blowout_gain: float = BLOWOUT_GAIN
    prov_games: int = PROV_GAMES
    prov_mult: float = PROV_MULT
    k_min: float = K_MIN
    cut: int = CUT
    positions: tuple[str, ...] = DEFAULT_POSITIONS


DEFAULT_MMR_SETTINGS = MMRSettings()


@dataclass
class MMRRuntimeState:
    """경기 순회 중 유지되는 플레이어 상태.

    종합(total) MMR은 라인 MMR의 평균이 아니라 **독립 누적기**다.
    같은 Δ가 total과 해당 포지션 line에 동시 누적된다.
    """

    total_mmr: dict[str, int] = field(default_factory=dict)
    total_games: dict[str, int] = field(default_factory=dict)
    total_wins: dict[str, int] = field(default_factory=dict)
    line_mmr: dict[str, dict[str, int]] = field(default_factory=dict)
    line_games: dict[str, dict[str, int]] = field(default_factory=dict)
    line_wins: dict[str, dict[str, int]] = field(default_factory=dict)

    def ensure_player(self, pid: str, settings: MMRSettings = DEFAULT_MMR_SETTINGS) -> None:
        self.total_mmr.setdefault(pid, settings.init_mmr)
        self.total_games.setdefault(pid, 0)
        self.total_wins.setdefault(pid, 0)
        self.line_mmr.setdefault(pid, {})
        self.line_games.setdefault(pid, {})
        self.line_wins.setdefault(pid, {})

    def ensure_position(self, pid: str, pos: str, settings: MMRSettings = DEFAULT_MMR_SETTINGS) -> None:
        self.ensure_player(pid, settings=settings)
        self.line_mmr[pid].setdefault(pos, settings.init_mmr)
        self.line_games[pid].setdefault(pos, 0)
        self.line_wins[pid].setdefault(pos, 0)

    def get_total_mmr(self, pid: str, settings: MMRSettings = DEFAULT_MMR_SETTINGS) -> int:
        self.ensure_player(pid, settings=settings)
        return int(self.total_mmr[pid])

    def get_line_mmr(self, pid: str, pos: str, settings: MMRSettings = DEFAULT_MMR_SETTINGS) -> int:
        self.ensure_position(pid, pos, settings=settings)
        return int(self.line_mmr[pid][pos])

    def apply_result(
        self,
        pid: str,
        pos: str,
        result: int,
        new_total: int,
        new_line: int,
    ) -> None:
        self.total_mmr[pid] = int(new_total)
        self.line_mmr[pid][pos] = int(new_line)
        self.total_games[pid] += 1
        self.line_games[pid][pos] += 1
        if result == 1:
            self.total_wins[pid] += 1
            self.line_wins[pid][pos] += 1


REQUIRED_MMR_COLUMNS: tuple[str, ...] = (
    "played_date",
    "custom_match_id",
    "puuid",
    "position",
    "game_team",
    "game_result",
    "perf_z",
    "blow",
)


# ==============================================================
# 보조 함수
# ==============================================================

def expected_performance(mmr_a: float, mmr_b: float, scale: float = SCALE) -> float:
    """Elo 기반 기대 승률."""
    return 1 / (1 + 10 ** ((mmr_b - mmr_a) / scale))


def calculate_k_factor(
    perf_z: float,
    blow: float,
    total_games_before: int,
    win: bool,
    settings: MMRSettings = DEFAULT_MMR_SETTINGS,
) -> float:
    """K = K_BASE × 배치 × 퍼포먼스 × 승부격차 (산식 문서 §3-3 (3))."""
    k = settings.k_base

    # 배치 보정
    if total_games_before < settings.prov_games:
        k *= settings.prov_mult

    # 퍼포먼스 보정: 이긴 경기에 잘했으면 K↑, 진 경기에 잘했으면 K↓
    perf_adj = settings.perf_gain * np.tanh(perf_z if not pd.isna(perf_z) else 0.0)
    k *= (1 + perf_adj) if win else (1 - perf_adj)

    # 승부격차 보정: 압승이면 K↑, 접전이면 K↓
    blow_val = 0.0 if pd.isna(blow) else float(blow)
    k *= 1 + settings.blowout_gain * blow_val

    return max(k, settings.k_min)


def validate_mmr_input_matches(
    df: pd.DataFrame,
    positions: tuple[str, ...] = DEFAULT_POSITIONS,
    expected_players_per_game: int = 10,
) -> None:
    """MMR 계산 전에 경기 구조를 검증한다 (10행 / 포지션당 2행 / 승자1·패자1)."""
    missing_cols = [c for c in REQUIRED_MMR_COLUMNS if c not in df.columns]
    if missing_cols:
        raise ValueError(f"MMR input is missing required columns: {missing_cols}")

    if df.empty:
        raise ValueError("MMR input is empty.")

    game_counts = df.groupby("custom_match_id").size()
    invalid_games = game_counts[game_counts != expected_players_per_game]
    if not invalid_games.empty:
        sample = invalid_games.head().to_dict()
        raise ValueError(
            "Invalid MMR input: each custom_match_id must contain "
            f"{expected_players_per_game} rows. Invalid sample: {sample}"
        )

    invalid_results = df[~df["game_result"].isin([0, 1])]
    if not invalid_results.empty:
        sample = invalid_results[["custom_match_id", "puuid", "game_result"]].head().to_dict("records")
        raise ValueError(f"Invalid MMR input: game_result must be 0 or 1. Invalid sample: {sample}")

    duplicated_players = df[df.duplicated(["custom_match_id", "puuid"], keep=False)]
    if not duplicated_players.empty:
        sample = duplicated_players[["custom_match_id", "puuid"]].head().to_dict("records")
        raise ValueError(f"Invalid MMR input: duplicated player rows in a match. Invalid sample: {sample}")

    expected_index = pd.MultiIndex.from_product(
        [df["custom_match_id"].dropna().unique(), positions],
        names=["custom_match_id", "position"],
    )

    position_counts = (
        df.groupby(["custom_match_id", "position"])
        .size()
        .reindex(expected_index, fill_value=0)
    )
    invalid_position_counts = position_counts[position_counts != 2]
    if not invalid_position_counts.empty:
        sample = invalid_position_counts.head().to_dict()
        raise ValueError(
            "Invalid MMR input: each custom_match_id/position pair must contain "
            f"exactly 2 rows. Invalid sample: {sample}"
        )

    position_result_sums = (
        df.groupby(["custom_match_id", "position"])["game_result"]
        .sum()
        .reindex(expected_index)
    )
    invalid_position_results = position_result_sums[position_result_sums != 1]
    if not invalid_position_results.empty:
        sample = invalid_position_results.head().to_dict()
        raise ValueError(
            "Invalid MMR input: each custom_match_id/position pair must contain "
            f"one winner and one loser. Invalid sample: {sample}"
        )

    # 팀 평균 Elo 전제: 경기마다 정확히 2팀, 각 팀 5명, 팀 단위 승패 일치(전원 동일 결과)
    team_group = df.groupby(["custom_match_id", "game_team"])["game_result"]
    team_sizes = team_group.size()
    invalid_team_sizes = team_sizes[team_sizes != expected_players_per_game // 2]
    team_counts = df.groupby("custom_match_id")["game_team"].nunique()
    invalid_team_counts = team_counts[team_counts != 2]
    # 팀 내 game_result가 모두 같아야 한다(승팀 전원 1 / 패팀 전원 0)
    team_result_uniform = team_group.nunique()
    invalid_team_results = team_result_uniform[team_result_uniform != 1]
    if not invalid_team_counts.empty or not invalid_team_sizes.empty or not invalid_team_results.empty:
        raise ValueError(
            "Invalid MMR input: each custom_match_id must have exactly 2 teams of "
            f"{expected_players_per_game // 2}, each team with a uniform game_result. "
            f"Invalid sample: teams={invalid_team_counts.head().to_dict()}, "
            f"sizes={invalid_team_sizes.head().to_dict()}, "
            f"results={invalid_team_results.head().to_dict()}"
        )


# ==============================================================
# 메인 MMR 갱신 로직: 팀 평균 Elo
# ==============================================================

def _team_average_mmr(
    game_df: pd.DataFrame,
    pre_total: dict[str, int],
) -> dict[str, float]:
    """경기 시작 전 스냅샷으로 팀별 평균 종합 MMR을 계산한다."""
    team_mmr: dict[str, float] = {}
    for team, group in game_df.groupby("game_team"):
        mmrs = [pre_total[pid] for pid in group["puuid"]]
        team_mmr[str(team)] = float(np.mean(mmrs)) if mmrs else float(INIT_MMR)
    return team_mmr


def _apply_mmr_game(
    game_df: pd.DataFrame,
    state: MMRRuntimeState,
    settings: MMRSettings = DEFAULT_MMR_SETTINGS,
) -> list[pd.Series]:
    """단일 경기를 현재 상태에 적용하고 갱신 row 목록을 반환한다."""
    # 경기 시작 전 스냅샷
    pre_total: dict[str, int] = {}
    pre_line: dict[tuple[str, str], int] = {}
    pre_games: dict[str, int] = {}
    for _, row in game_df.iterrows():
        pid, pos = row["puuid"], row["position"]
        pre_total[pid] = state.get_total_mmr(pid, settings=settings)
        pre_line[(pid, pos)] = state.get_line_mmr(pid, pos, settings=settings)
        pre_games[pid] = int(state.total_games.get(pid, 0))

    team_mmr = _team_average_mmr(game_df, pre_total)
    teams = list(team_mmr)

    # 팀별 기대승률 (2팀 가정)
    expected_team: dict[str, float] = {}
    if len(teams) == 2:
        a, b = teams
        expected_team[a] = expected_performance(team_mmr[a], team_mmr[b], settings.scale)
        expected_team[b] = 1 - expected_team[a]
    else:
        for t in teams:
            expected_team[t] = 0.5

    updates = []
    for _, row in game_df.iterrows():
        pid, pos = row["puuid"], row["position"]
        team = str(row["game_team"])
        win = int(row["game_result"]) == 1
        s = 1.0 if win else 0.0
        expected = expected_team.get(team, 0.5)

        k = calculate_k_factor(
            perf_z=row["perf_z"],
            blow=row["blow"],
            total_games_before=pre_games[pid],
            win=win,
            settings=settings,
        )
        delta = k * (s - expected)

        cur_total = pre_total[pid]
        cur_line = pre_line[(pid, pos)]
        new_total = int(round(cur_total + delta))
        new_line = int(round(cur_line + delta))

        row_copy = row.copy()
        row_copy["pre_game_mmr"] = int(cur_total)
        row_copy["pre_game_pos_mmr"] = int(cur_line)
        row_copy["team_mmr"] = round(team_mmr.get(team, float(settings.init_mmr)), 2)
        row_copy["expected_score"] = round(expected, 4)
        row_copy["actual_score"] = s
        row_copy["k_factor"] = round(k, 4)
        row_copy["mmr_change"] = int(new_total - cur_total)
        row_copy["total_mmr"] = int(new_total)
        row_copy["pos_cumulative_mmr"] = int(new_line)

        updates.append((pid, pos, int(row["game_result"]), new_total, new_line, row_copy))

    updated_rows: list[pd.Series] = []
    for pid, pos, result, new_total, new_line, row_copy in updates:
        state.apply_result(pid, pos, result, new_total, new_line)
        updated_rows.append(row_copy)

    return updated_rows


def update_mmr_matches(
    df: pd.DataFrame,
    state: MMRRuntimeState | None = None,
    settings: MMRSettings = DEFAULT_MMR_SETTINGS,
    validate: bool = True,
) -> pd.DataFrame:
    """여러 경기를 시간순으로 적용하고 row 단위 MMR 결과를 반환한다."""
    if validate:
        validate_mmr_input_matches(df, positions=settings.positions)

    df = df.sort_values(by=["played_date", "custom_match_id", "puuid"]).copy()
    state = state or MMRRuntimeState()

    updated_rows: list[pd.Series] = []
    for _, game_df in df.groupby("custom_match_id", sort=False):
        updated_rows.extend(_apply_mmr_game(game_df, state=state, settings=settings))

    return pd.DataFrame(updated_rows)


def update_single_match_mmr(
    match_df: pd.DataFrame,
    state: MMRRuntimeState,
    settings: MMRSettings = DEFAULT_MMR_SETTINGS,
) -> pd.DataFrame:
    """기존 상태에 단일 경기 하나를 적용하고 row 단위 MMR 결과를 반환한다."""
    validate_mmr_input_matches(match_df, positions=settings.positions)
    match_ids = match_df["custom_match_id"].dropna().unique()
    if len(match_ids) != 1:
        raise ValueError(
            "Single match MMR input must contain exactly one custom_match_id. "
            f"Got: {list(match_ids)}"
        )

    match_df = match_df.sort_values(by=["played_date", "custom_match_id", "puuid"]).copy()
    return pd.DataFrame(_apply_mmr_game(match_df, state=state, settings=settings))


def update_mmr_elo(
    df: pd.DataFrame,
    settings: MMRSettings = DEFAULT_MMR_SETTINGS,
) -> tuple[pd.DataFrame, pd.DataFrame]:
    """전체 경기를 시간순 적용하고 (row 결과, 요약)을 반환한다."""
    mmr_df_updated = update_mmr_matches(df, settings=settings)
    summary_df = make_summary_df_wide(mmr_df_updated, settings=settings)
    return mmr_df_updated, summary_df


# ==============================================================
# Wide 요약 생성 (산식 문서 §3-4·§3-5)
# ==============================================================

def make_summary_df_wide(
    mmr_df_updated: pd.DataFrame,
    settings: MMRSettings = DEFAULT_MMR_SETTINGS,
) -> pd.DataFrame:
    """puuid별 종합 MMR / 포지션별 MMR·게임수·승률 + 정식/배치중 구분을 정리한다."""
    positions = settings.positions

    # 포지션별 최종 라인 MMR (가장 마지막 경기 기준)
    pos_last = (
        mmr_df_updated
        .sort_values(by=["played_date", "custom_match_id"])
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

    # 종합 MMR (가장 마지막 경기 기준)
    total_mmr_df = (
        mmr_df_updated
        .sort_values(by=["played_date", "custom_match_id"])
        .groupby("puuid", as_index=False)
        .tail(1)
        [["puuid", "total_mmr"]]
    )

    # 주 포지션 (게임수 최다)
    main_pos = (
        pos_stats.sort_values(["pos_games"], ascending=False)
        .groupby("puuid", as_index=False)
        .head(1)
        [["puuid", "position"]]
        .rename(columns={"position": "main_position"})
    )

    overall_summary = (
        overall_summary
        .merge(total_mmr_df, on="puuid", how="left")
        .merge(main_pos, on="puuid", how="left")
        .drop(columns="total_wins")
    )

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

    # 정식 / 배치중 구분 (20판 컷)
    summary_df["is_ranked"] = summary_df["total_games"] >= settings.cut

    ordered_cols = [
        "puuid", "total_mmr", "total_games", "overall_winrate",
        "main_position", "is_ranked",
    ]
    for pos in positions:
        ordered_cols += [f"{pos}_mmr", f"{pos}_winrate", f"{pos}_games"]

    return (
        summary_df[ordered_cols]
        .sort_values(by="total_mmr", ascending=False)
        .reset_index(drop=True)
    )
