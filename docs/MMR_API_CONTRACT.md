# MMR API Contract Summary

이 문서는 백엔드와 MMR 서비스 간 API 요약이다. 상세 계약은 `docs/MMR_SERVICE_CONTRACT.md`를 기준으로 한다.

## API 목록

| API | Endpoint | 설명 |
| --- | --- | --- |
| Baseline 계산 | `POST /v1/mmr/baselines/calculate` | 시즌별 모든 클랜 데이터를 받아 baseline 계산 |
| 전체 MMR 계산 | `POST /v1/mmr/recalculate` | 특정 길드/시즌 전체 MMR 재계산 |
| 단일 경기 MMR 계산 | `POST /v1/mmr/matches/calculate` | 신규 경기 1개 MMR 증분 계산 |

## 공통 원칙

- MMR 서비스는 계산만 수행한다.
- DB 저장 책임은 백엔드에 있다.
- 공식 유저 식별자는 `player_code`다.
- `game_result`는 `1` 승리, `0` 패배다.
- `position`은 백엔드 기준 `TOP`, `JUG`, `MID`, `ADC`, `SUP`를 사용한다.
- baseline은 백엔드가 저장하고 계산 요청마다 MMR 서비스에 전달한다.

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
  "metadata": {}
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
  "baseline_version": "2026-06",
  "mmr_baseline": {},
  "game_impact_baseline": {},
  "matches": []
}
```

출력:

```json
{
  "guild_id": "123456789",
  "season": "2026",
  "baseline_version": "2026-06",
  "match_results": [],
  "user_summary": [],
  "position_summary": []
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
  "replay_code": "RPY-260601-example-1",
  "baseline_version": "2026-06",
  "mmr_baseline": {},
  "game_impact_baseline": {},
  "match_rows": [],
  "current_user_state": []
}
```

출력:

```json
{
  "guild_id": "123456789",
  "season": "2026",
  "replay_code": "RPY-260601-example-1",
  "baseline_version": "2026-06",
  "match_results": [],
  "updated_user_summary": [],
  "updated_position_summary": []
}
```

