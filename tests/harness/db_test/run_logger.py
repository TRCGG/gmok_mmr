"""MMR DB 테스트 실행 기록 모듈.

컨텍스트 매니저로 사용하면 소요시간·메모리·CPU를 자동 측정 후 DB에 저장한다.
백엔드 API 완성 후 db_test 패키지 전체와 함께 삭제한다.

사용 예::

    with MMRTestRunLogger(
        script_name="calculate_full_mmr_with_db_baseline",
        season="2026",
        baseline_version="2026-06",
        source_table="player_game_stats",
    ) as logger:
        # ... 계산 로직 ...
        logger.set_counts(match_count=30, player_game_row_count=300, user_count=15)
"""

from __future__ import annotations

import os
import time
import tracemalloc
import uuid
from contextlib import contextmanager
from dataclasses import dataclass, field
from datetime import UTC, datetime
from typing import Any

from sqlalchemy import create_engine, text

from .config import get_db_url

_LOG_TABLE = os.environ.get("MMR_TEST_RUN_LOG_TABLE", "mmr_test_run_log")


@dataclass
class MMRTestRunLogger:
    script_name: str
    season: str | None = None
    baseline_version: str | None = None
    source_table: str | None = None

    run_id: str = field(default_factory=lambda: str(uuid.uuid4())[:16])

    _match_count: int | None = field(default=None, init=False, repr=False)
    _player_game_row_count: int | None = field(default=None, init=False, repr=False)
    _user_count: int | None = field(default=None, init=False, repr=False)
    _started_at: datetime | None = field(default=None, init=False, repr=False)
    _cpu_start: float = field(default=0.0, init=False, repr=False)

    def set_counts(
        self,
        *,
        match_count: int | None = None,
        player_game_row_count: int | None = None,
        user_count: int | None = None,
    ) -> None:
        """계산 완료 후 처리량 수치를 설정한다."""
        if match_count is not None:
            self._match_count = match_count
        if player_game_row_count is not None:
            self._player_game_row_count = player_game_row_count
        if user_count is not None:
            self._user_count = user_count

    def __enter__(self) -> "MMRTestRunLogger":
        self._started_at = datetime.now(UTC)
        self._cpu_start = time.process_time()
        tracemalloc.start()
        self._save(status="running")
        return self

    def __exit__(self, exc_type, exc_val, exc_tb) -> None:
        finished_at = datetime.now(UTC)
        cpu_time = time.process_time() - self._cpu_start
        _, peak = tracemalloc.get_traced_memory()
        tracemalloc.stop()

        duration = (finished_at - self._started_at).total_seconds()
        peak_mb = round(peak / 1024 / 1024, 2)

        if exc_type is None:
            self._update(
                finished_at=finished_at,
                duration_seconds=round(duration, 3),
                peak_memory_mb=peak_mb,
                cpu_time_seconds=round(cpu_time, 3),
                status="success",
            )
        else:
            self._update(
                finished_at=finished_at,
                duration_seconds=round(duration, 3),
                peak_memory_mb=peak_mb,
                cpu_time_seconds=round(cpu_time, 3),
                status="error",
                error_message=f"{exc_type.__name__}: {exc_val}",
            )

    def _save(self, status: str) -> None:
        engine = create_engine(get_db_url())
        with engine.begin() as conn:
            conn.execute(
                text(
                    f"""
                    INSERT INTO {_LOG_TABLE} (
                        run_id, script_name,
                        season, baseline_version, source_table,
                        started_at, status
                    ) VALUES (
                        :run_id, :script_name,
                        :season, :baseline_version, :source_table,
                        :started_at, :status
                    )
                    """
                ),
                {
                    "run_id": self.run_id,
                    "script_name": self.script_name,
                    "season": self.season,
                    "baseline_version": self.baseline_version,
                    "source_table": self.source_table,
                    "started_at": self._started_at,
                    "status": status,
                },
            )

    def _update(self, finished_at: datetime, status: str, **kwargs: Any) -> None:
        engine = create_engine(get_db_url())
        with engine.begin() as conn:
            conn.execute(
                text(
                    f"""
                    UPDATE {_LOG_TABLE} SET
                        finished_at           = :finished_at,
                        duration_seconds      = :duration_seconds,
                        peak_memory_mb        = :peak_memory_mb,
                        cpu_time_seconds      = :cpu_time_seconds,
                        match_count           = :match_count,
                        player_game_row_count = :player_game_row_count,
                        user_count            = :user_count,
                        status                = :status,
                        error_message         = :error_message
                    WHERE run_id = :run_id
                    """
                ),
                {
                    "run_id": self.run_id,
                    "finished_at": finished_at,
                    "duration_seconds": kwargs.get("duration_seconds"),
                    "peak_memory_mb": kwargs.get("peak_memory_mb"),
                    "cpu_time_seconds": kwargs.get("cpu_time_seconds"),
                    "match_count": self._match_count,
                    "player_game_row_count": self._player_game_row_count,
                    "user_count": self._user_count,
                    "status": status,
                    "error_message": kwargs.get("error_message"),
                },
            )
