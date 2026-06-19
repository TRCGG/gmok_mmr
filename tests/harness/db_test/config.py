"""DB 테스트용 환경변수 설정 모듈.

백엔드 API 완성 후 db_test 패키지 전체와 함께 삭제한다.
"""

from __future__ import annotations

import os
import re
from pathlib import Path

try:
    from dotenv import load_dotenv

    _PROJECT_ROOT = Path(__file__).resolve().parents[3]
    load_dotenv(_PROJECT_ROOT / ".env")
except ImportError:
    pass


def get_db_url() -> str:
    """환경변수로 SQLAlchemy PostgreSQL 접속 URL을 만든다."""
    user = os.environ["DB_USER"]
    password = os.environ["DB_PASSWORD"]
    host = os.environ.get("DB_HOST", "localhost")
    port = os.environ.get("DB_PORT", "5432")
    name = os.environ["DB_NAME"]
    return f"postgresql+psycopg2://{user}:{password}@{host}:{port}/{name}"


def get_player_game_table() -> str:
    """DB loader가 조회할 원천 참가자 지표 테이블명을 반환한다 (DDL: mmr_participant_metric)."""
    return _safe_sql_identifier(
        os.environ.get("MMR_PARTICIPANT_METRIC_TABLE")
        or os.environ.get("MMR_PLAYER_GAME_TABLE", "mmr_participant_metric")
    )


def get_player_table() -> str:
    """DB loader가 조회할 원천 player 테이블명을 반환한다."""
    return _safe_sql_identifier(os.environ.get("MMR_PLAYER_TABLE", "player"))


def get_mmr_match_result_table() -> str:
    """row 단위 MMR 결과를 저장할 DB 테이블명을 반환한다."""
    return os.environ.get("MMR_MATCH_RESULT_TABLE", "mmr_match_results")


def get_mmr_summary_table() -> str:
    """플레이어 단위 MMR 요약 결과를 저장할 DB 테이블명을 반환한다."""
    return os.environ.get("MMR_SUMMARY_TABLE", "mmr_user_summary")


def get_mmr_baseline_table() -> str:
    """DB 테스트용 baseline 테이블명을 반환한다."""
    return _safe_sql_identifier(os.environ.get("MMR_BASELINE_TABLE", "mmr_baselines"))


def _safe_sql_identifier(value: str) -> str:
    """SQL 문자열 보간 전에 단순 테이블 식별자 형식인지 검증한다."""
    if not re.fullmatch(r"[A-Za-z_][A-Za-z0-9_]*", value):
        raise ValueError(f"Unsafe SQL identifier: {value!r}")
    return value
