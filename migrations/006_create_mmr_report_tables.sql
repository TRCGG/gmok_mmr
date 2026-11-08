-- 기존 유저 요약에 포지션별 리포트 결과를 통합한다.
-- 경기별 MMR 이력은 기존 mmr_match_results를 사용한다.
BEGIN;

ALTER TABLE mmr_user_summary
    ADD COLUMN IF NOT EXISTS position_report JSONB NOT NULL DEFAULT '{}'::jsonb;

CREATE INDEX IF NOT EXISTS idx_mmr_user_summary_position_report
    ON mmr_user_summary USING GIN (position_report);

CREATE INDEX IF NOT EXISTS idx_mmr_match_results_history_lookup
    ON mmr_match_results (guild_id, mmr_player_account, position, played_at);

COMMIT;
