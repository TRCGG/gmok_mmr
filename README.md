# GMOK MMR

LoL 내전 경기 데이터로 플레이어별 MMR을 계산하는 Python 저장소입니다.

- 서비스 시작 전에 **과거 기록 MMR을 한 번 계산**해 DB에 채웁니다.
- 시즌별 **baseline**(Game Impact·MMR 보정 기준값)을 만들어 DB에 저장합니다.
- 서비스 시작 뒤 경기별 MMR 계산은 백엔드가 이 저장소의 산식을 옮겨 수행합니다.

## 계산 흐름

```text
원천 경기(일반내전) → 정제 → 파생 feature → Game Impact(baseline 적용)
  → 인분(game_n_person_contribution) · 상대 대비(game_impact_vs_opponent)
  → ELO 기반 포지션 MMR → 결과 행 · 유저 요약 · position_report
```

- MMR은 길드·시즌·계정(`player_code`)·포지션별로 계산하고, 시즌마다 `1300`에서 시작합니다.
- 기본 설정: 승리 `+20`, 패배 `-15`, 변화량 `-25 ~ +30`, K-factor 감쇠 시작 `1500`
- `position_report`: 포지션별 지표 평균과 플레이 스타일(같은 길드·포지션 비교 백분위)

## 프로젝트 구조

```text
.
├── migrations/                   # DB DDL (db_test/: mmr_baselines)
├── scripts/
│   ├── calculate_baseline.py     # 시즌 baseline 계산·저장
│   ├── run_mmr_once.py           # 과거 기록 MMR 1회 계산·저장
│   └── run_api_server.py         # 계산 API 서버
├── src/mmr/                      # 계산 패키지 (DB 의존 없음)
│   ├── silver/                   # 정제 · 파생 feature · Game Impact
│   ├── gold/                     # baseline · MMR · position_report
│   └── serving/                  # 계산 서비스 · FastAPI
├── tests/
│   ├── harness/                  # DB 입출력, 시즌 처리
│   ├── cli/                      # 확인용 로컬 스크립트
│   └── test_*.py
└── archive/notebooks/            # 원본 노트북
```

## 설치

```bash
pip install -r requirements.txt
cp .env.example .env   # DB 접속 정보와 테이블명을 채운다
```

## 실행

### 1. migration

DB마다 번호 순서대로 한 번 적용합니다. 006은 `mmr_match_results`·`mmr_user_summary`를 비운 뒤
적용합니다.

```bash
psql -v ON_ERROR_STOP=1 -d <DB_NAME> -f migrations/001_create_mmr_result_tables.sql
psql -v ON_ERROR_STOP=1 -d <DB_NAME> -f migrations/003_alter_tables.sql
psql -v ON_ERROR_STOP=1 -d <DB_NAME> -f migrations/004_rename_summary_position_columns.sql
psql -v ON_ERROR_STOP=1 -d <DB_NAME> -f migrations/005_add_mmr_player_account.sql
psql -v ON_ERROR_STOP=1 -d <DB_NAME> -f migrations/006_mmr_report_season_baseline.sql
psql -v ON_ERROR_STOP=1 -d <DB_NAME> -f migrations/db_test/001_create_mmr_baselines.sql
```

### 2. baseline 계산

시즌의 일반내전 경기(전체 길드)로 baseline을 만들어 저장합니다. 200판 미만이면 저장하지 않으며,
같은 버전은 덮어쓰지 않습니다.

```bash
python scripts/calculate_baseline.py --season 2026 --baseline-version 20261117 --dry-run
python scripts/calculate_baseline.py --season 2026 --baseline-version 20261117
```

### 3. 과거 기록 MMR 계산

시즌마다 저장된 baseline으로 계산해 결과·유저 요약·`position_report`를 길드·시즌 단위로
교체 저장합니다. 이미 결과가 있으면 기본으로 중단하므로 `MMR_ALLOW_RECALCULATE=1`을 지정합니다.
서비스 시작 뒤에는 다시 실행하지 않습니다.

```bash
MMR_ALLOW_RECALCULATE=1 python scripts/run_mmr_once.py
```

`MMR_SEASON`, `MMR_GUILD_ID`로 범위를 좁힐 수 있지만 운영 계산은 전체 범위로 실행합니다.

### 확인용

저장된 baseline으로 한 시즌을 계산만 합니다(저장하지 않음).

```bash
python tests/cli/calculate_full_mmr_with_db_baseline.py --season 2026
```

## 테스트

```bash
python -m pytest -q
```

## 원본 로직

원본 작업 소스는 `archive/notebooks/MMR 작업 소스.ipynb`에 있습니다. 핵심 계산 흐름은 같고,
다음은 의도적으로 바꿨습니다.

- CSV 대신 DB 입출력, 깨진 경기 구조는 계산 전에 거부
- 시즌별 계산과 시즌별 baseline, 일반내전만 계산
- 부캐를 본캐에 합치지 않고 계정별로 계산
- Game Impact 정규화 기준(가중치·분위수·min/max)을 baseline에 저장해 한 경기 계산에도 같은 기준 적용
- 정수 MMR은 .5에서 0에서 먼 쪽으로 반올림
