# MMR Service Implementation Notes

## 현재 구현 방향

MMR 서비스는 FastAPI 기반 계산 전용 서버다.

백엔드는 다음을 책임진다.

- 원천 데이터 저장
- 시즌 공통 baseline 저장
- 시즌별 active baseline 1개 유지
- `guild_id + season` 단위 MMR 결과 저장
- `mmr_history` 저장
- guild별 최신 `mmr_user_summary` 저장/조회

MMR 서비스는 다음을 책임진다.

- baseline 계산
- 전체 MMR 계산
- 단일 경기 MMR 계산
- 요청 payload를 내부 계산 컬럼으로 변환
- 계산 결과와 `mmr_history` 반환

## 구현 기준

- 공식 유저 식별자는 `puuid`다.
- baseline은 모든 guild 공통 시즌 단위 값이다.
- MMR 결과는 `guild_id + season` 단위다.
- MMR 포지션 enum은 `TOP`, `JUG`, `MID`, `ADC`, `SUP`로 통일한다.
- 포지션별 MMR summary는 사용하지 않는다.
- 전체/단일 계산 응답에는 `mmr_history`를 포함한다.
- 백엔드가 저장한 baseline을 전체/단일 계산 요청에 포함한다.

## 구현된 주요 파일

| 파일 | 설명 |
| --- | --- |
| `src/mmr/gold/mmr.py` | MMR 상태/공통 계산 코어 |
| `src/mmr/silver/game_impact.py` | Game Impact 계산과 baseline 적용 함수 |
| `src/mmr/gold/baseline.py` | baseline 계산 orchestration |
| `src/mmr/serving/service.py` | API service layer |
| `src/mmr/serving/api_server.py` | FastAPI endpoint |
| `src/mmr/serving/schemas.py` | 요청/응답 스키마 초안 |
| `scripts/run_api_server.py` | 로컬 서버 실행 |

## 계산 흐름

### Baseline 계산

```text
season 전체 guild matches
  -> 백엔드 payload를 내부 컬럼으로 변환
  -> 기본 feature 생성
  -> position_weights 계산
  -> raw_game_impact 계산
  -> outcome_stats 계산
  -> mmr_baseline 계산
  -> baseline payload 반환
```

### 전체 MMR 계산

```text
guild/season matches + baseline
  -> 백엔드 payload를 내부 컬럼으로 변환
  -> 기본 feature 생성
  -> baseline으로 Game Impact feature 생성
  -> 전체 MMR 순차 계산
  -> match_results 생성
  -> user_summary 생성
  -> mmr_history 생성
  -> 결과 반환
```

### 단일 경기 MMR 계산

```text
match_rows 10개 + pre_match_user_summary + baseline
  -> 백엔드 payload를 내부 컬럼으로 변환
  -> 기본 feature 생성
  -> baseline으로 Game Impact feature 생성
  -> 기존 state에 단일 경기 반영
  -> match_results 생성
  -> updated_user_summary 생성
  -> mmr_history 생성
  -> 결과 반환
```

## 서버 실행

```bash
pip install -r requirements.txt
python scripts/run_api_server.py
```

```text
GET http://127.0.0.1:8000/health
```

## 남은 구현 작업

- 내부 포지션 enum을 `TOP`, `JUG`, `MID`, `ADC`, `SUP`로 전환
- `puuid` 기준 API adapter 정리
- 포지션별 MMR summary 제거
- `mmr_history` 응답 생성
- 단일 경기 `pre_match_user_summary` 구조 확정
- API 계약 기준 테스트 추가
