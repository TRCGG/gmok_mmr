# MMR Service Contract

## 목적

백엔드와 MMR 계산 서비스가 연동하기 위한 공식 API 계약을 정의한다.

MMR 서비스는 계산 전용 서비스다. 원천 데이터 저장, baseline 저장, MMR 결과 저장은 백엔드가 책임진다.

## 확정된 원칙

- MMR 계산은 MMR 서비스가 책임진다.
- 백엔드는 정제된 player-game payload를 MMR 서비스에 전달한다.
- MMR 서비스는 계산 결과만 반환하고 DB에 저장하지 않는다.
- 백엔드는 baseline과 MMR 결과를 DB에 저장한다.
- baseline은 시즌별 전체 클랜 데이터를 기준으로 일정 주기마다 계산한다.
- 전체 MMR 계산과 단일 경기 MMR 계산은 백엔드가 전달한 baseline을 사용한다.
- 공식 유저 식별자는 `player_code`다. `puuid`는 참고값이다.
- `position`, `game_team`은 백엔드 문서 기준 enum을 사용한다.
- `game_result`는 `1` 승리, `0` 패배를 사용한다.

## 공통 Enum

| 필드 | 허용값 |
| --- | --- |
| `position` | `TOP`, `JUG`, `MID`, `ADC`, `SUP` |
| `game_team` | `blue`, `red` |
| `game_result` | `1`, `0` |

MMR 서비스 내부에서는 필요 시 adapter에서 변환한다.

| 백엔드 position | MMR 내부 position |
| --- | --- |
| `TOP` | `TOP` |
| `JUG` | `JUNGLE` |
| `MID` | `MIDDLE` |
| `ADC` | `BOTTOM` |
| `SUP` | `UTILITY` |

## Player Game Payload

모든 계산 API의 경기 row는 player-game 단위다. 한 경기는 정확히 10개 row로 구성된다.

```json
{
  "player_game_id": 123,
  "replay_code": "RPY-260515-example-1",
  "guild_id": "123456789",
  "season": "2026",
  "player_code": "PLR_000001",
  "puuid": "optional-puuid",
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
  "feature_version": "2026-05-15",
  "played_at": "2026-05-15T12:00:00Z"
}
```

## API 1. Baseline 계산

### Endpoint

```http
POST /v1/mmr/baselines/calculate
```

### 용도

시즌별 모든 클랜의 player-game 데이터를 받아 MMR 계산에 사용할 baseline을 계산한다.

백엔드는 이 응답을 DB에 저장하고, 이후 전체/단일 MMR 계산 요청에 같은 baseline을 포함한다.

### Request

```json
{
  "season": "2026",
  "baseline_version": "2026-06",
  "matches": []
}
```

`matches`는 해당 시즌의 모든 클랜 player-game row 목록이다.

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
    "position_weights": {
      "TOP": {
        "kills": 0.1,
        "deaths": 0.05
      }
    },
    "outcome_stats": [
      {
        "position": "TOP",
        "game_result": 1,
        "lower": 100.0,
        "upper": 900.0
      }
    ]
  },
  "metadata": {
    "match_count": 1000,
    "player_game_row_count": 10000,
    "calculated_at": "2026-06-01T00:00:00Z"
  }
}
```

## API 2. 전체 MMR 계산

### Endpoint

```http
POST /v1/mmr/recalculate
```

### 용도

특정 `guild_id + season`의 전체 MMR을 전달받은 baseline 기준으로 재계산한다.

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
  "matches": []
}
```

### Response

```json
{
  "guild_id": "123456789",
  "season": "2026",
  "calculation_id": "MMR-20260601-0001",
  "baseline_version": "2026-06",
  "match_results": [],
  "user_summary": [],
  "position_summary": [],
  "metadata": {
    "match_count": 100,
    "player_game_row_count": 1000,
    "calculated_at": "2026-06-01T00:10:00Z"
  }
}
```

## API 3. 단일 경기 MMR 계산

### Endpoint

```http
POST /v1/mmr/matches/calculate
```

### 용도

신규 경기 1개를 기존 MMR state와 전달받은 baseline 기준으로 증분 계산한다.

### Request

```json
{
  "guild_id": "123456789",
  "season": "2026",
  "calculation_id": "MMR-20260601-0002",
  "replay_code": "RPY-260601-example-1",
  "baseline_version": "2026-06",
  "mmr_baseline": {
    "f1_mean": 1.0,
    "f2_mean": 50.0
  },
  "game_impact_baseline": {
    "position_weights": {},
    "outcome_stats": []
  },
  "match_rows": [],
  "current_user_state": [
    {
      "player_code": "PLR_000001",
      "position": "TOP",
      "pos_mmr": 1300,
      "pos_games": 3,
      "pos_wins": 2
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
  "replay_code": "RPY-260601-example-1",
  "baseline_version": "2026-06",
  "match_results": [],
  "updated_user_summary": [],
  "updated_position_summary": []
}
```

## 입력 검증 규칙

각 `replay_code`는 반드시 다음 구조를 가져야 한다.

- 정확히 10개 player-game row
- 포지션별 정확히 2개 row
- 각 `replay_code + position` 조합마다 승자 1명, 패자 1명
- 같은 경기 안에서 `player_code` 중복 없음
- `position`은 `TOP`, `JUG`, `MID`, `ADC`, `SUP` 중 하나
- `game_team`은 `blue`, `red` 중 하나
- `game_result`는 `1`, `0` 중 하나

## 책임 범위

### 백엔드

- 원천 replay/raw data 저장
- player-game payload 정제
- `player_code` 기준 유저 통합
- baseline 계산 API 호출
- baseline DB 저장 및 active baseline 선택
- MMR 계산 API 호출
- MMR 결과 DB 저장

### MMR 서비스

- payload 검증
- baseline 계산
- 전체 MMR 계산
- 단일 경기 MMR 계산
- 계산 결과 반환
- 내부 계산에 필요한 컬럼명/enum 변환

