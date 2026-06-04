-- MMR DB 테스트 실행 기록 테이블
--
-- calculate_baseline_db.py, calculate_full_mmr_with_db_baseline.py 실행마다
-- 소요시간과 리소스 사용량을 기록한다.

CREATE TABLE IF NOT EXISTS mmr_test_run_log (
    id                      BIGSERIAL       PRIMARY KEY,
    run_id                  VARCHAR(64)     NOT NULL,
    script_name             VARCHAR(128)    NOT NULL,

    season                  VARCHAR(32),
    baseline_version        VARCHAR(64),
    source_table            VARCHAR(128),

    match_count             INTEGER,
    player_game_row_count   INTEGER,
    user_count              INTEGER,

    started_at              TIMESTAMPTZ     NOT NULL,
    finished_at             TIMESTAMPTZ,
    duration_seconds        NUMERIC(10, 3),

    peak_memory_mb          NUMERIC(10, 2),
    cpu_time_seconds        NUMERIC(10, 3),

    status                  VARCHAR(16)     NOT NULL DEFAULT 'running',
    error_message           TEXT,

    created_at              TIMESTAMPTZ     NOT NULL DEFAULT CURRENT_TIMESTAMP
);

CREATE INDEX IF NOT EXISTS idx_mmr_test_run_log_run_id
    ON mmr_test_run_log (run_id);

CREATE INDEX IF NOT EXISTS idx_mmr_test_run_log_started_at
    ON mmr_test_run_log (started_at DESC);

CREATE INDEX IF NOT EXISTS idx_mmr_test_run_log_script_name
    ON mmr_test_run_log (script_name, started_at DESC);
