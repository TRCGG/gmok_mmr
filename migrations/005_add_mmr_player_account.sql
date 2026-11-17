-- MMR 계정 컬럼(mmr_player_account)을 추가한다.
-- 부캐 경기를 본캐에 귀속하려고 만들었으나 부캐 매핑을 없애면서 006에서 삭제한다.
-- 계정 키는 player_code 하나다.
ALTER TABLE mmr_match_results
    ADD COLUMN IF NOT EXISTS mmr_player_account VARCHAR(64);

CREATE INDEX IF NOT EXISTS idx_mmr_match_results_mmr_player_account
    ON mmr_match_results (guild_id, mmr_player_account);
