-- 경기 결과와 유저 요약에 시즌을 추가한다.
-- 시즌 값은 계산 시점이 아니라 그 경기의 custom_match.season을 따른다.
-- 유저 요약은 길드·선수·시즌별 1행이고, 시즌마다 MMR을 초기값부터 다시 계산한다.
BEGIN;

ALTER TABLE mmr_match_results ADD COLUMN IF NOT EXISTS season VARCHAR(64);
ALTER TABLE mmr_user_summary ADD COLUMN IF NOT EXISTS season VARCHAR(64);

UPDATE mmr_match_results m
SET season = cm.season
FROM custom_match cm
WHERE cm.id = m.replay_code
  AND m.season IS NULL;

-- 기존 요약은 해당 길드·선수의 마지막 결과 행 시즌으로 채운다.
UPDATE mmr_user_summary s
SET season = last_game.season
FROM (
    SELECT DISTINCT ON (guild_id, mmr_player_account)
        guild_id, mmr_player_account, season
    FROM mmr_match_results
    ORDER BY guild_id, mmr_player_account, played_at DESC, replay_code DESC
) last_game
WHERE last_game.guild_id = s.guild_id
  AND last_game.mmr_player_account = s.player_code
  AND s.season IS NULL;

-- 채우지 못한 행이 있으면 건수를 알리고 실패해 전체가 롤백된다.
DO $$
DECLARE
    missing_results BIGINT;
    missing_summaries BIGINT;
BEGIN
    SELECT count(*) INTO missing_results FROM mmr_match_results WHERE season IS NULL;
    SELECT count(*) INTO missing_summaries FROM mmr_user_summary WHERE season IS NULL;
    IF missing_results > 0 OR missing_summaries > 0 THEN
        RAISE EXCEPTION
            'season backfill incomplete: mmr_match_results=% rows (no custom_match), mmr_user_summary=% rows (no result rows)',
            missing_results, missing_summaries;
    END IF;
END
$$;

ALTER TABLE mmr_match_results ALTER COLUMN season SET NOT NULL;
ALTER TABLE mmr_user_summary ALTER COLUMN season SET NOT NULL;

DROP INDEX IF EXISTS uq_mmr_user_summary_guild_player;
CREATE UNIQUE INDEX IF NOT EXISTS uq_mmr_user_summary_guild_player_season
    ON mmr_user_summary (guild_id, player_code, season);

CREATE INDEX IF NOT EXISTS idx_mmr_match_results_guild_season
    ON mmr_match_results (guild_id, season);

COMMIT;
