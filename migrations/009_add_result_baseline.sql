-- 경기 결과마다 계산에 쓴 baseline을 기록한다.
-- 새 시즌 초반에는 가장 최근 저장된 baseline을, 새 baseline 저장 후에는 새 baseline을 쓰므로
-- 같은 시즌 안에서도 행마다 baseline이 다를 수 있다.
-- baseline_season은 baseline이 만들어진 시즌이며, 결과 행의 season과 다를 수 있다.
-- 이 migration 이전에 계산된 행은 NULL로 남고, 전체 재계산 시 채워진다.
BEGIN;

ALTER TABLE mmr_match_results ADD COLUMN IF NOT EXISTS baseline_season VARCHAR(64);
ALTER TABLE mmr_match_results ADD COLUMN IF NOT EXISTS baseline_version VARCHAR(64);

COMMIT;
