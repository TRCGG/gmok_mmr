"""Bronze → Silver 변환 (적격 필터 + 정합성 검사 + 기본 클렌징).

MMR 산식 v2의 silver 계층. 내부 표준 컬럼명은 ``mmr_participant_metric`` DDL을 따른다.
산식 문서 §3-0(데이터 정리)에 대응한다. 계정 통합(부계정→메인)은 백엔드가 저장
시점에 처리하므로 여기서는 다루지 않는다.
"""

from __future__ import annotations

import pandas as pd


# 결측 검사에서 제외할 (없을 수 있는) 컬럼
DEFAULT_NA_EXCLUDE_COLS: tuple[str, ...] = (
    "jungle_cs_own", "jungle_cs_enemy", "dragon_kills", "baron_kills",
    "herald_kills", "horde_kills", "damage_to_epic_monsters",
    "objectives_stolen", "barracks_killed",
)


def filter_eligible(df: pd.DataFrame) -> pd.DataFrame:
    """MMR 적격 경기만 남긴다: is_mmr_eligible == True AND is_deleted == False.

    해당 컬럼이 없으면(테스트/구버전 입력) 필터를 건너뛴다.
    """
    out = df
    if "is_mmr_eligible" in out.columns:
        out = out[out["is_mmr_eligible"].astype(bool)]
    if "is_deleted" in out.columns:
        out = out[~out["is_deleted"].astype(bool)]
    return out.copy()


def clean_match_data(
    df: pd.DataFrame,
    convert_duration_to_minutes: bool = True,
) -> pd.DataFrame:
    """매치 로그 적격 필터 + 기본 클렌징.

    적용 순서:
        1. 적격 필터(is_mmr_eligible / is_deleted)
        2. 중복 행 제거
        3. ``win`` 컬럼이 있으면 ``game_result`` (0/1) 로 변환 후 ``win`` 제거
        4. ``heal_on_teammates`` / ``shield_on_teammates`` 결측 → 0
        5. ``game_duration`` 단위를 초 → 분 으로 변환 (소수 둘째 자리 반올림)

    NOTE: ``game_duration`` 이 분 단위로 들어오면 ``convert_duration_to_minutes=False``.
    """
    out = filter_eligible(df).drop_duplicates().copy()

    # win → game_result
    if "win" in out.columns and "game_result" not in out.columns:
        out["game_result"] = (
            out["win"].astype(str).str.upper().map({"TRUE": 1, "FALSE": 0})
        )
        out = out.drop(columns=["win"])

    # 서포트 전용 지표 결측 → 0
    for col in ("heal_on_teammates", "shield_on_teammates"):
        if col in out.columns:
            out[col] = out[col].fillna(0)

    # game_duration 분 단위 변환
    if convert_duration_to_minutes and "game_duration" in out.columns:
        out["game_duration"] = (out["game_duration"] / 60).round(2)

    return out


def find_rows_with_na(
    df: pd.DataFrame,
    na_exclude_cols: tuple[str, ...] = DEFAULT_NA_EXCLUDE_COLS,
) -> pd.DataFrame:
    """결측 검사 대상 컬럼 중 어느 하나라도 NaN 인 row 반환 (분석/리포팅용)."""
    drop_cols = [c for c in na_exclude_cols if c in df.columns]
    check_df = df.drop(columns=drop_cols)
    return df[check_df.isnull().any(axis=1)]


def drop_invalid_matches(
    df: pd.DataFrame,
    positions: tuple[str, ...] = ("TOP", "JUNGLE", "MIDDLE", "BOTTOM", "UTILITY"),
    match_col: str = "custom_match_id",
    position_col: str = "position",
    result_col: str = "game_result",
    team_col: str = "game_team",
    expected_players: int = 10,
) -> pd.DataFrame:
    """5v5 구조가 맞지 않는 경기를 통째로 제거한다.

    제거 조건 (하나라도 해당하면 해당 custom_match_id 전체 drop):
        1. 경기 총 row 수가 expected_players(10)가 아님
        2. 포지션당 row 수가 정확히 2가 아님
        3. 포지션당 승자 1명 + 패자 1명 구조가 아님
        4. (game_team 존재 시) 팀이 정확히 2개·각 5명·팀 단위 승패 일치가 아님
           — 팀 평균 Elo 전제. validate_mmr_input_matches와 동일 구조 검사.
    """
    if df.empty:
        return df

    invalid_codes: set[str] = set()

    game_counts = df.groupby(match_col).size()
    invalid_codes.update(
        game_counts[game_counts != expected_players].index.tolist()
    )

    pos_counts = df.groupby([match_col, position_col]).size()
    invalid_codes.update(
        pos_counts[pos_counts != 2].reset_index()[match_col].tolist()
    )

    if result_col in df.columns:
        pos_result_sums = df.groupby([match_col, position_col])[result_col].sum()
        invalid_codes.update(
            pos_result_sums[pos_result_sums != 1].reset_index()[match_col].tolist()
        )

    if team_col in df.columns and result_col in df.columns:
        team_counts = df.groupby(match_col)[team_col].nunique()
        invalid_codes.update(team_counts[team_counts != 2].index.tolist())

        team_grp = df.groupby([match_col, team_col])[result_col]
        team_sizes = team_grp.size()
        invalid_codes.update(
            team_sizes[team_sizes != expected_players // 2].reset_index()[match_col].tolist()
        )
        team_uniform = team_grp.nunique()
        invalid_codes.update(
            team_uniform[team_uniform != 1].reset_index()[match_col].tolist()
        )

    if invalid_codes:
        print(
            f"[drop_invalid_matches] 유효하지 않은 경기 {len(invalid_codes)}건 제외: "
            + ", ".join(sorted(invalid_codes))
        )

    return df[~df[match_col].isin(invalid_codes)].copy()
