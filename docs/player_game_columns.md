# player_game 컬럼 사용 현황

`db_test/repository.py`에서 `player_game` 테이블 전체를 SELECT 하고 있다.
이 문서는 각 컬럼이 MMR 계산 파이프라인에서 실제로 사용되는지 여부를 정리한다.

---

## 사용 중인 컬럼 (27개)

### 식별 / 메타
| 컬럼 (DataFrame) | 원천 DB 컬럼 | 사용처 |
|-----------------|------------|--------|
| `replay_code` | `replay_code` | 경기 그룹핑, 정렬, 상대 비교 |
| `puuid` | `puuid` | 플레이어 식별 |
| `guild_id` | `guild_id` | 스크립트 필터링 |
| `champion_id` | `champion_id` | 결과 테이블 저장 |
| `team` | `team` | 결과 테이블 저장 |
| `position` | `position` | 포지션별 가중치 계산, 그룹핑 |
| `win` | `win` | → `game_result` 변환 후 승패 판정 |
| `played_at` | `played_at` | 시간순 정렬 (ELO 누적 순서) |

### 전투
| 컬럼 (DataFrame) | 원천 DB 컬럼 | 사용처 |
|-----------------|------------|--------|
| `kills` | `kills` | KDA, BASE_METRIC |
| `deaths` | `deaths` | KDA, 피해/처치당 지표, BASE_METRIC |
| `assists` | `assists` | KDA, BASE_METRIC |
| `penta_kills` | `penta_kills` | 결과 테이블 저장 |

### 골드 / 자원
| 컬럼 (DataFrame) | 원천 DB 컬럼 | 사용처 |
|-----------------|------------|--------|
| `gold` | `gold_earned` | gold_per_min, lane_gold_diff, BASE_METRIC |
| `minions_killed` | `minions_killed` | cs_per_min, BASE_METRIC |
| `neutral_minions_killed` | `neutral_minions_killed` | cs_per_min, BASE_METRIC |
| `exp` | `exp` | exp_per_min, BASE_METRIC |

### 딜량 / 피해
| 컬럼 (DataFrame) | 원천 DB 컬럼 | 사용처 |
|-----------------|------------|--------|
| `damage_to_champions` | `damage_to_champions` | dpm, damage_dealt_per_death, BASE_METRIC |
| `damage_taken` | `damage_taken` | damage_taken_per_min, damage_taken_per_death, BASE_METRIC |
| `damage_to_turrets` | `damage_to_turrets` | damage_to_turrets_per_min, BASE_METRIC |
| `cc_time` | `cc_time` | cc_time_per_min, BASE_METRIC |

### 시야
| 컬럼 (DataFrame) | 원천 DB 컬럼 | 사용처 |
|-----------------|------------|--------|
| `vision_score` | `vision_score` | BASE_METRIC (직접 사용) |
| `wards_placed` | `wards_placed` | wards_placed_per_min, BASE_METRIC |
| `wards_killed` | `wards_killed` | wards_killed_per_min, BASE_METRIC |
| `vision_bought` | `control_wards_bought` | 결과 테이블 저장 |

### 팀 기여
| 컬럼 (DataFrame) | 원천 DB 컬럼 | 사용처 |
|-----------------|------------|--------|
| `heal_on_teammates` | `heal_on_teammates` | BASE_METRIC (직접 사용) |
| `shield_on_teammates` | `shield_on_teammates` | BASE_METRIC (직접 사용) |

### 경기 정보
| 컬럼 (DataFrame) | 원천 DB 컬럼 | 사용처 |
|-----------------|------------|--------|
| `game_duration` | `game_duration` | 모든 per_min 지표의 분모 |

---

## 미사용 컬럼 (30개)

현재 MMR 계산 파이프라인 어디서도 참조하지 않는 컬럼.
나중에 계산 로직이 확장되면 추가 검토한다.

| 컬럼 (DataFrame) | 원천 DB 컬럼 | 비고 |
|-----------------|------------|------|
| `player_game_id` | `id` | `_stamp()`에서 명시적 drop, 결과 테이블에 없음 |
| `double_kills` | `double_kills` | |
| `triple_kills` | `triple_kills` | |
| `quadra_kills` | `quadra_kills` | |
| `killing_sprees` | `killing_sprees` | |
| `largest_killing_spree` | `largest_killing_spree` | |
| `damage_self_mitigated` | `damage_self_mitigated` | |
| `detector_wards_placed` | `detector_wards_placed` | |
| `time_spent_dead` | `time_spent_dead` | `dead_time_pct` 파생만 됨, BASE_METRIC 아님 |
| `longest_time_living` | `longest_time_living` | |
| `damage_to_objectives` | `damage_to_objectives` | |
| `dragon_kills` | `dragon_kills` | silver NA 제외 목록에만 등재 |
| `baron_kills` | `baron_kills` | silver NA 제외 목록에만 등재 |
| `herald_kills` | `herald_kills` | silver NA 제외 목록에만 등재 |
| `horde_kills` | `horde_kills` | silver NA 제외 목록에만 등재 |
| `last_takedown_time` | `last_takedown_time` | |
| `turrets_killed` | `turrets_killed` | |
| `turret_takedowns` | `turret_takedowns` | |
| `level` | `level` | |
| `turret_plates_destroyed` | `turret_plates_destroyed` | |
| `takedowns_under_turret` | `takedowns_under_turret` | |
| `takedowns_before_15min` | `takedowns_before_15min` | |
| `jungle_cs_own` | `jungle_cs_own` | silver NA 제외 목록에만 등재 |
| `jungle_cs_enemy` | `jungle_cs_enemy` | silver NA 제외 목록에만 등재 |
| `damage_to_epic_monsters` | `damage_to_epic_monsters` | silver NA 제외 목록에만 등재 |
| `objectives_stolen` | `objectives_stolen` | silver NA 제외 목록에만 등재 |
| `barracks_killed` | `barracks_killed` | silver NA 제외 목록에만 등재 |
| `enemy_missing_pings` | `enemy_missing_pings` | |
| `retreat_pings` | `retreat_pings` | |
| `on_my_way_pings` | `on_my_way_pings` | |
| `command_pings` | `command_pings` | |
| `created_at` | `created_at` | |
