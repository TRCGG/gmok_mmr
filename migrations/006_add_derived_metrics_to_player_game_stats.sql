-- player_game_stats / player_game_stats_old 에 파생지표 컬럼 추가 및 적재
--
-- features.py `add_basic_features` 의 파생 feature 계산을 SQL로 옮긴 것이다.
-- 003/004 의 raw 적재는 그대로 두고, 여기서 파생지표 컬럼을 ALTER 추가 후 UPDATE 채운다.
--
-- 단위/안전 처리 (silver.py `clean_match_data` + features.py 와 동일):
--   - game_duration 은 DB에 초 단위로 저장됨 → 분 = ROUND(game_duration / 60.0, 2)
--     (clean_match_data 가 계산 전 초→분, 소수 2자리 반올림하는 것과 일치)
--   - deaths 0 → 1 로 치환 후 분모 사용 (0데스 방지)
--   - 분모 0/NULL, inf/NaN 결과는 0 으로 채움 (features.py 의 inf→NaN→fillna(0) 와 동일)
--
-- 파생지표 → features.py 매핑:
--   gold_per_min              = gold / 분
--   dpm                       = damage_to_champions / 분
--   damage_taken_per_min      = damage_taken / 분
--   cc_time_per_min           = cc_time / 분
--   exp_per_min               = exp / 분
--   damage_to_turrets_per_min = damage_to_turrets / 분
--   cs_per_min                = (minions_killed + neutral_minions_killed) / 분
--   wards_placed_per_min      = wards_placed / 분
--   wards_killed_per_min      = wards_killed / 분
--   kda                       = (kills + assists) / deaths_safe
--   damage_taken_per_death    = damage_taken / deaths_safe
--   damage_dealt_per_death    = damage_to_champions / deaths_safe
--   dead_time_pct             = time_spent_dead / (분 * 60) * 100
--   lane_gold_diff            = gold - 같은 (replay_code, position) 상대 평균 gold

-- ============================================================
-- 1. 컬럼 추가 (두 테이블 동일)
-- ============================================================
ALTER TABLE player_game_stats_old
    ADD COLUMN IF NOT EXISTS gold_per_min              NUMERIC,
    ADD COLUMN IF NOT EXISTS dpm                       NUMERIC,
    ADD COLUMN IF NOT EXISTS damage_taken_per_min      NUMERIC,
    ADD COLUMN IF NOT EXISTS cc_time_per_min           NUMERIC,
    ADD COLUMN IF NOT EXISTS exp_per_min               NUMERIC,
    ADD COLUMN IF NOT EXISTS damage_to_turrets_per_min NUMERIC,
    ADD COLUMN IF NOT EXISTS cs_per_min                NUMERIC,
    ADD COLUMN IF NOT EXISTS wards_placed_per_min      NUMERIC,
    ADD COLUMN IF NOT EXISTS wards_killed_per_min      NUMERIC,
    ADD COLUMN IF NOT EXISTS kda                       NUMERIC,
    ADD COLUMN IF NOT EXISTS damage_taken_per_death    NUMERIC,
    ADD COLUMN IF NOT EXISTS damage_dealt_per_death    NUMERIC,
    ADD COLUMN IF NOT EXISTS dead_time_pct             NUMERIC,
    ADD COLUMN IF NOT EXISTS lane_gold_diff            NUMERIC;

ALTER TABLE player_game_stats
    ADD COLUMN IF NOT EXISTS gold_per_min              NUMERIC,
    ADD COLUMN IF NOT EXISTS dpm                       NUMERIC,
    ADD COLUMN IF NOT EXISTS damage_taken_per_min      NUMERIC,
    ADD COLUMN IF NOT EXISTS cc_time_per_min           NUMERIC,
    ADD COLUMN IF NOT EXISTS exp_per_min               NUMERIC,
    ADD COLUMN IF NOT EXISTS damage_to_turrets_per_min NUMERIC,
    ADD COLUMN IF NOT EXISTS cs_per_min                NUMERIC,
    ADD COLUMN IF NOT EXISTS wards_placed_per_min      NUMERIC,
    ADD COLUMN IF NOT EXISTS wards_killed_per_min      NUMERIC,
    ADD COLUMN IF NOT EXISTS kda                       NUMERIC,
    ADD COLUMN IF NOT EXISTS damage_taken_per_death    NUMERIC,
    ADD COLUMN IF NOT EXISTS damage_dealt_per_death    NUMERIC,
    ADD COLUMN IF NOT EXISTS dead_time_pct             NUMERIC,
    ADD COLUMN IF NOT EXISTS lane_gold_diff            NUMERIC;

