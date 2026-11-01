"""리포트 마이그레이션과 전체 MMR 배치를 한 번에 실행한다.

Usage::

    python scripts/run_mmr_report_once.py
"""

from __future__ import annotations

from pathlib import Path
import sys

from sqlalchemy import create_engine

ROOT = Path(__file__).resolve().parents[1]
for path in (ROOT, ROOT / "src", ROOT / "tests"):
    if str(path) not in sys.path:
        sys.path.insert(0, str(path))

try:
    from dotenv import load_dotenv
except ImportError as exc:  # pragma: no cover
    raise SystemExit("python-dotenv is required. Run: pip install -r requirements.txt") from exc

load_dotenv(ROOT / ".env")

from harness.db_test.config import get_db_url
from scripts.run_mmr_once import main as run_mmr_once


def apply_report_migration() -> None:
    migration_path = ROOT / "migrations" / "006_create_mmr_report_tables.sql"
    sql = migration_path.read_text(encoding="utf-8")
    engine = create_engine(get_db_url())
    raw_connection = engine.raw_connection()
    try:
        cursor = raw_connection.cursor()
        try:
            cursor.execute(sql)
        finally:
            cursor.close()
        raw_connection.commit()
    except Exception:
        raw_connection.rollback()
        raise
    finally:
        raw_connection.close()
        engine.dispose()
    print(f"Applied migration: {migration_path.name}")


def main() -> None:
    apply_report_migration()
    run_mmr_once()


if __name__ == "__main__":
    main()
