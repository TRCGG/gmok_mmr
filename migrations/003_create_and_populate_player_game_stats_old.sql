-- player_game_stats_old 테이블 생성 및 league raw_data 파싱 적재
--
-- league 테이블의 JSONB raw_data 배열을 플레이어별 row로 펼쳐서 적재한다.
-- repository.py SELECT 컬럼 구조에 맞게 매핑되어 있다.
--
-- JSON 키 → 컬럼 주요 매핑
--   CHAMPIONS_KILLED               → kills
--   NUM_DEATHS                     → deaths
--   TIME_CCING_OTHERS              → cc_time
--   TIME_PLAYED                    → game_duration  (초 단위)
--   TOTAL_DAMAGE_DEALT_TO_CHAMPIONS→ damage_to_champions
--   TOTAL_DAMAGE_DEALT_TO_BUILDINGS→ damage_to_turrets
--   TOTAL_DAMAGE_DEALT_TO_OBJECTIVES→ damage_to_objectives
--   TOTAL_DAMAGE_SELF_MITIGATED    → damage_self_mitigated
--   WARD_PLACED                    → wards_placed
--   WARD_KILLED                    → wards_killed
--   WARD_PLACED_DETECTOR           → detector_wards_placed
--   VISION_WARDS_BOUGHT_IN_GAME    → control_wards_bought
--   RIFT_HERALD_KILLS              → herald_kills
--   NEUTRAL_MINIONS_KILLED_YOUR_JUNGLE → jungle_cs_own
--   NEUTRAL_MINIONS_KILLED_ENEMY_JUNGLE→ jungle_cs_enemy
--   TOTAL_HEAL_ON_TEAMMATES        → heal_on_teammates
--   TOTAL_DAMAGE_SHIELDED_ON_TEAMMATES→ shield_on_teammates
--   Missions_TurretPlatesDestroyed → turret_plates_destroyed
--   Missions_TakedownsUnderTurret  → takedowns_under_turret
--   Missions_TakedownsBefore15Min  → takedowns_before_15min
--   damage_to_epic_monsters        → NULL (raw_data에 대응 필드 없음)

CREATE TABLE IF NOT EXISTS player_game_stats_old (
    id                              BIGSERIAL    PRIMARY KEY,
    replay_code                     VARCHAR(128) NOT NULL,
    puuid                           VARCHAR(64)  NOT NULL,
    guild_id                        VARCHAR(64),
    champion_id                     VARCHAR(16),
    team                            VARCHAR(8),
    position                        VARCHAR(16),
    win                             BOOLEAN,
    kills                           INTEGER,
    deaths                          INTEGER,
    assists                         INTEGER,
    double_kills                    INTEGER,
    triple_kills                    INTEGER,
    quadra_kills                    INTEGER,
    penta_kills                     INTEGER,
    killing_sprees                  INTEGER,
    largest_killing_spree           INTEGER,
    gold_earned                     INTEGER,
    cc_time                         INTEGER,
    game_duration                   INTEGER,
    damage_to_champions             INTEGER,
    damage_taken                    INTEGER,
    damage_self_mitigated           INTEGER,
    vision_score                    INTEGER,
    wards_placed                    INTEGER,
    wards_killed                    INTEGER,
    detector_wards_placed           INTEGER,
    control_wards_bought            INTEGER,
    minions_killed                  INTEGER,
    neutral_minions_killed          INTEGER,
    time_spent_dead                 INTEGER,
    longest_time_living             INTEGER,
    damage_to_turrets               INTEGER,
    damage_to_objectives            INTEGER,
    dragon_kills                    INTEGER,
    baron_kills                     INTEGER,
    herald_kills                    INTEGER,
    horde_kills                     INTEGER,
    last_takedown_time              INTEGER,
    turrets_killed                  INTEGER,
    turret_takedowns                INTEGER,
    level                           INTEGER,
    exp                             INTEGER,
    turret_plates_destroyed         INTEGER,
    takedowns_under_turret          INTEGER,
    takedowns_before_15min          INTEGER,
    jungle_cs_own                   INTEGER,
    jungle_cs_enemy                 INTEGER,
    damage_to_epic_monsters         INTEGER,
    objectives_stolen               INTEGER,
    barracks_killed                 INTEGER,
    heal_on_teammates               INTEGER,
    shield_on_teammates             INTEGER,
    enemy_missing_pings             INTEGER,
    retreat_pings                   INTEGER,
    on_my_way_pings                 INTEGER,
    command_pings                   INTEGER,
    played_at                       TIMESTAMP,
    created_at                      TIMESTAMP    DEFAULT CURRENT_TIMESTAMP
);

