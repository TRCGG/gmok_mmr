-- 기존 유저 요약에 포지션별 리포트 결과를 통합한다.
-- 경기별 MMR 이력은 기존 mmr_match_results를 사용한다.
BEGIN;

ALTER TABLE mmr_user_summary
    ADD COLUMN IF NOT EXISTS position_report JSONB NOT NULL DEFAULT '{}'::jsonb;

-- 이전 006 초안을 적용한 DB에서 조회 패턴에 맞지 않는 GIN 인덱스를 제거한다.
DROP INDEX IF EXISTS idx_mmr_user_summary_position_report;

CREATE INDEX IF NOT EXISTS idx_mmr_match_results_history_lookup
    ON mmr_match_results (guild_id, mmr_player_account, position, played_at);

COMMIT;
