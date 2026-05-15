# MMR API Contract Summary

이 문서는 백엔드와 MMR 서비스가 맞춰야 하는 API 요약이다.
상세 계약은 `docs/MMR_SERVICE_CONTRACT.md`를 기준으로 한다.

## 확정 원칙

- MMR 계산은 MMR 서비스가 담당한다.
- DB 저장은 백엔드가 담당한다.
- baseline은 시즌별로 관리한다.
- baseline은 모든 guild가 공통으로 사용하는 시즌 단위 값이다.
- 시즌별 active baseline은 1개만 유지한다.
- baseline은 매 경기마다 재계산하지 않고, 월 1회 또는 정해진 주기마다 시즌 전체 guild 데이터로 계산한다.
- MMR 결과와 유저 summary는 `guild_id + season` 단위로 관리한다.
- 전체 MMR 계산과 단일 경기 MMR 계산은 백엔드가 전달한 baseline을 사용한다.
- 유저 식별자는 `puuid`를 그대로 사용한다.
- 경기 식별자는 `custom_match_id`를 사용한다.
- `custom_match_id` 1개가 `custom_match` 1개이며, 한 경기를 의미한다.
- MMR 포지션은 `TOP`, `JUG`, `MID`, `ADC`, `SUP`로 저장한다.
- 포지션별 MMR summary는 사용하지 않는다.
- `mmr_history`를 추가해 경기별 MMR 변경 이력을 저장한다.

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

## Baseline 계산 API

```http
POST /v1/mmr/baselines/calculate
```

입력:

```json
{
  "season": "2026",
  "baseline_version": "2026-06",
  "matches": []
}
```

출력:

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

## 전체 MMR 계산 API

```http
POST /v1/mmr/recalculate
```

입력:

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
      "puuid": "puuid-000001",
      "position": "TOP",
      "game_result": 1
    }
  ]
}
```

출력:

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

## 단일 경기 MMR 계산 API

```http
POST /v1/mmr/matches/calculate
```

입력:

```json
{
  "guild_id": "123456789",
  "season": "2026",
  "calculation_id": "MMR-20260601-0002",
  "custom_match_id": "CUSTOM-MATCH-260601-example-1",
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
  "pre_match_user_summary": []
}
```

출력:

```json
{
  "guild_id": "123456789",
  "season": "2026",
  "calculation_id": "MMR-20260601-0002",
  "custom_match_id": "CUSTOM-MATCH-260601-example-1",
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

## 백엔드 저장 대상

- baseline
- active baseline
- MMR 결과
- guild별 유저 현재 MMR summary
- `mmr_history`

