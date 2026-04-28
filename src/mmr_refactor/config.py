"""환경 변수 로딩 및 연결 정보 헬퍼.

`.env` 파일은 프로젝트 루트에 두고, 실제 값은 `.env.example` 참고.
"""

from __future__ import annotations

import os
from pathlib import Path

try:
    from dotenv import load_dotenv

    _PROJECT_ROOT = Path(__file__).resolve().parents[2]
    load_dotenv(_PROJECT_ROOT / ".env")
except ImportError:
    # python-dotenv 미설치 시 OS 환경변수만 사용
    pass


def get_db_url() -> str:
    """SQLAlchemy 형식의 PostgreSQL 연결 URL 반환.

    필요 환경변수: DB_USER, DB_PASSWORD, DB_NAME (필수),
    DB_HOST, DB_PORT (선택, 기본 localhost:5432).
    """
    user = os.environ["DB_USER"]
    password = os.environ["DB_PASSWORD"]
    host = os.environ.get("DB_HOST", "localhost")
    port = os.environ.get("DB_PORT", "5432")
    name = os.environ["DB_NAME"]
    return f"postgresql+psycopg2://{user}:{password}@{host}:{port}/{name}"


def get_output_dir() -> Path:
    """엑셀/이미지 등 산출물 저장 디렉토리. 없으면 생성."""
    out = Path(os.environ.get("OUTPUT_DIR", "./output"))
    out.mkdir(parents=True, exist_ok=True)
    return out


# TODO: 추후 백엔드 API 버전으로 전환 시 사용
# def get_api_base_url() -> str:
#     return os.environ["API_BASE_URL"]
#
# def get_api_token() -> str:
#     return os.environ.get("API_TOKEN", "")
