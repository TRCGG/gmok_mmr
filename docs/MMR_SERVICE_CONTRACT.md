# MMR Service Contract

## 목적

백엔드와 MMR 계산 서비스가 연동하기 위한 공식 API 계약을 정의한다.

이 문서는 MMR 서비스에 전달할 확정 계약 문서다. MMR 서비스가 받아야 하는 입력 형식, 반환해야 하는 응답 형식, baseline 정책, 책임 범위를 정리한다.

## 확정 원칙

- MMR 계산은 MMR 서비스가 담당한다.
- MMR 계산 결과의 DB 저장은 백엔드가 담당한다.
- 유저 식별자는 `puuid`를 기준으로 한다.
- 부계정 통합은 MMR에서 고려하지 않는다.
- 경기 식별자는 `custom_match_id`를 사용한다.
- `custom_match_id` 1개가 `custom_match` 1개이며 한 경기를 의미한다.
- 포지션은 `TOP`, `JUG`, `MID`, `ADC`, `SUP`를 사용한다.
- 승패는 `game_result`에 `1`, `0`으로 전달한다.
- `1`은 승리, `0`은 패배다.
- 포지션별 MMR summary는 사용하지 않는다.
- baseline은 시즌별로 관리한다.
- baseline은 모든 guild가 공통으로 사용하는 시즌 단위 값이다.
- 시즌별 active baseline은 1개만 유지한다.
- baseline은 매 경기마다 재계산하지 않고, 월 1회 또는 정해진 주기마다 시즌 전체 guild 데이터로 계산한다.
- MMR 결과와 유저 summary는 `guild_id + season` 단위로 관리한다.
- 전체 MMR 계산과 단일 경기 MMR 계산은 백엔드가 전달한 baseline을 사용한다.
- MMR 서비스는 일반 계산 이력인 `mmr_history`를 계산 결과와 함께 반환한다.
- 백엔드는 MMR 서비스가 반환한 `mmr_history`를 저장한다.
- 경기 삭제 보정처럼 백엔드가 직접 보정하는 이력은 백엔드가 `DELETE_ADJUST` history로 생성한다.

## API 목록

| API | Endpoint | 설명 |
| --- | --- | --- |
| Baseline 계산 | `POST /v1/mmr/baselines/calculate` | 시즌 전체 guild 데이터로 공통 baseline 계산 |
| 전체 MMR 계산 | `POST /v1/mmr/recalculate` | 특정 guild/season 전체 MMR 재계산 |
| 단일 경기 MMR 계산 | `POST /v1/mmr/matches/calculate` | 신규 경기 1개 증분 계산 |

## 공통 Enum

| 필드 | 값 |
| --- | --- |
| `position` | `TOP`, `JUG`, `MID`, `ADC`, `SUP` |
| `game_team` | `blue`, `red` |
| `game_result` | `1`, `0` |

## Player Game Payload

MMR 서비스가 받는 기본 row 단위는 player-game이다.

한 경기는 10개 player-game row로 구성된다.

```json
{
  "custom_match_id": "CUSTOM-MATCH-260601-example-1",
  "participant_id": 123,
  "guild_id": "123456789",
  "season": "2026",
  "puuid": "puuid-000001",
  "riot_name": "optional riot name",
  "riot_name_tag": "optional tag",
  "champion_id": "1",
  "game_team": "blue",
  "position": "TOP",
  "game_result": 1,
  "time_played": 1800,
  "kill": 4,
  "death": 2,
  "assist": 6,
  "gold": 12000,
  "ccing": 20,
  "exp": 15000,
  "total_damage_champions": 23000,
  "total_damage_dealt_to_buildings": 2500,
  "total_damage_taken": 18000,
  "vision_score": 25,
  "vision_bought": 1,
  "minions_killed": 180,
  "neutral_minions_killed": 12,
  "wards_placed": 8,
  "wards_killed": 3,
  "time_spent_dead": 120,
  "heal_on_teammates": 0,
  "shield_on_teammates": 0,
  "feature_version": "2026-06",
  "played_at": "2026-06-01T12:00:00Z"
}
```

