# MMR API 상세 스펙 정리

## 목적

MMR 서비스와 연동할 API의 상세 스펙을 정리한다.

백엔드에서 확정할 수 있는 항목은 이 문서에서 확정하고, MMR 계산 로직 내부 구조와 직접 관련된 항목은 MMR 서비스에서 확정하도록 분리한다.

## 백엔드 확정 항목

### 공통 식별자

| 항목 | 확정값 |
| --- | --- |
| 유저 식별자 | `puuid` |
| 경기 식별자 | `custom_match_id` |
| 길드 식별자 | `guild_id` |
| 시즌 식별자 | `season` |
| 계산 실행 식별자 | `calculation_id` |
| baseline 식별자 | `baseline_version` |

범위:

- baseline은 `season` 단위 공통 값이다.
- baseline은 모든 guild가 함께 사용한다.
- MMR 결과, 유저 summary, history는 `guild_id + season` 단위로 저장한다.

### 공통 Enum

| 필드 | 값 |
| --- | --- |
| `position` | `TOP`, `JUG`, `MID`, `ADC`, `SUP` |
| `game_team` | `blue`, `red` |
| `game_result` | `1`, `0` |

`game_result` 의미:

```text
1 = 승리
0 = 패배
```

### 시간 단위

| 필드 | 단위 |
| --- | --- |
| `time_played` | 초 |
| `played_at` | ISO 8601 datetime string |
| `calculated_at` | ISO 8601 datetime string |

### 백엔드가 전달할 player-game 필드

백엔드는 MMR 서비스에 `replay.raw_data`를 그대로 전달하지 않는다.

백엔드는 raw data와 DB 데이터를 조합해 아래 player-game payload로 정제해 전달한다.

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

### 백엔드 기준 필수 필드

백엔드는 아래 필드를 항상 전달한다.

| 필드 | 설명 |
| --- | --- |
| `custom_match_id` | 백엔드 `custom_match.id` |
| `participant_id` | 백엔드 참가자 row ID |
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

### 백엔드가 제공 가능한 추가 필드

아래 필드는 raw data에서 정제해 제공할 수 있다.

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

## API 상세 스펙

## 1. Baseline 계산 API

### Endpoint

```http
POST /v1/mmr/baselines/calculate
Content-Type: application/json
```

### Request

백엔드 확정:

```json
{
  "season": "2026",
  "baseline_version": "2026-06",
  "matches": []
}
```

`matches`는 시즌 전체 guild의 player-game payload 배열이다.
baseline 계산 요청은 특정 `guild_id` 하나로 제한하지 않는다.

### Response

MMR 서비스가 확정해야 한다.

현재 백엔드가 기대하는 최소 구조:

```json
{
  "season": "2026",
  "baseline_version": "2026-06",
  "mmr_baseline": {},
  "game_impact_baseline": {},
  "metadata": {
    "match_count": 1000,
    "player_game_row_count": 10000,
    "calculated_at": "2026-06-01T00:00:00Z"
  }
}
```

MMR 서비스 확정 필요:

- `mmr_baseline` 내부 JSON 구조
- `game_impact_baseline` 내부 JSON 구조
- baseline 계산에 필요한 최소 경기 수
- baseline 계산 실패 조건

## 2. 전체 MMR 재계산 API

### Endpoint

```http
POST /v1/mmr/recalculate
Content-Type: application/json
```

### Request

백엔드 확정:

```json
{
  "guild_id": "123456789",
  "season": "2026",
  "calculation_id": "MMR-20260601-0001",
  "baseline_version": "2026-06",
  "mmr_baseline": {},
  "game_impact_baseline": {},
  "matches": []
}
```

`matches`는 player-game payload 배열이다.

백엔드는 active baseline을 조회해서 `baseline_version`, `mmr_baseline`, `game_impact_baseline`을 함께 전달한다.

### Response

백엔드가 저장하기 위해 필요한 최소 구조:

```json
{
  "guild_id": "123456789",
  "season": "2026",
  "calculation_id": "MMR-20260601-0001",
  "baseline_version": "2026-06",
  "match_results": [],
  "user_summary": [],
  "mmr_history": [],
  "metadata": {
    "match_count": 100,
    "player_game_row_count": 1000,
    "calculated_at": "2026-06-01T00:10:00Z"
  }
}
```

### `match_results` 최소 기대 필드

백엔드 저장을 위해 아래 필드는 필요하다.

```json
{
  "custom_match_id": "CUSTOM-MATCH-260601-example-1",
  "participant_id": 123,
  "puuid": "puuid-000001",
  "position": "TOP",
  "game_result": 1,
  "pre_game_mmr": 1300,
  "mmr_change": 23,
  "post_game_mmr": 1323
}
```

MMR 서비스가 확정할 필드:

- `expected_score`
- `actual_score`
- `relative_factor`
- `personal_factor`
- `final_factor`
- 기타 계산 설명용 factor

### `user_summary` 최소 기대 필드

```json
{
  "puuid": "puuid-000001",
  "total_mmr": 1323,
  "total_games": 10,
  "wins": 6,
  "losses": 4,
  "overall_winrate": 60.0
}
```

백엔드 확정:

- 포지션별 MMR summary는 사용하지 않는다.
- 승률은 percent number로 저장한다. 예: `60.0`

