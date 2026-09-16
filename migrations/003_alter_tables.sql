-- 결과 테이블에 guild_id 추가
-- puuid 제거 player_code로 대체
-- 배경:
--   baseline 은 전역으로 계산하되 MMR 계산은 길드별 격리로 돌린다.
--   길드별 결과를 한 테이블에 저장하되 어느 길드 결과인지 구분할 수 있도록
--   guild_id 컬럼을 추가한다. (전역 1회 실행 시 user_summary 의 guild_id 는 NULL)

ALTER TABLE mmr_match_results DROP COLUMN puuid;
ALTER TABLE mmr_user_summary DROP COLUMN puuid;

ALTER TABLE mmr_match_results ADD COLUMN player_code VARCHAR(64) NOT NULL;
ALTER TABLE mmr_user_summary ADD COLUMN player_code VARCHAR(64) NOT NULL;

ALTER TABLE mmr_match_results ADD COLUMN guild_id VARCHAR(128);
ALTER TABLE mmr_user_summary ADD COLUMN guild_id VARCHAR(128);

CREATE INDEX idx_mmr_match_results_guild_id ON mmr_match_results (guild_id);
CREATE INDEX idx_mmr_user_summary_guild_id ON mmr_user_summary (guild_id);

CREATE INDEX idx_mmr_user_summary_player_code
  ON mmr_user_summary (player_code);

CREATE INDEX idx_mmr_match_results_player_code_position
  ON mmr_match_results (player_code, position);


