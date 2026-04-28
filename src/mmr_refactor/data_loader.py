"""매치/유저 데이터 로더.

현재 버전: PostgreSQL DB에서 직접 조회.
TODO: 추후 백엔드 API 호출 버전으로 전환 예정.
      파일 하단의 `_load_*_from_api` 주석 블록 참고.
"""

from __future__ import annotations

import pandas as pd
from sqlalchemy import create_engine, text

from .config import get_db_url


# =====================================================
# Public API
# =====================================================

def load_match_dataframe() -> pd.DataFrame:
    """매치 로그 DataFrame 로드.

    현재: DB(`player_game` JOIN `player`)에서 조회.
    TODO: 백엔드 API 전환 시 `_load_match_from_api()`로 교체.
    """
    return _load_match_from_db()


def load_user_name_dataframe() -> pd.DataFrame:
    """puuid → riot_name 매핑 DataFrame 로드.

    현재: DB(`player`)에서 조회.
    TODO: 백엔드 API 전환 시 `_load_user_name_from_api()`로 교체.
    """
    return _load_user_name_from_db()


# =====================================================
# DB 구현 (현재)
# =====================================================

def _load_match_from_db() -> pd.DataFrame:
    """`player_game` 테이블을 파이프라인 컬럼으로 매핑하여 조회.

    NOTE: 실제 운영 스키마에 맞춰 컬럼/per_min 파생을 조정해야 한다.
    """
    engine = create_engine(get_db_url())

    query = text(
        """
        SELECT
            pg.game_id                                     AS replay_code,
            p.puuid                                        AS puuid,
            pg.position                                    AS position,
            pg.kill                                        AS kills,
            pg.death                                       AS deaths,
            pg.assist                                      AS assists,
            pg.gold                                        AS gold,
            pg.time_played                                 AS game_duration,
            pg.total_damage_champions                      AS damage_to_champions,
            pg.total_damage_taken                          AS damage_taken,
            pg.vision_score                                AS vision_score,
            pg.vision_bought                               AS vision_bought,
            pg.ccing                                       AS cc_time,
            pg.penta_kills                                 AS penta_kills,
            pg.game_date                                   AS played_at,
            CASE WHEN pg.game_result = '승' THEN 1 ELSE 0 END AS game_result
        FROM player_game pg
        JOIN player p ON p.player_id = pg.player_id AND p.delete_yn = 'N'
        WHERE pg.delete_yn = 'N'
        """
    )

    with engine.connect() as conn:
        return pd.read_sql(query, conn)


def _load_user_name_from_db() -> pd.DataFrame:
    """`player` 테이블에서 puuid ↔ riot_name 매핑 조회."""
    engine = create_engine(get_db_url())

    query = text(
        """
        SELECT puuid, riot_name
        FROM player
        WHERE delete_yn = 'N'
        """
    )

    with engine.connect() as conn:
        return pd.read_sql(query, conn).drop_duplicates(subset=["puuid"])


# =====================================================
# Backend API 구현 (TODO: 추후 전환)
# =====================================================
# def _load_match_from_api() -> pd.DataFrame:
#     import os
#     import requests
#     from .config import get_api_base_url, get_api_token
#
#     resp = requests.get(
#         f"{get_api_base_url()}/v1/matches",
#         headers={"Authorization": f"Bearer {get_api_token()}"},
#         timeout=30,
#     )
#     resp.raise_for_status()
#     return pd.DataFrame(resp.json())
#
#
# def _load_user_name_from_api() -> pd.DataFrame:
#     import requests
#     from .config import get_api_base_url, get_api_token
#
#     resp = requests.get(
#         f"{get_api_base_url()}/v1/users",
#         headers={"Authorization": f"Bearer {get_api_token()}"},
#         timeout=30,
#     )
#     resp.raise_for_status()
#     return pd.DataFrame(resp.json())[["puuid", "riot_name"]].drop_duplicates(subset=["puuid"])
