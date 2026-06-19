"""DB 테스트용 원천 경기 데이터 repository.

SQL 문과 DB read/write 책임을 관리한다.
백엔드 API 완성 후 db_test 패키지 전체와 함께 삭제한다.
"""

from __future__ import annotations

import pandas as pd
from sqlalchemy import create_engine, inspect, text

from .config import (
    get_db_url,
    get_mmr_match_result_table,
    get_mmr_summary_table,
    get_player_game_table,
    get_player_table,
)


def load_match_dataframe_from_db(guild_id: str | None = None) -> pd.DataFrame:
    """PostgreSQL ``mmr_participant_metric`` 에서 원천 참가자 지표를 읽는다.

    내부 파이프라인은 DDL 컬럼명을 그대로 쓰므로 별도 alias 없이 ``*`` 로 읽고,
    interface_spec 호환을 위해 PK ``id`` 를 ``match_participant_id`` 로만 추가 노출한다.
    적격 필터(is_mmr_eligible/is_deleted)는 cleaning에서도 적용되지만 read 단계에서도 건다.

    Args:
        guild_id: 지정 시 해당 guild의 경기만 읽는다. None이면 전체.
    """
    engine = create_engine(get_db_url())
    table = get_player_game_table()
    guild_clause = "AND mpm.guild_id = :guild_id" if guild_id is not None else ""

    query = text(
        f"""
        SELECT
            mpm.*,
            mpm.id AS match_participant_id
        FROM {table} mpm
        WHERE COALESCE(mpm.is_deleted, false) = false
          AND COALESCE(mpm.is_mmr_eligible, true) = true
          {guild_clause}
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


def save_mmr_results_to_db(
    match_results: pd.DataFrame,
    user_summary: pd.DataFrame,
) -> None:
    """계산된 MMR 결과를 PostgreSQL 결과 테이블에 추가 저장한다."""
    engine = create_engine(get_db_url())
    with engine.begin() as conn:
        _align_to_table_columns(match_results, conn, get_mmr_match_result_table()).to_sql(
            get_mmr_match_result_table(),
            conn,
            if_exists="append",
            index=False,
            method="multi",
            chunksize=1000,
        )
        _align_to_table_columns(user_summary, conn, get_mmr_summary_table()).to_sql(
            get_mmr_summary_table(),
            conn,
            if_exists="append",
            index=False,
            method="multi",
            chunksize=1000,
        )


def _align_to_table_columns(
    df: pd.DataFrame,
    conn,
    table_name: str,
) -> pd.DataFrame:
    """대상 DB 테이블에 실제로 존재하는 컬럼만 남긴다."""
    table_cols = {col["name"] for col in inspect(conn).get_columns(table_name)}
    keep_cols = [col for col in df.columns if col in table_cols]
    return df[keep_cols]
