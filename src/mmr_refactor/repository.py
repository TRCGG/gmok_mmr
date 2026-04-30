"""Database repository functions for the MMR pipeline.

This module owns SQL statements and DB reads/writes. Higher-level loader/writer
modules decide whether the pipeline uses DB or API, then call this repository
when DB mode is selected.
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


def load_match_dataframe_from_db() -> pd.DataFrame:
    """Read raw player-game records from PostgreSQL."""
    engine = create_engine(get_db_url())
    player_game_table = get_player_game_table()

    query = text(
        f"""
        SELECT
            pg.id                                           AS player_game_id,
            pg.replay_code                                  AS replay_code,
            pg.puuid                                        AS puuid,
            pg.champion_id                                 AS champion_id,
            pg.team                                        AS team,
            pg.position                                    AS position,
            pg.win                                         AS win,
            pg.kills                                       AS kills,
            pg.deaths                                      AS deaths,
            pg.assists                                     AS assists,
            pg.gold_earned                                 AS gold,
            pg.cc_time                                     AS cc_time,
            pg.game_duration                               AS game_duration,
            pg.damage_to_champions                         AS damage_to_champions,
            pg.damage_taken                                AS damage_taken,
            pg.vision_score                                AS vision_score,
            pg.control_wards_bought                        AS vision_bought,
            pg.penta_kills                                 AS penta_kills,
            pg.heal_on_teammates                           AS heal_on_teammates,
            pg.shield_on_teammates                         AS shield_on_teammates,
            pg.played_at                                   AS played_at
        FROM {player_game_table} pg
        """
    )

    with engine.connect() as conn:
        return pd.read_sql(query, conn)


def load_user_name_dataframe_from_db() -> pd.DataFrame:
    """Read ``puuid`` to ``riot_name`` mapping from PostgreSQL."""
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
    """Append calculated MMR outputs to PostgreSQL tables."""
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
    """Keep only columns that exist in the target DB table."""
    table_cols = {col["name"] for col in inspect(conn).get_columns(table_name)}
    keep_cols = [col for col in df.columns if col in table_cols]
    return df[keep_cols]
