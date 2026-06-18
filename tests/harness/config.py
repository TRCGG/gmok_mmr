"""MMR 파이프라인 실행 설정 모듈.

데이터 입출력 방식(DB/API)과 공통 설정만 관리한다.
DB 접속 정보는 db_test.config에서 관리한다.
"""

from __future__ import annotations

import os
from pathlib import Path

try:
    from dotenv import load_dotenv

    PROJECT_ROOT = Path(__file__).resolve().parents[2]
    load_dotenv(PROJECT_ROOT / ".env")
except ImportError:
    PROJECT_ROOT = Path(__file__).resolve().parents[2]


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
