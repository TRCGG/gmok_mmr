-- 경기별 실제 참가 계정(player_code)과 MMR 귀속 본캐를 함께 보존한다.
-- 기존 계산 결과는 원본 경기와 현재 계정 관계로 재계산해야 한다.
ALTER TABLE mmr_match_results
    ADD COLUMN IF NOT EXISTS mmr_player_account VARCHAR(64);

CREATE INDEX IF NOT EXISTS idx_mmr_match_results_mmr_player_account
    ON mmr_match_results (guild_id, mmr_player_account);
