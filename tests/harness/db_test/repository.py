"""DB 테스트용 원천 경기 데이터 repository.

SQL 문과 DB read/write 책임을 관리한다.
백엔드 API 완성 후 db_test 패키지 전체와 함께 삭제한다.
"""

from __future__ import annotations

import pandas as pd
from sqlalchemy import create_engine, inspect, text
from sqlalchemy.dialects.postgresql import JSONB

from .config import (
    get_db_url,
    get_guild_member_table,
    get_mmr_match_result_table,
    get_mmr_summary_table,
    get_player_game_table,
    get_player_table,
)

# dict 값을 담는 결과 컬럼. dtype을 지정하지 않으면 psycopg2가 dict를 바인딩하지 못한다.
JSONB_RESULT_COLUMNS = ("position_report",)


def load_match_dataframe_from_db(guild_id: str | None = None) -> pd.DataFrame:
    """PostgreSQL에서 원천 player-game 레코드를 읽는다.

    Args:
        guild_id: 지정 시 해당 guild의 경기만 읽는다. None이면 전체.

    NOTE: ``is_deleted = false`` 와 ``is_mmr_eligible = true`` 행만 읽는다.
    시즌은 계산 시점 값이 아니라 경기의 ``custom_match.season``을 읽는다.

    MMR 식별자는 player_code이며 길드별로 계산한다. player_game의
    player_code가 없으면 riot_account에서 보강한다. 원본 puuid는 계정
    정보로만 전달하며 MMR 식별자 대신 사용하지 않는다.
    """
    engine = create_engine(get_db_url())
    player_game_table = get_player_game_table()
    conditions = ["pg.is_deleted = false", "pg.is_mmr_eligible = true"]
    if guild_id is not None:
        conditions.append("pg.guild_id = :guild_id")
    where_clause = "WHERE " + " AND ".join(conditions)

    query = text(
        f"""
        SELECT
            pg.id                                           AS player_game_id,
            pg.custom_match_id                              AS replay_code,
            COALESCE(pg.player_code, ra.player_code)          AS player_code,
            pg.puuid                                       AS puuid,
            pg.guild_id                                     AS guild_id,
            pg.champion_id                                 AS champion_id,
            pg.game_team                                   AS team,
            pg.position                                    AS position,
            pg.game_result                                 AS game_result,
            pg.kills                                       AS kills,
            pg.deaths                                      AS deaths,
            pg.assists                                     AS assists,
            pg.double_kills                                 AS double_kills,
            pg.triple_kills                                 AS triple_kills,
            pg.quadra_kills                                 AS quadra_kills,
            pg.penta_kills                                  AS penta_kills,
            pg.killing_sprees                               AS killing_sprees,
            pg.largest_killing_spree                        AS largest_killing_spree,
            pg.gold_earned                                 AS gold,
            pg.cc_time                                     AS cc_time,
            pg.game_duration                               AS game_duration,
            pg.damage_to_champions                         AS damage_to_champions,
            pg.damage_taken                                AS damage_taken,
            pg.damage_self_mitigated                        AS damage_self_mitigated,
            pg.vision_score                                AS vision_score,
            pg.wards_placed                                AS wards_placed,
            pg.wards_killed                                AS wards_killed,
            pg.detector_wards_placed                        AS detector_wards_placed,
            pg.control_wards_bought                        AS vision_bought,
            pg.minions_killed                              AS minions_killed,
            pg.neutral_minions_killed                       AS neutral_minions_killed,
            pg.time_spent_dead                              AS time_spent_dead,
            pg.longest_time_living                          AS longest_time_living,
            pg.damage_to_turrets                            AS damage_to_turrets,
            pg.damage_to_objectives                         AS damage_to_objectives,
            pg.dragon_kills                                 AS dragon_kills,
            pg.baron_kills                                  AS baron_kills,
            pg.herald_kills                                 AS herald_kills,
            pg.horde_kills                                  AS horde_kills,
            pg.last_takedown_time                           AS last_takedown_time,
            pg.turrets_killed                               AS turrets_killed,
            pg.turret_takedowns                             AS turret_takedowns,
            pg.level                                       AS level,
            pg.exp                                         AS exp,
            pg.turret_plates_destroyed                      AS turret_plates_destroyed,
            pg.takedowns_under_turret                       AS takedowns_under_turret,
            pg.takedowns_before_15min                       AS takedowns_before_15min,
            pg.jungle_cs_own                                AS jungle_cs_own,
            pg.jungle_cs_enemy                              AS jungle_cs_enemy,
            pg.damage_to_epic_monsters                      AS damage_to_epic_monsters,
            pg.objectives_stolen                            AS objectives_stolen,
            pg.barracks_killed                              AS barracks_killed,
            pg.heal_on_teammates                           AS heal_on_teammates,
            pg.shield_on_teammates                         AS shield_on_teammates,
            pg.enemy_missing_pings                          AS enemy_missing_pings,
            pg.retreat_pings                                AS retreat_pings,
            pg.on_my_way_pings                              AS on_my_way_pings,
            pg.command_pings                                AS command_pings,
            pg.create_date                                  AS created_at,
            pg.played_date                                 AS played_at,
            cm.season                                      AS season
        FROM {player_game_table} pg
        LEFT JOIN riot_account ra ON ra.puuid = pg.puuid
        LEFT JOIN custom_match cm ON cm.id = pg.custom_match_id
        {where_clause}
        """
    )

    params = {"guild_id": guild_id} if guild_id is not None else {}
    with engine.connect() as conn:
        return pd.read_sql(query, conn, params=params)