CREATE INDEX IF NOT EXISTS idx_pgs_old_replay_code
    ON player_game_stats_old (replay_code);

CREATE INDEX IF NOT EXISTS idx_pgs_old_puuid
    ON player_game_stats_old (puuid);

CREATE INDEX IF NOT EXISTS idx_pgs_old_guild_id
    ON player_game_stats_old (guild_id);


INSERT INTO player_game_stats_old (
    replay_code,
    puuid,
    guild_id,
    champion_id,
    team,
    position,
    win,
    kills,
    deaths,
    assists,
    double_kills,
    triple_kills,
    quadra_kills,
    penta_kills,
    killing_sprees,
    largest_killing_spree,
    gold_earned,
    cc_time,
    game_duration,
    damage_to_champions,
    damage_taken,
    damage_self_mitigated,
    vision_score,
    wards_placed,
    wards_killed,
    detector_wards_placed,
    control_wards_bought,
    minions_killed,
    neutral_minions_killed,
    time_spent_dead,
    longest_time_living,
    damage_to_turrets,
    damage_to_objectives,
    dragon_kills,
    baron_kills,
    herald_kills,
    horde_kills,
    last_takedown_time,
    turrets_killed,
    turret_takedowns,
    level,
    exp,
    turret_plates_destroyed,
    takedowns_under_turret,
    takedowns_before_15min,
    jungle_cs_own,
    jungle_cs_enemy,
    damage_to_epic_monsters,
    objectives_stolen,
    barracks_killed,
    heal_on_teammates,
    shield_on_teammates,
    enemy_missing_pings,
    retreat_pings,
    on_my_way_pings,
    command_pings,
    played_at,
    created_at
)
SELECT
    l.game_id::VARCHAR                                                          AS replay_code,
    d.raw_data->>'PUUID'                                                        AS puuid,
    l.guild_id                                                                  AS guild_id,
    c.id                                                                        AS champion_id,
    d.raw_data->>'TEAM'                                                         AS team,
    d.raw_data->>'TEAM_POSITION'                                                AS position,
    CASE WHEN d.raw_data->>'WIN' = 'Win' THEN TRUE ELSE FALSE END               AS win,
    (d.raw_data->>'CHAMPIONS_KILLED')::INTEGER                                  AS kills,
    (d.raw_data->>'NUM_DEATHS')::INTEGER                                        AS deaths,
    (d.raw_data->>'ASSISTS')::INTEGER                                           AS assists,
    (d.raw_data->>'DOUBLE_KILLS')::INTEGER                                      AS double_kills,
    (d.raw_data->>'TRIPLE_KILLS')::INTEGER                                      AS triple_kills,
    (d.raw_data->>'QUADRA_KILLS')::INTEGER                                      AS quadra_kills,
    (d.raw_data->>'PENTA_KILLS')::INTEGER                                       AS penta_kills,
    (d.raw_data->>'KILLING_SPREES')::INTEGER                                    AS killing_sprees,
    (d.raw_data->>'LARGEST_KILLING_SPREE')::INTEGER                             AS largest_killing_spree,
    (d.raw_data->>'GOLD_EARNED')::INTEGER                                       AS gold_earned,
    (d.raw_data->>'TIME_CCING_OTHERS')::INTEGER                                 AS cc_time,
    (d.raw_data->>'TIME_PLAYED')::INTEGER                                       AS game_duration,
    (d.raw_data->>'TOTAL_DAMAGE_DEALT_TO_CHAMPIONS')::INTEGER                   AS damage_to_champions,
    (d.raw_data->>'TOTAL_DAMAGE_TAKEN')::INTEGER                                AS damage_taken,
    (d.raw_data->>'TOTAL_DAMAGE_SELF_MITIGATED')::INTEGER                       AS damage_self_mitigated,
    (d.raw_data->>'VISION_SCORE')::INTEGER                                      AS vision_score,
    (d.raw_data->>'WARD_PLACED')::INTEGER                                       AS wards_placed,
    (d.raw_data->>'WARD_KILLED')::INTEGER                                       AS wards_killed,
    (d.raw_data->>'WARD_PLACED_DETECTOR')::INTEGER                              AS detector_wards_placed,
    (d.raw_data->>'VISION_WARDS_BOUGHT_IN_GAME')::INTEGER                       AS control_wards_bought,
    (d.raw_data->>'MINIONS_KILLED')::INTEGER                                    AS minions_killed,
    (d.raw_data->>'NEUTRAL_MINIONS_KILLED')::INTEGER                            AS neutral_minions_killed,
    (d.raw_data->>'TOTAL_TIME_SPENT_DEAD')::INTEGER                             AS time_spent_dead,
    (d.raw_data->>'LONGEST_TIME_SPENT_LIVING')::INTEGER                         AS longest_time_living,
    (d.raw_data->>'TOTAL_DAMAGE_DEALT_TO_BUILDINGS')::INTEGER                   AS damage_to_turrets,
    (d.raw_data->>'TOTAL_DAMAGE_DEALT_TO_OBJECTIVES')::INTEGER                  AS damage_to_objectives,
    (d.raw_data->>'DRAGON_KILLS')::INTEGER                                      AS dragon_kills,
    (d.raw_data->>'BARON_KILLS')::INTEGER                                       AS baron_kills,
    (d.raw_data->>'RIFT_HERALD_KILLS')::INTEGER                                 AS herald_kills,
    (d.raw_data->>'HORDE_KILLS')::INTEGER                                       AS horde_kills,
    (d.raw_data->>'LAST_TAKEDOWN_TIME')::INTEGER                                AS last_takedown_time,
    (d.raw_data->>'TURRETS_KILLED')::INTEGER                                    AS turrets_killed,
    (d.raw_data->>'TURRET_TAKEDOWNS')::INTEGER                                  AS turret_takedowns,
    (d.raw_data->>'LEVEL')::INTEGER                                             AS level,
    (d.raw_data->>'EXP')::INTEGER                                               AS exp,
    (d.raw_data->>'Missions_TurretPlatesDestroyed')::INTEGER                    AS turret_plates_destroyed,
    (d.raw_data->>'Missions_TakedownsUnderTurret')::INTEGER                     AS takedowns_under_turret,
    (d.raw_data->>'Missions_TakedownsBefore15Min')::INTEGER                     AS takedowns_before_15min,
    (d.raw_data->>'NEUTRAL_MINIONS_KILLED_YOUR_JUNGLE')::INTEGER                AS jungle_cs_own,
    (d.raw_data->>'NEUTRAL_MINIONS_KILLED_ENEMY_JUNGLE')::INTEGER               AS jungle_cs_enemy,
    NULL::INTEGER                                                               AS damage_to_epic_monsters,
    (d.raw_data->>'OBJECTIVES_STOLEN')::INTEGER                                 AS objectives_stolen,
    (d.raw_data->>'BARRACKS_KILLED')::INTEGER                                   AS barracks_killed,
    (d.raw_data->>'TOTAL_HEAL_ON_TEAMMATES')::INTEGER                           AS heal_on_teammates,
    (d.raw_data->>'TOTAL_DAMAGE_SHIELDED_ON_TEAMMATES')::INTEGER                AS shield_on_teammates,
    (d.raw_data->>'ENEMY_MISSING_PINGS')::INTEGER                               AS enemy_missing_pings,
    (d.raw_data->>'RETREAT_PINGS')::INTEGER                                     AS retreat_pings,
    (d.raw_data->>'ON_MY_WAY_PINGS')::INTEGER                                   AS on_my_way_pings,
    (d.raw_data->>'COMMAND_PINGS')::INTEGER                                     AS command_pings,
    l.game_date::TIMESTAMP                                                      AS played_at,
    l.create_date                                                               AS created_at
FROM league l
CROSS JOIN LATERAL jsonb_array_elements(l.raw_data) AS d(raw_data)
LEFT JOIN Champion c
    ON LOWER(TRIM(d.raw_data->>'SKIN')) = LOWER(TRIM(c.champ_name_eng))
WHERE NOT (d.raw_data ? 'TOTAL_DAMAGE_DEALT_TO_EPIC_MONSTERS')
  AND d.raw_data->>'TEAM_POSITION' IN ('TOP', 'JUNGLE', 'MIDDLE', 'BOTTOM', 'UTILITY');
