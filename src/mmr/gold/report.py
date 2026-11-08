"""프론트 조회용 포지션 리포트 집계."""

from __future__ import annotations

from collections.abc import Callable

import numpy as np
import pandas as pd

REPORT_METRICS = (
    "game_impact", "game_n_person_contribution", "game_impact_vs_opponent",
    "damage_taken_per_min", "dpm", "gold_per_min", "damage_dealt_per_death",
    "damage_taken_per_death", "vision_score", "cc_time_per_min", "kda",
    "cs_per_min", "exp_per_min",
)
STYLE_METRICS = (
    "dpm", "damage_dealt_per_death", "cs_per_min", "gold_per_min",
    "exp_per_min", "kda", "game_n_person_contribution",
    "game_impact_vs_opponent",
)
StyleRule = tuple[str, Callable[[dict[str, float]], bool]]

BASE_STYLE_RULES: tuple[StyleRule, ...] = (
    ("불도저", lambda p: p["dpm"] >= 75 and p["damage_dealt_per_death"] <= 35),
    ("생존형 딜러", lambda p: p["dpm"] >= 75 and p["damage_dealt_per_death"] >= 75),
    ("성장형(파밍 중심)", lambda p: p["cs_per_min"] >= 75 and (p["gold_per_min"] >= 75 or p["exp_per_min"] >= 75)),
    ("팀파이트 캐리형", lambda p: p["kda"] >= 75 and p["game_impact_vs_opponent"] >= 75),
    ("밸런스형(올라운더)", lambda p: p["game_n_person_contribution"] >= 70 and p["game_impact_vs_opponent"] >= 60),
    ("운영형", lambda p: (p["cs_per_min"] >= 70 or p["gold_per_min"] >= 70) and p["kda"] <= 40),
)

POSITION_STYLE_RULES: dict[str, tuple[StyleRule, ...]] = {
    "TOP": (
        ("사이드 운영형 탑", lambda p: p["cs_per_min"] >= 70 and p["gold_per_min"] >= 65 and p["game_impact_vs_opponent"] >= 60),
        ("한타 개입형 탑", lambda p: p["dpm"] >= 65 and p["kda"] >= 65 and p["game_n_person_contribution"] >= 65),
    ),
    "JUG": (
        ("갱킹형 정글러", lambda p: p["kda"] >= 70 and p["game_n_person_contribution"] >= 70 and p["game_impact_vs_opponent"] >= 60),
        ("오브젝트/주도권형 정글러", lambda p: p["game_impact_vs_opponent"] >= 75 and p["game_n_person_contribution"] >= 65 and p["cs_per_min"] >= 55),
        ("파밍형 정글러", lambda p: p["cs_per_min"] >= 75 and p["gold_per_min"] >= 70 and p["exp_per_min"] >= 70),
    ),
    "MID": (
        ("로밍형 미드", lambda p: p["kda"] >= 70 and p["game_n_person_contribution"] >= 70 and p["cs_per_min"] <= 50),
        ("라인 캐리형 미드", lambda p: p["game_impact_vs_opponent"] >= 70 and p["dpm"] >= 70 and p["cs_per_min"] >= 55),
    ),
    "ADC": (
        ("하드 캐리형 원딜", lambda p: p["dpm"] >= 75 and p["gold_per_min"] >= 70 and p["damage_dealt_per_death"] >= 70),
        ("라인전 우위형 원딜", lambda p: p["game_impact_vs_opponent"] >= 70 and p["cs_per_min"] >= 65 and p["dpm"] >= 65),
    ),
    "SUP": (
        ("팀 기여형 서포터", lambda p: p["game_n_person_contribution"] >= 70 and p["kda"] >= 65 and p["game_impact_vs_opponent"] >= 60),
        ("교전 개시형 서포터", lambda p: p["game_n_person_contribution"] >= 70 and p["dpm"] >= 55 and p["kda"] >= 55),
    ),
}