### 필수 필드

| 필드 | 설명 |
| --- | --- |
| `custom_match_id` | 백엔드 `custom_match.id` |
| `participant_id` | 백엔드 참가자 row ID. 필요 없으면 무시 가능 |
| `guild_id` | 길드 ID |
| `season` | 시즌 |
| `puuid` | 유저 식별자 |
| `champion_id` | 챔피언 ID |
| `game_team` | `blue`, `red` |
| `position` | `TOP`, `JUG`, `MID`, `ADC`, `SUP` |
| `game_result` | 승리 `1`, 패배 `0` |
| `time_played` | 초 단위 경기 시간 |
| `kill` | 킬 |
| `death` | 데스 |
| `assist` | 어시스트 |
| `gold` | 획득 골드 |
| `ccing` | 군중제어 시간 |
| `exp` | 경험치 |
| `total_damage_champions` | 챔피언 대상 피해량 |
| `total_damage_taken` | 받은 피해량 |
| `vision_score` | 시야 점수 |
| `played_at` | MMR 누적 계산 순서 기준 |

### 권장 필드

| 필드 | 설명 |
| --- | --- |
| `total_damage_dealt_to_buildings` | 건물 피해량 |
| `vision_bought` | 제어 와드 구매 수 |
| `minions_killed` | 미니언 처치 수 |
| `neutral_minions_killed` | 중립 몬스터 처치 수 |
| `wards_placed` | 와드 설치 수 |
| `wards_killed` | 와드 제거 수 |
| `time_spent_dead` | 사망 상태 시간 |
| `heal_on_teammates` | 아군 치유량 |
| `shield_on_teammates` | 아군 보호막량 |
| `feature_version` | 백엔드 feature 추출 버전 |

## API 1. Baseline 계산

### 용도

시즌 전체 guild 데이터를 기준으로 MMR 계산에 필요한 공통 baseline을 계산한다.

baseline은 시즌별로 관리하고, active baseline은 시즌별 1개만 유지한다.
baseline은 guild별로 나누지 않는다.

### Endpoint

```http
POST /v1/mmr/baselines/calculate
```

### Request

```json
{
  "season": "2026",
  "baseline_version": "2026-06",
  "matches": [
    {
      "custom_match_id": "CUSTOM-MATCH-260601-example-1",
      "participant_id": 123,
      "guild_id": "123456789",
      "season": "2026",
      "puuid": "puuid-000001",
      "position": "TOP",
      "game_team": "blue",
      "game_result": 1,
      "time_played": 1800,
      "kill": 4,
      "death": 2,
      "assist": 6,
      "gold": 12000,
      "ccing": 20,
      "exp": 15000,
      "total_damage_champions": 23000,
      "total_damage_dealt_to_buildings": 2500,
      "total_damage_taken": 18000,
      "vision_score": 25,
      "vision_bought": 1,
      "minions_killed": 180,
      "neutral_minions_killed": 12,
      "wards_placed": 8,
      "wards_killed": 3,
      "time_spent_dead": 120,
      "heal_on_teammates": 0,
      "shield_on_teammates": 0,
      "played_at": "2026-06-01T12:00:00Z"
    }
  ]
}
```

### Response

```json
{
  "season": "2026",
  "baseline_version": "2026-06",
  "mmr_baseline": {
    "f1_mean": 1.0,
    "f2_mean": 50.0
  },
  "game_impact_baseline": {
    "position_weights": {},
    "outcome_stats": []
  },
  "metadata": {
    "match_count": 1000,
    "player_game_row_count": 10000,
    "calculated_at": "2026-06-01T00:00:00Z"
  }
}
```

## API 2. 전체 MMR 계산

### 용도

특정 `guild_id + season`의 전체 player-game 데이터를 받아 MMR을 처음부터 다시 계산한다.

사용 시점:

- MMR 구독 시작 후 초기 계산
- MMR 산식 변경 후 재계산
- 경기 삭제/수정 후 정합성 복구
- 장애 복구

### Endpoint

```http
POST /v1/mmr/recalculate
```

### Request

