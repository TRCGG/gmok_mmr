-- MMR result tables
-- Apply this migration before running:
--   python scripts/main_pipeline.py --source db --sink db

CREATE TABLE IF NOT EXISTS mmr_match_results (
    id BIGSERIAL PRIMARY KEY,

    replay_code VARCHAR(128) NOT NULL,
    puuid VARCHAR(64) NOT NULL,
    champion_id VARCHAR(16),
    team VARCHAR(8),
    position VARCHAR(16) NOT NULL,
    played_at TIMESTAMP,

    game_result INTEGER NOT NULL,
    kills INTEGER,
    deaths INTEGER,
    assists INTEGER,
    gold INTEGER,
    cc_time INTEGER,
    game_duration NUMERIC,
    damage_to_champions INTEGER,
    damage_taken INTEGER,
    vision_score INTEGER,
    vision_bought INTEGER,
    penta_kills INTEGER,

    gold_per_min NUMERIC,
    dpm NUMERIC,
    damage_taken_per_min NUMERIC,
    cc_time_per_min NUMERIC,
    kda NUMERIC,
    damage_taken_per_death NUMERIC,
    damage_dealt_per_death NUMERIC,

    raw_game_impact NUMERIC,
    game_impact NUMERIC,
    game_impact_winloss_norm NUMERIC,
    game_n_person_contribution NUMERIC,
    game_impact_vs_opponent NUMERIC,

    pre_game_pos_mmr INTEGER,
    expected_score NUMERIC,
    actual_score NUMERIC,
    relative_factor NUMERIC,
    personal_factor NUMERIC,
    final_factor NUMERIC,
    mmr_change INTEGER,
    pos_cumulative_mmr INTEGER,
    total_mmr INTEGER,

    calculated_at TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP
);

CREATE INDEX IF NOT EXISTS idx_mmr_match_results_replay_code
    ON mmr_match_results (replay_code);

CREATE INDEX IF NOT EXISTS idx_mmr_match_results_puuid_position
    ON mmr_match_results (puuid, position);

CREATE INDEX IF NOT EXISTS idx_mmr_match_results_calculated_at
    ON mmr_match_results (calculated_at);


CREATE TABLE IF NOT EXISTS mmr_user_summary (
    id BIGSERIAL PRIMARY KEY,

    puuid VARCHAR(64) NOT NULL,
    total_mmr NUMERIC,
    total_games INTEGER,
    overall_winrate NUMERIC,

    top_mmr NUMERIC,
    top_winrate NUMERIC,
    top_games INTEGER,

    bottom_mmr NUMERIC,
    bottom_winrate NUMERIC,
    bottom_games INTEGER,

    middle_mmr NUMERIC,
    middle_winrate NUMERIC,
    middle_games INTEGER,

    jungle_mmr NUMERIC,
    jungle_winrate NUMERIC,
    jungle_games INTEGER,

    utility_mmr NUMERIC,
    utility_winrate NUMERIC,
    utility_games INTEGER,

    calculated_at TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP
);

CREATE INDEX IF NOT EXISTS idx_mmr_user_summary_puuid
    ON mmr_user_summary (puuid);

CREATE INDEX IF NOT EXISTS idx_mmr_user_summary_total_mmr
    ON mmr_user_summary (total_mmr DESC);

CREATE INDEX IF NOT EXISTS idx_mmr_user_summary_calculated_at
    ON mmr_user_summary (calculated_at);
