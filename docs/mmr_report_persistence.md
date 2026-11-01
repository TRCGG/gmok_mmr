# MMR 리포트 저장 설계

## 목적

MMR 일괄 계산 결과를 프론트가 추가 가공 없이 조회할 수 있도록 경기별 MMR 이력과
유저·포지션별 리포트 요약을 함께 저장한다. 현재 배치 실행과 추후 단일 경기 실시간
반영이 같은 테이블을 사용하도록 고유 키와 업서트 기준을 고정한다.

## 책임 분리

- `src/mmr/gold/report.py`: DataFrame 입력으로 리포트 지표와 스타일을 계산한다. DB에 접근하지 않는다.
- `scripts/run_mmr_once.py`: 전체 계산 결과에서 이력과 포지션 요약을 만들고 저장 어댑터를 호출한다.
- `tests/harness/db_test/repository.py`: 테스트·배치용 PostgreSQL 저장을 담당한다.
- `migrations/006_create_mmr_report_tables.sql`: 리포트 조회용 테이블과 인덱스를 생성한다.

## 저장 테이블

### `mmr_history`

경기 종료 시점의 포지션 MMR을 저장한다.

- 고유 키: `(guild_id, player_code, position, replay_code)`
- `player_code`: 본캐로 통합된 MMR 귀속 계정
- `mmr`: 해당 경기 종료 시점 `pos_cumulative_mmr`
- `mmr_change`: 해당 경기의 MMR 변화량
- `played_at`: 그래프 정렬 및 기간 비교 기준

### `mmr_user_position_summary`

프론트 목록과 상세 화면에 필요한 현재 집계 결과를 포지션별 한 행으로 저장한다.

- 고유 키: `(guild_id, player_code, position)`
- MMR, 판수, 승률과 공통 경기 지표 저장
- `base_style`, `position_style`, `comparison_basis`, `reference_users` 저장
- 20판 이상인 같은 길드·포지션 유저가 5명 이상일 때 스타일을 분류
- 조건이 부족하거나 뚜렷한 규칙이 없으면 `분류 준비 상태` 저장
- 스타일 비교는 전체 계산 기록으로 수행하고 최종 저장 행은 `guild_member.status = '1'`인 현재 클랜원만 남긴다.
- 부캐는 `COALESCE(main_account, account)` 기준의 본캐 계정으로 합친다.

## 스타일 계산

경기별 결과를 `(guild_id, mmr_player_account, position)`으로 집계한다. 지표 평균을
같은 길드·포지션의 20판 이상 비교군에서 백분위로 변환한 후 기존 노트북 규칙을
순서대로 적용한다. 포지션 코드는 운영 코드인 `TOP/JUG/MID/ADC/SUP`을 사용한다.

## 실행 흐름

```text
원천 경기 조회
→ 본캐 계정 귀속
→ Game Impact 및 MMR 계산
→ mmr_match_results / mmr_user_summary 생성
→ mmr_history 생성
→ mmr_user_position_summary 및 스타일 생성
→ 한 번의 DB 트랜잭션으로 저장
```

## 실시간 확장

단일 경기 계산 결과에도 같은 변환 함수를 적용할 수 있다. `mmr_history`는 경기 고유
키로 업서트하고, `mmr_user_position_summary`는 유저·포지션 키로 최신 값을 교체한다.
실시간 경로에서는 스타일 비교군 전체를 다시 읽거나 별도 집계 작업으로 갱신해야 한다.

현재 클랜원 상태가 배치 이후 바뀌면 저장된 포지션 요약은 다음 배치에서 갱신된다.
실시간 회원 반영이 필요할 때는 백엔드 조회에서 `guild_member.status = '1'`을 한 번 더
검사한다.

## 프론트 조회 예시

```sql
SELECT *
FROM mmr_user_position_summary
WHERE guild_id = :guild_id
  AND position = :position
  AND games >= 5
ORDER BY mmr DESC;
```

```sql
SELECT played_at, mmr, mmr_change
FROM mmr_history
WHERE guild_id = :guild_id
  AND player_code = :player_code
  AND position = :position
ORDER BY played_at;
```

## 적용 순서

기존 001~005 마이그레이션이 적용된 DB에서는 아래 명령 한 번으로 006 마이그레이션과
전체 MMR 저장을 연속 실행한다.

```bash
python scripts/run_mmr_report_once.py
```

마이그레이션과 계산을 분리해야 하는 운영 환경에서는 006을 먼저 적용한 뒤 기존
`python scripts/run_mmr_once.py`를 실행한다.

## 구현 및 검증 결과

- 리포트 집계: `src/mmr/gold/report.py`
- 마이그레이션: `migrations/006_create_mmr_report_tables.sql`
- 통합 실행: `scripts/run_mmr_report_once.py`
- DB 저장: `tests/harness/db_test/repository.py`
- 단위·회귀 테스트: 59개 통과
- 실제 운영 DB 적용은 이 변경 범위에 포함하지 않는다.
