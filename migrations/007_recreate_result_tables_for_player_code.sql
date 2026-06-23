-- 결과 테이블을 MMR 신규 기준으로 재생성 (기존 메인 테이블은 아카이브로 rename)
-- 배경:
--   - db_test 계산 식별자를 player_code 기준으로 통합 (puuid -> player_code)
--   - 포지션 컬럼을 코어/계약 enum 으로 전환 (top/jungle/middle/bottom/utility -> top/jug/mid/adc/sup)
-- 방식:
--   기존 메인 테이블(과거 puuid/구 라벨 데이터)은 DROP 하지 않고 *_0623_old 로 rename 해 보존한다.
--   백업 스냅샷(_lol_*/_trc/_0604_*)이 공유 시퀀스를 참조하므로 DROP 대신 rename 으로 의존성 충돌을 피한다.
--   인덱스/PK 이름이 새 테이블과 충돌하지 않도록 함께 rename 한다.

-- 1) 기존 메인 -> 아카이브
ALTER TABLE mmr_match_results RENAME TO mmr_match_results_0623_old;
ALTER INDEX mmr_match_results_pkey RENAME TO mmr_match_results_0623_old_pkey;
ALTER INDEX idx_mmr_match_results_replay_code RENAME TO idx_mmr_match_results_0623_old_replay_code;
ALTER INDEX idx_mmr_match_results_puuid_position RENAME TO idx_mmr_match_results_0623_old_puuid_position;
ALTER INDEX idx_mmr_match_results_calculated_at RENAME TO idx_mmr_match_results_0623_old_calculated_at;

ALTER TABLE mmr_user_summary RENAME TO mmr_user_summary_0623_old;
ALTER INDEX mmr_user_summary_pkey RENAME TO mmr_user_summary_0623_old_pkey;
ALTER INDEX idx_mmr_user_summary_puuid RENAME TO idx_mmr_user_summary_0623_old_puuid;
ALTER INDEX idx_mmr_user_summary_total_mmr RENAME TO idx_mmr_user_summary_0623_old_total_mmr;
ALTER INDEX idx_mmr_user_summary_calculated_at RENAME TO idx_mmr_user_summary_0623_old_calculated_at;

-- 2) 신 스키마로 메인 테이블 재생성
CREATE TABLE mmr_match_results (
    id BIGSERIAL PRIMARY KEY,

    replay_code VARCHAR(128) NOT NULL,
    player_code VARCHAR(64) NOT NULL,
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

CREATE INDEX idx_mmr_match_results_replay_code
    ON mmr_match_results (replay_code);

CREATE INDEX idx_mmr_match_results_player_code_position
    ON mmr_match_results (player_code, position);

CREATE INDEX idx_mmr_match_results_calculated_at
    ON mmr_match_results (calculated_at);


CREATE TABLE mmr_user_summary (
    id BIGSERIAL PRIMARY KEY,

    player_code VARCHAR(64) NOT NULL,
    total_mmr NUMERIC,
    total_games INTEGER,
    overall_winrate NUMERIC,

    top_mmr NUMERIC,
    top_winrate NUMERIC,
    top_games INTEGER,

    jug_mmr NUMERIC,
    jug_winrate NUMERIC,
    jug_games INTEGER,

    mid_mmr NUMERIC,
    mid_winrate NUMERIC,
    mid_games INTEGER,

    adc_mmr NUMERIC,
    adc_winrate NUMERIC,
    adc_games INTEGER,

    sup_mmr NUMERIC,
    sup_winrate NUMERIC,
    sup_games INTEGER,

    calculated_at TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP
);

CREATE INDEX idx_mmr_user_summary_player_code
    ON mmr_user_summary (player_code);

CREATE INDEX idx_mmr_user_summary_total_mmr
    ON mmr_user_summary (total_mmr DESC);

CREATE INDEX idx_mmr_user_summary_calculated_at
    ON mmr_user_summary (calculated_at);
