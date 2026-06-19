-- MMR 산식 v2 결과 테이블 재생성
-- v1(replay_code/played_at/game_impact_*·factor)에서 v2(custom_match_id/perf_z/blow/팀평균 Elo)로 교체.
-- Apply:
--   psql -d <DB_NAME> -f migrations/007_recreate_mmr_result_tables_v2.sql
--
-- 주의: DB 테스트 결과 저장용. 백엔드 연동 후 결과 저장은 백엔드 책임으로 이관한다.

DROP TABLE IF EXISTS mmr_match_results;
DROP TABLE IF EXISTS mmr_user_summary;

CREATE TABLE mmr_match_results (
    id BIGSERIAL PRIMARY KEY,

    custom_match_id VARCHAR(255) NOT NULL,
    match_participant_id BIGINT,
    puuid VARCHAR(128) NOT NULL,
    position VARCHAR(16) NOT NULL,
    game_team VARCHAR(8),
    game_result INTEGER NOT NULL,

    perf_z NUMERIC,
    blow NUMERIC,

    pre_game_mmr INTEGER,
    pre_game_pos_mmr INTEGER,
    team_mmr NUMERIC,
    expected_score NUMERIC,
    actual_score NUMERIC,
    k_factor NUMERIC,
    mmr_change INTEGER,
    total_mmr INTEGER,
    pos_cumulative_mmr INTEGER,

    calculated_at TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP
);

CREATE INDEX idx_mmr_match_results_custom_match ON mmr_match_results (custom_match_id);
CREATE INDEX idx_mmr_match_results_puuid_position ON mmr_match_results (puuid, position);
CREATE INDEX idx_mmr_match_results_calculated_at ON mmr_match_results (calculated_at);


CREATE TABLE mmr_user_summary (
    id BIGSERIAL PRIMARY KEY,

    puuid VARCHAR(128) NOT NULL,
    total_mmr INTEGER,
    total_games INTEGER,
    overall_winrate NUMERIC,
    main_position VARCHAR(16),
    is_ranked BOOLEAN,           -- 20판 컷: 정식(true) / 배치중(false)

    top_mmr NUMERIC, top_winrate NUMERIC, top_games INTEGER,
    bottom_mmr NUMERIC, bottom_winrate NUMERIC, bottom_games INTEGER,
    middle_mmr NUMERIC, middle_winrate NUMERIC, middle_games INTEGER,
    jungle_mmr NUMERIC, jungle_winrate NUMERIC, jungle_games INTEGER,
    utility_mmr NUMERIC, utility_winrate NUMERIC, utility_games INTEGER,

    calculated_at TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP
);

CREATE INDEX idx_mmr_user_summary_puuid ON mmr_user_summary (puuid);
CREATE INDEX idx_mmr_user_summary_total_mmr ON mmr_user_summary (total_mmr DESC);
CREATE INDEX idx_mmr_user_summary_calculated_at ON mmr_user_summary (calculated_at);
