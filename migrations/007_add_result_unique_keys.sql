-- 결과·요약 테이블의 멱등 저장 키를 DB 제약으로 고정한다.
-- 경기 결과: 길드·경기·실제 참가 계정당 1행, 유저 요약: 길드·MMR 귀속 계정당 1행.
-- 고유 인덱스 생성 전에 중복 행이 있으면 가장 최근 행(id 최대)만 남긴다.
BEGIN;

DELETE FROM mmr_match_results older
USING mmr_match_results newer
WHERE older.guild_id = newer.guild_id
  AND older.replay_code = newer.replay_code
  AND older.player_code = newer.player_code
  AND older.id < newer.id;

ALTER TABLE mmr_match_results ALTER COLUMN guild_id SET NOT NULL;
ALTER TABLE mmr_user_summary ALTER COLUMN guild_id SET NOT NULL;

CREATE UNIQUE INDEX IF NOT EXISTS uq_mmr_match_results_game_player
    ON mmr_match_results (guild_id, replay_code, player_code);

-- 008 적용 후(요약에 season이 있으면) 요약 키는 (guild_id, player_code, season)이다.
-- 이때 다시 실행돼도 다른 시즌 요약을 지우거나 옛 고유 인덱스를 만들지 않는다.
DO $$
BEGIN
    IF NOT EXISTS (
        SELECT 1
        FROM information_schema.columns
        WHERE table_schema = current_schema()
          AND table_name = 'mmr_user_summary'
          AND column_name = 'season'
    ) THEN
        DELETE FROM mmr_user_summary older
        USING mmr_user_summary newer
        WHERE older.guild_id = newer.guild_id
          AND older.player_code = newer.player_code
          AND older.id < newer.id;

        CREATE UNIQUE INDEX IF NOT EXISTS uq_mmr_user_summary_guild_player
            ON mmr_user_summary (guild_id, player_code);
    END IF;
END
$$;

COMMIT;