```json
{
  "guild_id": "123456789",
  "season": "2026",
  "calculation_id": "MMR-20260601-0001",
  "baseline_version": "2026-06",
  "mmr_baseline": {
    "f1_mean": 1.0,
    "f2_mean": 50.0
  },
  "game_impact_baseline": {
    "position_weights": {},
    "outcome_stats": []
  },
  "matches": [
    {
      "custom_match_id": "CUSTOM-MATCH-260601-example-1",
      "participant_id": 123,
      "puuid": "puuid-000001",
      "position": "TOP",
      "game_team": "blue",
      "game_result": 1,
      "time_played": 1800,
      "kill": 4,
      "death": 2,
      "assist": 6,
      "gold": 12000,
      "ccing": 20,
      "exp": 15000,
      "total_damage_champions": 23000,
      "total_damage_taken": 18000,
      "vision_score": 25,
      "played_at": "2026-06-01T12:00:00Z"
    }
  ]
}
```

### Response

```json
{
  "guild_id": "123456789",
  "season": "2026",
  "calculation_id": "MMR-20260601-0001",
  "baseline_version": "2026-06",
  "match_results": [
    {
      "custom_match_id": "CUSTOM-MATCH-260601-example-1",
      "participant_id": 123,
      "puuid": "puuid-000001",
      "position": "TOP",
      "game_result": 1,
      "pre_game_mmr": 1300,
      "expected_score": 0.5,
      "actual_score": 0.62,
      "relative_factor": 1.24,
      "personal_factor": 1.08,
      "final_factor": 1.13,
      "mmr_change": 23,
      "post_game_mmr": 1323
    }
  ],
  "user_summary": [
    {
      "puuid": "puuid-000001",
      "total_mmr": 1323,
      "total_games": 10,
      "overall_winrate": 60.0
    }
  ],
  "mmr_history": [
    {
      "puuid": "puuid-000001",
      "custom_match_id": "CUSTOM-MATCH-260601-example-1",
      "history_type": "MATCH_RESULT",
      "mmr_delta": 23,
      "before_mmr": 1300,
      "after_mmr": 1323,
      "source_calculation_id": "MMR-20260601-0001",
      "reason": "match result"
    }
  ],
  "metadata": {
    "match_count": 100,
    "player_game_row_count": 1000,
    "calculated_at": "2026-06-01T00:10:00Z"
  }
}
```

## API 3. 단일 경기 MMR 계산

### 용도

MMR 구독이 활성화된 길드에서 신규 경기 1개가 저장된 후, 해당 경기의 MMR 변화를 계산한다.

### Endpoint

```http
POST /v1/mmr/matches/calculate
```

### Request

```json
{
  "guild_id": "123456789",
  "season": "2026",
  "calculation_id": "MMR-20260601-0002",
  "custom_match_id": "CUSTOM-MATCH-260601-example-2",
  "baseline_version": "2026-06",
  "mmr_baseline": {
    "f1_mean": 1.0,
    "f2_mean": 50.0
  },
  "game_impact_baseline": {
    "position_weights": {},
    "outcome_stats": []
  },
  "match_rows": [
    {
      "custom_match_id": "CUSTOM-MATCH-260601-example-2",
      "participant_id": 456,
      "puuid": "puuid-000001",
      "position": "TOP",
      "game_team": "blue",
      "game_result": 1,
      "time_played": 1800,
      "kill": 4,
      "death": 2,
      "assist": 6,
      "gold": 12000,
      "ccing": 20,
      "exp": 15000,
      "total_damage_champions": 23000,
      "total_damage_taken": 18000,
      "vision_score": 25,
      "played_at": "2026-06-01T12:00:00Z"
    }
  ],
  "pre_match_user_summary": [
    {
      "puuid": "puuid-000001",
      "total_mmr": 1300,
      "total_games": 3,
      "wins": 2
    }
  ]
}
```

### Response