MMR 서비스 확인 필요:

- `wins`, `losses` 제공 가능 여부
- `overall_winrate` 반올림 자리수

### `mmr_history` 최소 기대 필드

일반 계산 이력은 MMR 서비스가 생성해 반환한다.

```json
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
```

백엔드 확정:

- MMR 서비스가 반환한 `mmr_history`는 백엔드가 저장한다.
- 경기 삭제 보정 이력인 `DELETE_ADJUST`는 백엔드가 생성한다.

MMR 서비스 확정 필요:

- 전체 재계산 시 `history_type`을 `MATCH_RESULT`로 줄지, `RECALC_RESET`으로 줄지
- `reason` 값의 enum 또는 자유 문자열 여부

## 3. 단일 경기 MMR 계산 API

### Endpoint

```http
POST /v1/mmr/matches/calculate
Content-Type: application/json
```

### Request

백엔드 확정:

```json
{
  "guild_id": "123456789",
  "season": "2026",
  "calculation_id": "MMR-20260601-0002",
  "custom_match_id": "CUSTOM-MATCH-260601-example-2",
  "baseline_version": "2026-06",
  "mmr_baseline": {},
  "game_impact_baseline": {},
  "match_rows": [],
  "pre_match_user_summary": []
}
```

`match_rows`는 player-game payload 10개다.

`pre_match_user_summary`는 백엔드가 `mmr_user_summary`에서 조회한 경기 직전 유저 MMR 상태다.
백엔드는 `match_rows`의 10명 `puuid`에 해당하는 summary를 전달한다.

백엔드가 제공 가능한 구조:

```json
{
  "puuid": "puuid-000001",
  "total_mmr": 1300,
  "total_games": 3,
  "wins": 2,
  "losses": 1,
  "overall_winrate": 66.67
}
```

MMR 서비스 확정 필요:

- 단일 경기 계산에 필요한 `pre_match_user_summary` 최소 필드
- 유저가 처음 등장할 때 `pre_match_user_summary`가 없어도 계산 가능한지
- 신규 유저 기본 MMR 값

### Response

백엔드가 저장하기 위해 필요한 최소 구조:

```json
{
  "guild_id": "123456789",
  "season": "2026",
  "calculation_id": "MMR-20260601-0002",
  "custom_match_id": "CUSTOM-MATCH-260601-example-2",
  "baseline_version": "2026-06",
  "match_results": [],
  "updated_user_summary": [],
  "mmr_history": [],
  "metadata": {
    "calculated_at": "2026-06-01T00:20:00Z",
    "mode": "incremental"
  }
}
```

`match_results`, `updated_user_summary`, `mmr_history`의 세부 필드는 전체 MMR 재계산 API와 동일한 구조를 사용한다.

## 공통 입력 검증

백엔드가 보장하는 구조:

- 한 `custom_match_id`는 10개 player-game row를 가진다.
- 포지션별로 정확히 2개 row를 가진다.
- 같은 경기 안에서 `puuid` 중복은 없다.
- `position`은 `TOP`, `JUG`, `MID`, `ADC`, `SUP` 중 하나다.
- `game_team`은 `blue`, `red` 중 하나다.
- `game_result`는 `1`, `0` 중 하나다.

MMR 서비스도 방어적으로 검증해야 하는 항목:

- 필수 컬럼 누락
- 경기 row 수 오류
- 포지션 구조 오류
- 승패 구조 오류
- baseline 누락 또는 형식 오류
- 단일 경기 계산에 필요한 `pre_match_user_summary` 부족

## 공통 에러 응답

MMR 서비스에서 확정해야 한다.

백엔드가 처리하기 쉬운 권장 형식:

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

## MMR 서비스에서 확정해야 할 항목

아래 항목은 계산 로직과 직접 관련되므로 MMR 서비스에서 확정해야 한다.

1. `mmr_baseline` JSON 구조
2. `game_impact_baseline` JSON 구조
3. baseline 계산에 필요한 최소 데이터 조건
4. baseline 계산 주기 권장값
5. `pre_match_user_summary` 최소 필드
6. 신규 유저 기본 MMR
7. `match_results`의 factor 필드 목록
8. `mmr_change`, `pre_game_mmr`, `post_game_mmr`의 integer/float 여부
9. `overall_winrate` 반올림 정책
10. 전체 재계산 시 `mmr_history.history_type` 정책
11. 에러 응답 HTTP status와 `error_code` 최종 목록

## 백엔드에서 확정한 항목

아래 항목은 백엔드 정책으로 확정한다.

1. 유저 식별자는 `puuid`
2. 경기 식별자는 `custom_match_id`
3. `position` 값은 `TOP`, `JUG`, `MID`, `ADC`, `SUP`
4. `game_team` 값은 `blue`, `red`
5. `game_result` 값은 `1`, `0`
6. 포지션별 MMR summary는 사용하지 않음
7. baseline은 백엔드 DB에 저장하고 active baseline을 관리함
8. MMR 서비스가 반환한 `match_results`, `user_summary`, `mmr_history`는 백엔드가 저장함
9. 경기 삭제 보정 이력 `DELETE_ADJUST`는 백엔드가 생성함
10. baseline은 모든 guild 공통, MMR 결과는 guild별로 관리함
