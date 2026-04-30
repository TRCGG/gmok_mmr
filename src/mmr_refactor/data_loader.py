"""Raw match and user-data loaders.

Current test flow:
    PostgreSQL -> pandas DataFrame

Final service flow:
    Backend API -> pandas DataFrame

The rest of the MMR pipeline should call only ``load_match_dataframe`` and
``load_user_name_dataframe`` so the transport can change without touching the
calculation modules.
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
    """Load row-level raw match data from the configured source."""
    source = (source or get_data_source()).lower()
    if source == "db":
        return load_match_dataframe_from_db()
    if source == "api":
        return _load_match_from_api()
    raise ValueError(f"Unsupported MMR_DATA_SOURCE: {source!r}")


def load_user_name_dataframe(source: str | None = None) -> pd.DataFrame:
    """Load ``puuid`` to ``riot_name`` mapping from the configured source."""
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
    """Read raw player-game records from the backend API.

    Expected response shape is a JSON array whose keys match the pipeline
    column names used by ``_load_match_from_db``.
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
    """Read user names from the backend API."""
    import requests

    resp = requests.get(
        f"{get_api_base_url()}/v1/mmr/users",
        headers=_api_headers(),
        timeout=30,
    )
    resp.raise_for_status()
    return pd.DataFrame(resp.json())[["puuid", "riot_name"]].drop_duplicates(subset=["puuid"])
