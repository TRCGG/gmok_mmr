-- DB TEST ONLY: temporary MMR baseline storage.
-- 백엔드 baseline 저장 API가 준비되기 전 로컬 DB 검증에만 사용한다.
-- 운영 마이그레이션으로 간주하지 말고, 백엔드 연동 후 삭제하거나 분리한다.
--
-- Apply:
--   psql -d <DB_NAME> -f migrations/db_test/001_create_mmr_baselines.sql

CREATE TABLE IF NOT EXISTS mmr_baselines (
    id BIGSERIAL PRIMARY KEY,

    season VARCHAR(64) NOT NULL,
    baseline_version VARCHAR(64) NOT NULL,
    is_active BOOLEAN NOT NULL DEFAULT false,

    -- 산식 v2 baseline: 퍼포먼스(perf_z) · 승부격차(blow) 표준화 기준값
    performance_baseline JSONB NOT NULL,
    blowout_baseline JSONB NOT NULL,
    metadata JSONB NOT NULL DEFAULT '{}'::jsonb,

    match_count INTEGER,
    player_game_row_count INTEGER,

    calculated_at TIMESTAMPTZ,
    saved_at TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP,

    CONSTRAINT uq_mmr_baselines_season_version
        UNIQUE (season, baseline_version)
);

CREATE UNIQUE INDEX IF NOT EXISTS uq_mmr_baselines_active_per_season
    ON mmr_baselines (season)
    WHERE is_active = true;

CREATE INDEX IF NOT EXISTS idx_mmr_baselines_season_version
    ON mmr_baselines (season, baseline_version);

CREATE INDEX IF NOT EXISTS idx_mmr_baselines_saved_at
    ON mmr_baselines (saved_at DESC);