def load_user_name_dataframe_from_db() -> pd.DataFrame:
    """PostgreSQL에서 ``puuid``와 ``riot_name`` 매핑을 읽는다."""
    engine = create_engine(get_db_url())
    player_table = get_player_table()
    query = text(
        f"""
        SELECT puuid, riot_name
        FROM {player_table}
        WHERE COALESCE(is_deleted, false) = false
        """
    )

    with engine.connect() as conn:
        return pd.read_sql(query, conn).drop_duplicates(subset=["puuid"])


def load_guild_members_for_mmr(guild_id: str | None = None) -> pd.DataFrame:
    """현재 활성 길드 멤버의 계정 귀속 관계를 일괄 조회한다."""
    table_name = get_guild_member_table()
    query = text(
        f"SELECT guild_id, account, main_account, is_main, status FROM {table_name} "
        "WHERE is_deleted = false"
        + (" AND guild_id = :guild_id" if guild_id is not None else "")
    )
    engine = create_engine(get_db_url())
    with engine.connect() as conn:
        return pd.read_sql(query, conn, params={"guild_id": guild_id} if guild_id is not None else {})


def save_mmr_results_to_db(
    match_results: pd.DataFrame,
    user_summary: pd.DataFrame,
    replace_scopes: pd.DataFrame | None = None,
) -> None:
    """계산된 MMR 결과를 PostgreSQL 결과 테이블에 교체 저장한다.

    ``replace_scopes``는 이번 계산 대상인 ``(guild_id, season)`` 목록이다. 계산 결과가
    없는 범위(경기가 전부 제외된 길드·시즌)의 예전 행도 지우려면 계산 대상 기준으로
    넘긴다. 생략하면 결과 행의 범위를 쓴다.
    """
    scopes = _resolve_replace_scopes(match_results, user_summary, replace_scopes)
    engine = create_engine(get_db_url())
    with engine.begin() as conn:
        matches = _align_to_table_columns(
            match_results, conn, get_mmr_match_result_table()
        )
        _delete_existing_season_scope(scopes, conn, get_mmr_match_result_table())
        matches.to_sql(
            get_mmr_match_result_table(),
            conn,
            if_exists="append",
            index=False,
            method="multi",
            chunksize=1000,
        )
        summary = _align_to_table_columns(user_summary, conn, get_mmr_summary_table())
        _delete_existing_season_scope(scopes, conn, get_mmr_summary_table())
        summary.to_sql(
            get_mmr_summary_table(),
            conn,
            if_exists="append",
            index=False,
            method="multi",
            chunksize=1000,
            dtype=_jsonb_dtype(summary),
        )


def _resolve_replace_scopes(
    match_results: pd.DataFrame,
    user_summary: pd.DataFrame,
    replace_scopes: pd.DataFrame | None,
) -> pd.DataFrame:
    """교체할 (guild_id, season) 범위를 정하고, 저장할 행이 범위 안에 있는지 검증한다."""
    keys = ["guild_id", "season"]
    for name, frame in (("match_results", match_results), ("user_summary", user_summary)):
        missing = set(keys) - set(frame.columns)
        if missing:
            raise ValueError(f"{name} is missing replace-scope columns: {sorted(missing)}")
        if frame[keys].isna().any().any():
            raise ValueError(f"{name} contains missing guild_id or season values.")

    scopes = match_results[keys] if replace_scopes is None else replace_scopes[keys]
    scopes = scopes.drop_duplicates().reset_index(drop=True)
    if scopes.isna().any().any():
        raise ValueError("Replace scopes contain missing guild_id or season values.")

    scope_keys = set(scopes.itertuples(index=False, name=None))
    for name, frame in (("match_results", match_results), ("user_summary", user_summary)):
        outside = set(frame[keys].drop_duplicates().itertuples(index=False, name=None)) - scope_keys
        if outside:
            raise ValueError(f"{name} has rows outside the replace scopes: {sorted(outside)[:5]}")
    return scopes


def _align_to_table_columns(
    df: pd.DataFrame,
    conn,
    table_name: str,
) -> pd.DataFrame:
    """대상 DB 테이블에 실제로 존재하는 컬럼만 남긴다."""
    table_cols = {col["name"] for col in inspect(conn).get_columns(table_name)}
    keep_cols = [col for col in df.columns if col in table_cols]
    return df[keep_cols]


def _jsonb_dtype(df: pd.DataFrame) -> dict[str, JSONB]:
    """to_sql에 넘길 JSONB 컬럼 dtype 매핑을 만든다."""
    return {column: JSONB() for column in JSONB_RESULT_COLUMNS if column in df.columns}


def _delete_existing_season_scope(scopes: pd.DataFrame, conn, table_name: str) -> None:
    """전체 재계산 대상 길드·시즌의 이전 결과를 제거한다.

    전체 계산은 길드·시즌의 모든 경기를 처음부터 다시 계산하므로, 이번 계산에서 빠진
    경기(원천 삭제·계정 충돌 거부)의 예전 결과와 탈퇴 유저 요약도 함께 정리한다.
    계산하지 않은 시즌의 결과는 건드리지 않는다.
    """
    if scopes.empty:
        return
    records = scopes[["guild_id", "season"]].drop_duplicates().to_dict(orient="records")
    conn.execute(
        text(f"DELETE FROM {table_name} WHERE guild_id = :guild_id AND season = :season"),
        records,
    )
