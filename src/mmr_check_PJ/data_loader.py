"""원천 경기 데이터와 사용자명 데이터 loader 모듈.

현재 테스트 흐름:
    PostgreSQL -> pandas DataFrame

최종 서비스 흐름:
    Backend API -> pandas DataFrame

MMR 계산 모듈은 ``load_match_dataframe``과 ``load_user_name_dataframe``만
호출한다. 이렇게 두면 DB/API 전송 방식이 바뀌어도 계산 로직은 수정하지 않는다.
"""

from __future__ import annotations

import pandas as pd

from .config import (
    get_api_base_url,
    get_api_token,
    get_data_source,
)
from .repository import (
    load_match_dataframe_from_db,
    load_user_name_dataframe_from_db,
)


def load_match_dataframe(source: str | None = None) -> pd.DataFrame:
    """설정된 입력 방식에서 row 단위 원천 경기 데이터를 읽는다."""
    source = (source or get_data_source()).lower()
    if source == "db":
        return load_match_dataframe_from_db()
    if source == "api":
        return _load_match_from_api()
    raise ValueError(f"Unsupported MMR_DATA_SOURCE: {source!r}")


def load_user_name_dataframe(source: str | None = None) -> pd.DataFrame:
    """설정된 입력 방식에서 ``puuid``와 ``riot_name`` 매핑을 읽는다."""
    source = (source or get_data_source()).lower()
    if source == "db":
        return load_user_name_dataframe_from_db()
    if source == "api":
        return _load_user_name_from_api()
    raise ValueError(f"Unsupported MMR_DATA_SOURCE: {source!r}")


def _api_headers() -> dict[str, str]:
    token = get_api_token()
    if not token:
        return {}
    return {"Authorization": f"Bearer {token}"}


def _load_match_from_api() -> pd.DataFrame:
    """백엔드 API에서 원천 player-game 레코드를 읽는다.

    응답은 파이프라인 컬럼명과 같은 key를 가진 JSON 배열이어야 한다.
    """
    import requests

    resp = requests.get(
        f"{get_api_base_url()}/v1/mmr/raw-matches",
        headers=_api_headers(),
        timeout=30,
    )
    resp.raise_for_status()
    return pd.DataFrame(resp.json())


def _load_user_name_from_api() -> pd.DataFrame:
    """백엔드 API에서 사용자명 데이터를 읽는다."""
    import requests

    resp = requests.get(
        f"{get_api_base_url()}/v1/mmr/users",
        headers=_api_headers(),
        timeout=30,
    )
    resp.raise_for_status()
    return pd.DataFrame(resp.json())[["puuid", "riot_name"]].drop_duplicates(subset=["puuid"])
