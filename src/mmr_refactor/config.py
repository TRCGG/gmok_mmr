"""Runtime configuration for the MMR pipeline.

The current test flow reads raw match data from PostgreSQL and writes the
calculated MMR outputs back to PostgreSQL. Later, the same public loader/writer
functions can be switched to backend API calls by changing environment values.
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
    """Return a SQLAlchemy PostgreSQL URL built from environment variables."""
    user = os.environ["DB_USER"]
    password = os.environ["DB_PASSWORD"]
    host = os.environ.get("DB_HOST", "localhost")
    port = os.environ.get("DB_PORT", "5432")
    name = os.environ["DB_NAME"]
    return f"postgresql+psycopg2://{user}:{password}@{host}:{port}/{name}"


def get_data_source() -> str:
    """Return the raw-data source: ``db`` now, ``api`` later."""
    return os.environ.get("MMR_DATA_SOURCE", "db").lower()


def get_result_sink() -> str:
    """Return the result destination: ``db`` now, ``api`` later."""
    return os.environ.get("MMR_RESULT_SINK", "db").lower()


def get_api_base_url() -> str:
    """Return the backend API base URL used by API loader/writer adapters."""
    return os.environ["API_BASE_URL"].rstrip("/")


def get_api_token() -> str:
    """Return an optional bearer token for backend API calls."""
    return os.environ.get("API_TOKEN", "")


def get_output_dir() -> Path:
    """Return the local output directory for optional files and diagnostics."""
    out = Path(os.environ.get("OUTPUT_DIR", "./output"))
    out.mkdir(parents=True, exist_ok=True)
    return out


def get_mmr_match_result_table() -> str:
    """Return the DB table name for row-level MMR outputs."""
    return os.environ.get("MMR_MATCH_RESULT_TABLE", "mmr_match_results")


def get_mmr_summary_table() -> str:
    """Return the DB table name for player-level MMR summary outputs."""
    return os.environ.get("MMR_SUMMARY_TABLE", "mmr_user_summary")


def get_player_game_table() -> str:
    """Return the raw player-game table used by the DB loader."""
    return _safe_sql_identifier(os.environ.get("MMR_PLAYER_GAME_TABLE", "player_game"))


def get_player_table() -> str:
    """Return the raw player table used by the DB loader."""
    return _safe_sql_identifier(os.environ.get("MMR_PLAYER_TABLE", "player"))


def _safe_sql_identifier(value: str) -> str:
    """Validate a simple SQL table identifier before string interpolation."""
    if not re.fullmatch(r"[A-Za-z_][A-Za-z0-9_]*", value):
        raise ValueError(f"Unsafe SQL identifier: {value!r}")
    return value