def build_user_position_report(
    match_results: pd.DataFrame,
    *,
    min_style_games: int = 20,
    min_reference_users: int = 5,
) -> pd.DataFrame:
    """유저·포지션별 현재 지표와 스타일 분류 결과를 만든다."""
    _require_columns(match_results, {
        "guild_id", "position", "game_result", "played_at",
        "replay_code", "pos_cumulative_mmr",
    })
    work = match_results.copy()
    work["player_code"] = _account_series(work)
    for metric in REPORT_METRICS:
        if metric not in work:
            work[metric] = np.nan

    keys = ["guild_id", "player_code", "position"]
    aggregated = work.groupby(keys, as_index=False).agg(
        games=("game_result", "size"),
        wins=("game_result", "sum"),
        **{metric: (metric, "mean") for metric in REPORT_METRICS},
    )
    aggregated["winrate"] = aggregated["wins"] / aggregated["games"] * 100
    aggregated = aggregated.drop(columns="wins")
    last_mmr = (
        work.sort_values(["played_at", "replay_code"])
        .groupby(keys, as_index=False).tail(1)[keys + ["pos_cumulative_mmr"]]
        .rename(columns={"pos_cumulative_mmr": "mmr"})
    )
    report = aggregated.merge(last_mmr, on=keys, how="left", validate="one_to_one")
    report["base_style"] = "분류 준비 상태"
    report["position_style"] = "분류 준비 상태"
    report["comparison_basis"] = "같은 클랜·포지션 전체"
    report["reference_users"] = 0

    for _, indexes in report.groupby(["guild_id", "position"]).groups.items():
        group = report.loc[indexes]
        reference = group[group["games"] >= min_style_games]
        report.loc[indexes, "reference_users"] = len(reference)
        if len(reference) < min_reference_users:
            continue
        percentiles = {
            metric: group[metric].map(
                lambda value, population=pd.to_numeric(reference[metric], errors="coerce").dropna():
                _percentile(value, population)
            )
            for metric in STYLE_METRICS
        }
        for row_index in indexes:
            if report.at[row_index, "games"] < min_style_games:
                continue
            values = {metric: float(percentiles[metric].at[row_index]) for metric in STYLE_METRICS}
            if any(np.isnan(value) for value in values.values()):
                continue
            report.at[row_index, "base_style"] = _classify(values, BASE_STYLE_RULES, "밸런스형(기본)")
            report.at[row_index, "position_style"] = _classify(
                values,
                POSITION_STYLE_RULES.get(str(report.at[row_index, "position"]), ()),
                "분류 준비 상태",
            )

    ordered = [
        "guild_id", "player_code", "position", "mmr", "games", "winrate",
        *REPORT_METRICS, "base_style", "position_style", "comparison_basis",
        "reference_users",
    ]
    return report[ordered].sort_values(
        ["guild_id", "position", "mmr"], ascending=[True, True, False]
    ).reset_index(drop=True)


def filter_active_guild_members(
    position_summary: pd.DataFrame, guild_members: pd.DataFrame
) -> pd.DataFrame:
    """현재 길드원만 남기되 부캐는 본캐 MMR 귀속 계정으로 통합한다."""
    _require_columns(position_summary, {"guild_id", "player_code"})
    _require_columns(guild_members, {"guild_id", "account", "main_account", "status"})
    active = guild_members[guild_members["status"].astype(str).eq("1")].copy()
    active["player_code"] = active["main_account"].where(
        active["main_account"].notna(), active["account"]
    )
    active_keys = active[["guild_id", "player_code"]].drop_duplicates()
    return position_summary.merge(
        active_keys,
        on=["guild_id", "player_code"],
        how="inner",
        validate="many_to_one",
    )


def attach_position_report(
    user_summary: pd.DataFrame, position_summary: pd.DataFrame
) -> pd.DataFrame:
    """활성 유저 요약에 포지션별 리포트를 JSON 호환 객체로 합친다.

    ``position_summary``는 활성 길드원 필터가 적용된 결과여야 한다. 따라서
    inner join을 사용해 탈퇴 유저를 최종 요약 저장 대상에서도 제외한다.
    """
    keys = ["guild_id", "player_code"]
    _require_columns(user_summary, set(keys))
    _require_columns(position_summary, {*keys, "position"})

    payload_columns = [column for column in position_summary.columns if column not in keys]
    reports = []
    for key_values, group in position_summary.groupby(keys, sort=False):
        position_report = {}
        for row in group[payload_columns].to_dict(orient="records"):
            position = str(row.pop("position"))
            position_report[position] = {
                key: _json_value(value) for key, value in row.items()
            }
        reports.append({
            "guild_id": key_values[0],
            "player_code": key_values[1],
            "position_report": position_report,
        })

    report_frame = pd.DataFrame(reports, columns=[*keys, "position_report"])
    return user_summary.merge(
        report_frame,
        on=keys,
        how="inner",
        validate="one_to_one",
    )


def _account_series(frame: pd.DataFrame) -> pd.Series:
    column = "mmr_player_account" if "mmr_player_account" in frame else "player_code"
    if column not in frame:
        raise ValueError("MMR report input requires player_code or mmr_player_account.")
    if frame[column].isna().any():
        raise ValueError(f"MMR report input contains missing {column} values.")
    return frame[column].astype(str)


def _percentile(value: object, population: pd.Series) -> float:
    numeric = pd.to_numeric(pd.Series([value]), errors="coerce").iloc[0]
    if pd.isna(numeric) or population.empty:
        return float("nan")
    return float((population <= numeric).mean() * 100)


def _classify(percentiles: dict[str, float], rules: tuple[StyleRule, ...], default: str) -> str:
    for label, rule in rules:
        if rule(percentiles):
            return label
    return default


def _json_value(value: object) -> object:
    if pd.isna(value):
        return None
    if hasattr(value, "item"):
        return value.item()
    return value


def _require_columns(frame: pd.DataFrame, required: set[str]) -> None:
    missing = required - set(frame.columns)
    if missing:
        raise ValueError(f"MMR report input is missing columns: {sorted(missing)}")
