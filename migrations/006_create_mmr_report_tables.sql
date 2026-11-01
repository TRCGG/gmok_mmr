-- 프론트 조회용 MMR 이력 및 유저·포지션 요약
-- 적용 후 scripts/run_mmr_once.py 한 번으로 계산 결과와 함께 채워진다.
BEGIN;

CREATE TABLE IF NOT EXISTS mmr_history (
    id BIGSERIAL PRIMARY KEY,
    guild_id VARCHAR(128) NOT NULL,
    player_code VARCHAR(64) NOT NULL,
    position VARCHAR(16) NOT NULL,
    replay_code VARCHAR(128) NOT NULL,
    played_at TIMESTAMP NOT NULL,
    mmr NUMERIC NOT NULL,
    mmr_change INTEGER NOT NULL,
    calculated_at TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP,
    CONSTRAINT uq_mmr_history_game
        UNIQUE (guild_id, player_code, position, replay_code)
);

CREATE INDEX IF NOT EXISTS idx_mmr_history_player_position_date
    ON mmr_history (guild_id, player_code, position, played_at);

CREATE TABLE IF NOT EXISTS mmr_user_position_summary (
    id BIGSERIAL PRIMARY KEY,
    guild_id VARCHAR(128) NOT NULL,
    player_code VARCHAR(64) NOT NULL,
    position VARCHAR(16) NOT NULL,
    mmr NUMERIC NOT NULL,
    games INTEGER NOT NULL,
    winrate NUMERIC,
    game_impact NUMERIC,
    game_n_person_contribution NUMERIC,
    game_impact_vs_opponent NUMERIC,
    damage_taken_per_min NUMERIC,
    dpm NUMERIC,
    gold_per_min NUMERIC,
    damage_dealt_per_death NUMERIC,
    damage_taken_per_death NUMERIC,
    vision_score NUMERIC,
    cc_time_per_min NUMERIC,
    kda NUMERIC,
    cs_per_min NUMERIC,
    exp_per_min NUMERIC,
    base_style VARCHAR(64) NOT NULL DEFAULT '분류 준비 상태',
    position_style VARCHAR(64) NOT NULL DEFAULT '분류 준비 상태',
    comparison_basis VARCHAR(128) NOT NULL DEFAULT '같은 클랜·포지션 전체',
    reference_users INTEGER NOT NULL DEFAULT 0,
    calculated_at TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP,
    CONSTRAINT uq_mmr_user_position_summary
        UNIQUE (guild_id, player_code, position)
);

CREATE INDEX IF NOT EXISTS idx_mmr_user_position_summary_guild_position_mmr
    ON mmr_user_position_summary (guild_id, position, mmr DESC);

COMMIT;
