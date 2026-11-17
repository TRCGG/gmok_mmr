-- MMR 리포트·고유 키·시즌·baseline 기록 (이전 006~009를 하나로 합침, 스키마만 변경)
--
-- 1) 유저 요약에 포지션별 리포트(position_report) 추가
-- 2) 경기 결과 고유 키 (guild_id, replay_code, player_code)
-- 3) 결과·요약에 season 추가(그 경기의 custom_match.season), 요약 고유 키 (guild_id, player_code, season)
-- 4) 결과 행에 계산에 쓴 baseline(baseline_season, baseline_version) 기록
-- 5) mmr_player_account 삭제: 부캐 매핑을 없애 항상 player_code와 같아진 컬럼이다.
--    계정 키는 player_code 하나다(005에서 추가했던 컬럼·인덱스를 함께 지운다).
--
-- 전제: mmr_player_account 컬럼 삭제 외에는 기존 데이터를 고치지 않는다.
-- mmr_match_results·mmr_user_summary를 비운 뒤(과거 기록 1회 계산 전) 실행한다. 데이터가 남아 있으면 season NOT NULL·고유 인덱스 단계에서 실패하고
-- 전체가 롤백된다. 이전 006~008을 이미 적용한 DB에서는 다시 실행해도 안전하며, 남은 변경
-- (baseline 기록 컬럼 추가, mmr_player_account 삭제)만 반영된다.
--
-- 운영: 예전 방식(부캐→본캐 귀속)으로 계산된 결과가 남아 있으면 컬럼 삭제 뒤에는 구분할 수
-- 없으므로, 006 적용 직후 전체 범위로 다시 계산한다(MMR_SEASON·MMR_GUILD_ID 비움,
-- MMR_ALLOW_RECALCULATE=1). 트랜잭션 동안 두 테이블 읽기·쓰기가 막히니 트래픽이 없을 때 실행한다.
BEGIN;

-- ---------------------------------------------------------------------------
-- 1) position_report
-- ---------------------------------------------------------------------------
ALTER TABLE mmr_user_summary
    ADD COLUMN IF NOT EXISTS position_report JSONB NOT NULL DEFAULT '{}'::jsonb;

-- 이전 006 초안을 적용한 DB에서 조회 패턴에 맞지 않는 GIN 인덱스를 제거한다.
DROP INDEX IF EXISTS idx_mmr_user_summary_position_report;

-- mmr_player_account와 이 컬럼에 걸린 인덱스(idx_mmr_match_results_mmr_player_account,
-- 이전 버전의 idx_mmr_match_results_history_lookup)를 지운다. 인덱스는 컬럼과 함께 지워진다.
ALTER TABLE mmr_match_results DROP COLUMN IF EXISTS mmr_player_account;

-- 경기별 MMR 이력(그래프) 조회용
CREATE INDEX IF NOT EXISTS idx_mmr_match_results_history_lookup
    ON mmr_match_results (guild_id, player_code, position, played_at);

-- ---------------------------------------------------------------------------
-- 2) 경기 결과 고유 키: 길드·경기·실제 참가 계정당 1행
-- ---------------------------------------------------------------------------
ALTER TABLE mmr_match_results ALTER COLUMN guild_id SET NOT NULL;
ALTER TABLE mmr_user_summary ALTER COLUMN guild_id SET NOT NULL;

CREATE UNIQUE INDEX IF NOT EXISTS uq_mmr_match_results_game_player
    ON mmr_match_results (guild_id, replay_code, player_code);

-- ---------------------------------------------------------------------------
-- 3) 시즌: 계산 시점이 아니라 그 경기의 custom_match.season을 따른다.
--    유저 요약은 길드·선수·시즌별 1행이고, 시즌마다 MMR을 1300부터 다시 계산한다.
-- ---------------------------------------------------------------------------
ALTER TABLE mmr_match_results ADD COLUMN IF NOT EXISTS season VARCHAR(64) NOT NULL;
ALTER TABLE mmr_user_summary ADD COLUMN IF NOT EXISTS season VARCHAR(64) NOT NULL;
-- 컬럼이 이미 NULL 허용으로 있던 DB도 NOT NULL로 맞춘다.
ALTER TABLE mmr_match_results ALTER COLUMN season SET NOT NULL;
ALTER TABLE mmr_user_summary ALTER COLUMN season SET NOT NULL;

-- 시즌 이전의 요약 키가 남아 있으면 지운다(시즌별 행을 둘 수 없게 막는다).
DROP INDEX IF EXISTS uq_mmr_user_summary_guild_player;
CREATE UNIQUE INDEX IF NOT EXISTS uq_mmr_user_summary_guild_player_season
    ON mmr_user_summary (guild_id, player_code, season);

CREATE INDEX IF NOT EXISTS idx_mmr_match_results_guild_season
    ON mmr_match_results (guild_id, season);

-- ---------------------------------------------------------------------------
-- 4) 결과 행마다 계산에 쓴 baseline을 기록한다.
--    새 시즌 초반에는 가장 최근 저장된 baseline을, 새 baseline 저장 후에는 새 baseline을
--    쓰므로 같은 시즌 안에서도 행마다 다를 수 있다. baseline_season은 baseline이 만들어진
--    시즌이라 결과의 season과 다를 수 있다. 이전 006~008만 적용된 DB의 기존 행은 NULL로
--    남고, 전체 재계산 시 채워진다.
-- ---------------------------------------------------------------------------
ALTER TABLE mmr_match_results ADD COLUMN IF NOT EXISTS baseline_season VARCHAR(64);
ALTER TABLE mmr_match_results ADD COLUMN IF NOT EXISTS baseline_version VARCHAR(64);

COMMIT;