-- ============================================================
-- 2. player_game_stats_old 파생지표 적재
-- ============================================================
WITH derived AS (
    SELECT
        id,
        ROUND(game_duration / 60.0, 2)                          AS dur_min,
        CASE WHEN deaths = 0 THEN 1 ELSE deaths END             AS deaths_safe,
        SUM(gold_earned) OVER (PARTITION BY replay_code, position) - gold_earned AS opp_gold_sum,
        COUNT(*)         OVER (PARTITION BY replay_code, position) - 1           AS opp_cnt
    FROM player_game_stats_old
)
UPDATE player_game_stats_old pg SET
    gold_per_min              = COALESCE(pg.gold_earned::numeric            / NULLIF(d.dur_min, 0), 0),
    dpm                       = COALESCE(pg.damage_to_champions::numeric    / NULLIF(d.dur_min, 0), 0),
    damage_taken_per_min      = COALESCE(pg.damage_taken::numeric           / NULLIF(d.dur_min, 0), 0),
    cc_time_per_min           = COALESCE(pg.cc_time::numeric                / NULLIF(d.dur_min, 0), 0),
    exp_per_min               = COALESCE(pg.exp::numeric                    / NULLIF(d.dur_min, 0), 0),
    damage_to_turrets_per_min = COALESCE(pg.damage_to_turrets::numeric      / NULLIF(d.dur_min, 0), 0),
    cs_per_min                = COALESCE((pg.minions_killed + pg.neutral_minions_killed)::numeric / NULLIF(d.dur_min, 0), 0),
    wards_placed_per_min      = COALESCE(pg.wards_placed::numeric           / NULLIF(d.dur_min, 0), 0),
    wards_killed_per_min      = COALESCE(pg.wards_killed::numeric           / NULLIF(d.dur_min, 0), 0),
    kda                       = COALESCE((pg.kills + pg.assists)::numeric   / NULLIF(d.deaths_safe, 0), 0),
    damage_taken_per_death    = COALESCE(pg.damage_taken::numeric           / NULLIF(d.deaths_safe, 0), 0),
    damage_dealt_per_death    = COALESCE(pg.damage_to_champions::numeric    / NULLIF(d.deaths_safe, 0), 0),
    dead_time_pct             = COALESCE(pg.time_spent_dead::numeric        / NULLIF(d.dur_min * 60, 0) * 100, 0),
    lane_gold_diff            = COALESCE(pg.gold_earned::numeric - (d.opp_gold_sum::numeric / NULLIF(d.opp_cnt, 0)), 0)
FROM derived d
WHERE pg.id = d.id;

-- ============================================================
-- 3. player_game_stats (신포맷) 파생지표 적재
-- ============================================================
WITH derived AS (
    SELECT
        id,
        ROUND(game_duration / 60.0, 2)                          AS dur_min,
        CASE WHEN deaths = 0 THEN 1 ELSE deaths END             AS deaths_safe,
        SUM(gold_earned) OVER (PARTITION BY replay_code, position) - gold_earned AS opp_gold_sum,
        COUNT(*)         OVER (PARTITION BY replay_code, position) - 1           AS opp_cnt
    FROM player_game_stats
)
UPDATE player_game_stats pg SET
    gold_per_min              = COALESCE(pg.gold_earned::numeric            / NULLIF(d.dur_min, 0), 0),
    dpm                       = COALESCE(pg.damage_to_champions::numeric    / NULLIF(d.dur_min, 0), 0),
    damage_taken_per_min      = COALESCE(pg.damage_taken::numeric           / NULLIF(d.dur_min, 0), 0),
    cc_time_per_min           = COALESCE(pg.cc_time::numeric                / NULLIF(d.dur_min, 0), 0),
    exp_per_min               = COALESCE(pg.exp::numeric                    / NULLIF(d.dur_min, 0), 0),
    damage_to_turrets_per_min = COALESCE(pg.damage_to_turrets::numeric      / NULLIF(d.dur_min, 0), 0),
    cs_per_min                = COALESCE((pg.minions_killed + pg.neutral_minions_killed)::numeric / NULLIF(d.dur_min, 0), 0),
    wards_placed_per_min      = COALESCE(pg.wards_placed::numeric           / NULLIF(d.dur_min, 0), 0),
    wards_killed_per_min      = COALESCE(pg.wards_killed::numeric           / NULLIF(d.dur_min, 0), 0),
    kda                       = COALESCE((pg.kills + pg.assists)::numeric   / NULLIF(d.deaths_safe, 0), 0),
    damage_taken_per_death    = COALESCE(pg.damage_taken::numeric           / NULLIF(d.deaths_safe, 0), 0),
    damage_dealt_per_death    = COALESCE(pg.damage_to_champions::numeric    / NULLIF(d.deaths_safe, 0), 0),
    dead_time_pct             = COALESCE(pg.time_spent_dead::numeric        / NULLIF(d.dur_min * 60, 0) * 100, 0),
    lane_gold_diff            = COALESCE(pg.gold_earned::numeric - (d.opp_gold_sum::numeric / NULLIF(d.opp_cnt, 0)), 0)
FROM derived d
WHERE pg.id = d.id;
