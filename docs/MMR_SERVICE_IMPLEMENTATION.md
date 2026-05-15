# MMR Service Implementation Notes

## 현재 구현 방향

MMR 서비스는 FastAPI 기반 계산 전용 서버다.

백엔드는 다음을 책임진다.

- 원천 데이터 저장
- baseline 저장
- MMR 결과 저장
- active baseline 선택

MMR 서비스는 다음을 책임진다.

- baseline 계산
- 전체 MMR 계산
- 단일 경기 MMR 계산
- 요청 payload를 내부 계산 컬럼으로 변환

## 구현된 주요 파일

| 파일 | 설명 |
| --- | --- |
| `src/mmr_refactor/mmr.py` | MMR 상태/공통 계산 코어 |
| `src/mmr_refactor/game_impact.py` | Game Impact 계산과 baseline 적용 함수 |
| `src/mmr_refactor/baseline.py` | baseline 계산 orchestration |
| `src/mmr_refactor/service.py` | API service layer |
| `src/mmr_refactor/api_server.py` | FastAPI endpoint |
| `scripts/run_api_server.py` | 로컬 서버 실행 |

## 계산 흐름

### Baseline 계산

```text
season 전체 클랜 matches
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
  -> match/user/position 결과 반환
```

### 단일 경기 MMR 계산

```text
match_rows 10개 + current_user_state + baseline
  -> 백엔드 payload를 내부 컬럼으로 변환
  -> 기본 feature 생성
  -> baseline으로 Game Impact feature 생성
  -> 기존 state에 단일 경기 반영
  -> match/user/position 결과 반환
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

- `baseline.py` 기반 API endpoint 연결
- 전체 MMR 계산에서 baseline 필수화
- 단일 경기 계산에서 전체 재계산 fallback 제거
- `player_code` 기준 adapter 정리
- `position_summary` normalized 응답 생성
- 서비스 계약 기준 테스트 추가

