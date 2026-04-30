"""MMR 파이프라인 실행 설정 모듈.

현재 테스트 흐름은 PostgreSQL에서 원천 경기 데이터를 읽고 계산된 MMR 결과를
다시 PostgreSQL에 저장한다. 추후 환경변수만 바꾸면 같은 loader/writer
인터페이스로 백엔드 API 호출 방식으로 전환할 수 있다.
"""

from __future__ import annotations

import os
from pathlib import Path
import re

try:
    from dotenv import load_dotenv

    PROJECT_ROOT = Path(__file__).resolve().parents[2]
    load_dotenv(PROJECT_ROOT / ".env")
except ImportError:
    PROJECT_ROOT = Path(__file__).resolve().parents[2]


def get_db_url() -> str:
    """환경변수로 SQLAlchemy PostgreSQL 접속 URL을 만든다."""
    user = os.environ["DB_USER"]
    password = os.environ["DB_PASSWORD"]
    host = os.environ.get("DB_HOST", "localhost")
    port = os.environ.get("DB_PORT", "5432")
    name = os.environ["DB_NAME"]
    return f"postgresql+psycopg2://{user}:{password}@{host}:{port}/{name}"


def get_data_source() -> str:
    """원천 데이터 입력 방식을 반환한다. 현재는 ``db``, 추후 ``api``를 사용한다."""
    return os.environ.get("MMR_DATA_SOURCE", "db").lower()


def get_result_sink() -> str:
    """계산 결과 저장 방식을 반환한다. 현재는 ``db``, 추후 ``api``를 사용한다."""
    return os.environ.get("MMR_RESULT_SINK", "db").lower()


def get_api_base_url() -> str:
    """API loader/writer adapter가 사용할 백엔드 API base URL을 반환한다."""
    return os.environ["API_BASE_URL"].rstrip("/")


def get_api_token() -> str:
    """백엔드 API 호출에 사용할 bearer token을 반환한다."""
    return os.environ.get("API_TOKEN", "")


def get_output_dir() -> Path:
    """선택 파일과 진단 결과를 저장할 로컬 output 경로를 반환한다."""
    out = Path(os.environ.get("OUTPUT_DIR", "./output"))
    out.mkdir(parents=True, exist_ok=True)
    return out


def get_mmr_match_result_table() -> str:
    """row 단위 MMR 결과를 저장할 DB 테이블명을 반환한다."""
    return os.environ.get("MMR_MATCH_RESULT_TABLE", "mmr_match_results")


def get_mmr_summary_table() -> str:
    """플레이어 단위 MMR 요약 결과를 저장할 DB 테이블명을 반환한다."""
    return os.environ.get("MMR_SUMMARY_TABLE", "mmr_user_summary")


def get_player_game_table() -> str:
    """DB loader가 조회할 원천 player-game 테이블명을 반환한다."""
    return _safe_sql_identifier(os.environ.get("MMR_PLAYER_GAME_TABLE", "player_game"))


def get_player_table() -> str:
    """DB loader가 조회할 원천 player 테이블명을 반환한다."""
    return _safe_sql_identifier(os.environ.get("MMR_PLAYER_TABLE", "player"))


def _safe_sql_identifier(value: str) -> str:
    """SQL 문자열 보간 전에 단순 테이블 식별자 형식인지 검증한다."""
    if not re.fullmatch(r"[A-Za-z_][A-Za-z0-9_]*", value):
        raise ValueError(f"Unsafe SQL identifier: {value!r}")
    return value