```json
{
  "guild_id": "123456789",
  "season": "2026",
  "calculation_id": "MMR-20260601-0002",
  "custom_match_id": "CUSTOM-MATCH-260601-example-2",
  "baseline_version": "2026-06",
  "match_results": [
    {
      "custom_match_id": "CUSTOM-MATCH-260601-example-2",
      "participant_id": 456,
      "puuid": "puuid-000001",
      "position": "TOP",
      "game_result": 1,
      "pre_game_mmr": 1300,
      "expected_score": 0.5,
      "actual_score": 0.62,
      "relative_factor": 1.24,
      "personal_factor": 1.08,
      "final_factor": 1.13,
      "mmr_change": 23,
      "post_game_mmr": 1323
    }
  ],
  "updated_user_summary": [
    {
      "puuid": "puuid-000001",
      "total_mmr": 1323,
      "total_games": 4,
      "overall_winrate": 75.0
    }
  ],
  "mmr_history": [
    {
      "puuid": "puuid-000001",
      "custom_match_id": "CUSTOM-MATCH-260601-example-2",
      "history_type": "MATCH_RESULT",
      "mmr_delta": 23,
      "before_mmr": 1300,
      "after_mmr": 1323,
      "source_calculation_id": "MMR-20260601-0002",
      "reason": "match result"
    }
  ],
  "metadata": {
    "calculated_at": "2026-06-01T00:20:00Z",
    "mode": "incremental"
  }
}
```

## 입력 검증 규칙

각 `custom_match_id`는 반드시 다음 구조를 가져야 한다.

- 정확히 10개 player-game row
- 포지션별 정확히 2개 row
- 각 `custom_match_id + position` 조합마다 승자 1명, 패자 1명
- 같은 경기 안에서 `puuid` 중복 없음
- `position`은 `TOP`, `JUG`, `MID`, `ADC`, `SUP` 중 하나
- `game_team`은 `blue`, `red` 중 하나
- `game_result`는 `1`, `0` 중 하나

검증 실패 시 `400 Bad Request`로 처리한다.

## 에러 응답

```json
{
  "error_code": "INVALID_MATCH_STRUCTURE",
  "message": "each custom_match_id must contain 10 rows",
  "details": {
    "invalid_custom_match_ids": ["CUSTOM-MATCH-260601-example-1"]
  }
}
```

권장 에러 코드:

| 코드 | 의미 |
| --- | --- |
| `MISSING_REQUIRED_COLUMN` | 필수 컬럼 누락 |
| `INVALID_MATCH_STRUCTURE` | 경기 row/포지션/승패 구조 오류 |
| `INVALID_POSITION` | `TOP`, `JUG`, `MID`, `ADC`, `SUP` 외 포지션 |
| `INVALID_GAME_TEAM` | `blue`, `red` 외 팀 값 |
| `INVALID_GAME_RESULT` | `1`, `0` 외 승패 값 |
| `INVALID_BASELINE` | baseline 누락 또는 형식 오류 |
| `INSUFFICIENT_USER_STATE` | 단일 경기 계산에 필요한 기존 유저 summary 부족 |
| `CALCULATION_FAILED` | 계산 중 예외 |

## 책임 범위

### 백엔드 책임

- 리플레이 원본 저장
- raw data에서 MMR feature 정제
- `game_result`를 `1`, `0`으로 변환
- baseline 저장 및 active baseline 관리
- MMR 서비스 API 호출
- MMR 계산 결과 저장
- guild별 `mmr_user_summary` 저장 및 조회
- MMR 서비스가 반환한 `mmr_history` 저장
- 구독 상태 관리
- backfill 및 job 처리
- 경기 삭제 보정 처리

### MMR 서비스 책임

- 백엔드 정제 payload 검증
- baseline 계산
- 전체 MMR 재계산
- 단일 경기 MMR 계산
- 일반 계산 이력 `mmr_history` 생성
- 계산 결과 반환
- 내부 계산에 필요한 컬럼명/enum 변환

## 백엔드 저장 대상

MMR 서비스 응답을 받은 뒤 백엔드는 다음 데이터를 저장한다.

- baseline: `mmr_baseline`
- 경기별 MMR 결과: `match_mmr_result`
- 유저별 현재 MMR: `player_mmr_summary`
- MMR 변경 이력: `mmr_history`
- 경기별 계산 상태: `custom_match_mmr_status`
