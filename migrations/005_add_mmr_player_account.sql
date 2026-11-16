-- MMR 계정 컬럼(mmr_player_account)을 추가한다.
-- 처음에는 부캐 경기를 본캐에 귀속하려고 만들었으나, 지금은 부캐 매핑을 보지 않아
-- 항상 실제 참가 계정(player_code)과 같은 값을 넣는다(백엔드 계약상 컬럼은 유지).
ALTER TABLE mmr_match_results
    ADD COLUMN IF NOT EXISTS mmr_player_account VARCHAR(64);

CREATE INDEX IF NOT EXISTS idx_mmr_match_results_mmr_player_account
    ON mmr_match_results (guild_id, mmr_player_account);
