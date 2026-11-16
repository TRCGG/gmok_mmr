# GMOK MMR Pipeline

LoL 내전 경기 데이터를 기반으로 플레이어별 MMR을 계산하는 Python 파이프라인입니다.

현재 개발 흐름은 `DB -> MMR 계산 -> DB 저장`입니다. 이후 백엔드 API 연동이 필요하면 같은 loader/writer 인터페이스에서 `api -> api` 방식으로 전환할 수 있도록 구성했습니다.

## 주요 흐름

```text
raw match rows
  -> clean_match_data
  -> add_basic_features
  -> derive or apply position weights
  -> raw_game_impact
  -> game_impact (baseline의 시즌 전체 min/max 기준 0~100)
  -> game_impact_winloss_norm
  -> game_n_person_contribution
  -> game_impact_vs_opponent
  -> update_mmr_elo
  -> save_mmr_results
```

## MMR 계산 개요

파이프라인은 단순 승패만 보지 않고 다음 값을 같이 반영합니다.

- `Game Impact`: 포지션별 feature importance 기반 경기 영향도. `game_impact`는 노트북처럼
  시즌 전체 `raw_game_impact`의 최솟값·최댓값으로 0~100 변환하며, 이 범위를 baseline
  (`game_impact_baseline.impact_range`)에 저장해 한 경기만 계산해도 같은 기준을 씁니다.
  범위 밖 값은 0~100으로 자릅니다. MMR 계산에는 쓰이지 않습니다.
- `game_n_person_contribution`: 한 경기 안에서 개인이 차지한 기여도 비중
- `game_impact_vs_opponent`: 같은 경기, 같은 포지션 상대와의 영향도 비교
- `ELO expected score`: 상대 MMR 대비 기대 성과
- `MMRSettings`: 초기 MMR, 승패 기본 변화량, K-factor 감쇠 등 계산 설정

기본 MMR 설정:

- 초기 MMR: `1300`
- 승리 기본 변화량: `20`
- 패배 기본 변화량: `-15`
- MMR 변화량 제한: `-25 ~ 30`
- K-factor 감쇠 시작: `1500`

## 프로젝트 구조

```text
.
├── archive/notebooks/              # 원본 notebook, 변환 py 보관
├── migrations/                     # DB DDL migration
├── scripts/
│   ├── calculate_baseline.py       # 시즌 baseline 계산·저장 (로컬 수동, 200판 이상)
│   ├── run_mmr_once.py             # 과거 기록 전체 MMR 계산 (저장된 baseline 사용)
│   └── run_api_server.py           # 운영 API 서버 실행
├── src/mmr/                        # 운영 패키지 (계산 + API, DB 의존 없음)
│   ├── silver/                     # 정제 · 파생 feature · Game Impact
│   │   ├── cleaning.py             # 기본 정제 (clean/drop)
│   │   ├── features.py             # 파생 feature, metric 목록
│   │   └── game_impact.py          # Game Impact 계산
│   ├── gold/                       # baseline · ELO MMR 계산
│   │   ├── baseline.py             # baseline 조립/직렬화
│   │   └── mmr.py                  # ELO 기반 MMR 계산/요약
│   └── serving/                    # API 계층
│       ├── service.py              # 계산 서비스 함수
│       ├── api_server.py           # FastAPI 엔드포인트
│       └── schemas.py              # 요청/응답 스키마 (초안)
└── tests/
    ├── harness/                    # 테스트 전용 DB 입출력 (운영 미사용, 연동 후 삭제)
    │   ├── config.py               # DB/API 라우팅 설정
    │   ├── data_loader.py          # raw 데이터 로딩
    │   ├── data_writer.py          # 결과 저장
    │   └── db_test/                # PostgreSQL 직접 접근
    ├── cli/                        # 로컬 실행 스크립트
    │   ├── main_pipeline.py        # DB→DB 배치 파이프라인
    │   └── calculate_full_mmr_with_db_baseline.py
    └── test_*.py                   # 단위 테스트
```

> **운영 원칙**: 운영에서는 백엔드 API가 HTTP로 raw 데이터를 전달하고 결과도 HTTP 응답으로 돌려받는다. DB 직접 접근과 로컬 배치는 `tests/`(harness·cli)에만 둔다.

## 개발 환경 설정

Python 가상환경을 만든 뒤 requirements로 설치합니다.

```bash
pip install -r requirements.txt
```

`.env.example`을 참고해 `.env`를 생성합니다.

```env
MMR_DATA_SOURCE=db
MMR_RESULT_SINK=db

DB_HOST=localhost
DB_PORT=5432
DB_NAME=league
DB_USER=postgres
DB_PASSWORD=changeme

MMR_PLAYER_GAME_TABLE=player_game
MMR_PLAYER_TABLE=player
MMR_GUILD_MEMBER_TABLE=guild_member

MMR_MATCH_RESULT_TABLE=mmr_match_results
MMR_SUMMARY_TABLE=mmr_user_summary
```

## DB migration

MMR 계산의 유저 식별자는 실제 경기 계정인 `player_code`입니다. 전적과 포지션별 MMR은
`(guild_id, player_code)`별로 독립적으로 계산되며, 같은 사람이 다른 길드에서 처음
경기하면 해당 길드의 초기 MMR에서 시작합니다. 원본 `puuid`는 Riot 계정 식별용입니다.
DB 입력은 `player_game`과 `riot_account`의 `player_code`를 사용합니다.
`mmr_player_account` 컬럼은 백엔드 계약상 유지하며 항상 `player_code`와 같은 값입니다.
다른 값이 들어오면 배치가 저장 전에 중단합니다.

MMR은 부캐 매핑을 보지 않습니다. 부캐도 실제 계정 기준으로 별도 MMR을 가지며,
`scripts/run_mmr_once.py` DB 배치는 `mmr_player_account`와 사용자 요약의
`player_code`에 항상 실제 참가 계정의 `player_code`를 넣습니다(부캐 노출 여부는
조회 단계에서 처리). `guild_member`는 현재 길드원(`status = '1'`) 판정에만 쓰며,
사용자 요약에는 현재 길드원 계정만 저장합니다. 적용 전
`migrations/005_add_mmr_player_account.sql`을 실행해야 합니다. 배치를 재실행하면
계산 대상 길드·시즌의 경기 결과와 사용자 요약을 한 트랜잭션에서 교체합니다.

서비스 시작 전 과거 기록 계산은 `MMR_SEASON`, `MMR_GUILD_ID`를 비워 **전체 범위로**
실행합니다. 부분 실행하면 범위 밖에 예전 방식(부캐→본캐 귀속) 결과가 남을 수 있습니다.
실행 후 아래 쿼리가 0이어야 합니다.

```sql
SELECT count(*) FROM mmr_match_results
WHERE mmr_player_account IS DISTINCT FROM player_code;
```

migration은 DB마다 번호 순서대로 **한 번만** 적용합니다. 배치 스크립트는 migration을
실행하지 않고, 필요한 컬럼이 없으면 실행 전에 중단합니다.

```bash
psql -d <DB_NAME> -f migrations/001_create_mmr_result_tables.sql
psql -d <DB_NAME> -f migrations/003_alter_tables.sql
psql -d <DB_NAME> -f migrations/004_rename_summary_position_columns.sql
psql -d <DB_NAME> -f migrations/005_add_mmr_player_account.sql
psql -d <DB_NAME> -f migrations/006_add_position_report.sql
psql -d <DB_NAME> -f migrations/007_add_result_unique_keys.sql
psql -d <DB_NAME> -f migrations/008_add_season.sql
psql -d <DB_NAME> -f migrations/009_add_result_baseline.sql
```

- 006: 유저 요약에 포지션별 지표·스타일 JSON(`position_report`) 추가
- 007: 결과 `(guild_id, replay_code, player_code)`, 요약 `(guild_id, player_code)` 고유 인덱스
- 008: 결과·요약에 `season` 추가, 요약 고유 키를 `(guild_id, player_code, season)`으로 교체
- 009: 결과에 계산에 쓴 `baseline_season`, `baseline_version` 기록

현재 결과 저장 테이블은 계산 결과 중심 컬럼만 저장합니다. DB 조회 단계에서는 원본 notebook 기준 Game Impact metric을 맞추기 위해 더 많은 raw/derived 컬럼을 사용하지만, 저장 시에는 실제 결과 테이블에 존재하는 컬럼만 저장됩니다.

추가 metric 컬럼까지 결과 테이블에 남기려면 별도 migration으로 `mmr_match_results`를 확장해야 합니다.

## 실행

DB 결과 테이블 저장은 길드·시즌 단위로 교체하므로 `scripts/run_mmr_once.py`로만 합니다
(아래 과거 기록 전체 계산 참고). `tests/cli/main_pipeline.py`는 `--sink api`로만 동작합니다.

baseline 테이블(`mmr_baselines`)은 아래 migration으로 만듭니다. 저장된 baseline으로 한 시즌의
MMR을 계산만 해 보려면 확인용 스크립트를 씁니다. 이 스크립트는 결과를 저장하지 않습니다.

```bash
psql -d <DB_NAME> -f migrations/db_test/001_create_mmr_baselines.sql
python tests/cli/calculate_full_mmr_with_db_baseline.py --season 2026
```

기본값은 `.env`의 `MMR_DATA_SOURCE`, `MMR_RESULT_SINK`를 따릅니다.

### baseline 계산 (로컬 수동 실행)

baseline은 MMR 계산과 분리해 `scripts/calculate_baseline.py`로 시즌마다 만들고 DB
(`mmr_baselines`)에 저장합니다. 전체 길드의 해당 시즌 경기(`custom_match.season`)를 쓰며,
5v5 검증을 통과한 경기가 **200판 미만**이거나 baseline이 퇴화하면 저장하지 않고
중단합니다. 같은 `(season, baseline_version)`이 이미 있으면 덮어쓰지 않고 중단하므로 새
버전을 지정합니다. 저장하면 같은 시즌의 이전 baseline은 비활성화되고, `metadata.scope =
all_guilds` 표식이 남습니다.

```bash
python scripts/calculate_baseline.py --season 2026 --baseline-version 20261117 --dry-run
python scripts/calculate_baseline.py --season 2026 --baseline-version 20261117
```

새 시즌이 시작되면 그 시즌 baseline이 생길 때까지 **가장 최근에 저장된(`saved_at`) 활성
baseline**으로 계산하고, 200판이 쌓여 새 baseline을 저장하면 이후 계산부터 새 baseline을
씁니다. 시즌 문자열은 비교하지 않습니다. 지난 시즌 baseline을 나중에 다시 저장하면 그것이
가장 최근 baseline이 되므로, 지난 시즌 baseline은 다시 만들지 않습니다.
이미 계산된 결과는 다시 계산하지 않으며, 결과 행의 `baseline_season`, `baseline_version`으로
어느 baseline으로 계산했는지 확인할 수 있습니다.

### 과거 기록 전체 계산

과거 기록 전체 계산은 아래 배치로 한 번 실행합니다. 006~009 migration과 시즌 baseline이
먼저 있어야 합니다. 배치는 baseline을 만들지 않고, 시즌마다 그 시즌의 활성 baseline
(없으면 가장 최근에 저장된 활성 baseline)을 읽어 계산합니다. 200판 미만이거나
`scripts/calculate_baseline.py`로 만들지 않은(`metadata.scope` 표식이 없는) baseline은 쓰지
않고 중단합니다. 이 배치는 시즌 전체를 그 시즌의 현재 baseline으로 계산하므로, 백엔드가 시즌
초반을 이전 baseline으로 계산한 결과와는 다를 수 있습니다.

대상 길드·시즌에 이미 결과가 있으면 기본으로 중단합니다. 서비스 시작 뒤에는 백엔드가 결과를
이어서 쌓으므로 다시 돌리면 그 결과를 덮어쓰게 됩니다. 서비스 시작 전 과거 기록 계산이나
의도적인 재구성에만 `MMR_ALLOW_RECALCULATE=1`을 지정합니다. 시즌은 경기의 `custom_match.season`을 따르며, 시즌마다 초기 MMR부터
따로 계산합니다. 유저 요약은 길드·선수·시즌별 1행이고, 포지션별 지표·스타일은
`position_report` JSON에 함께 저장합니다. 경기별 MMR 이력은 경기 결과 테이블을 사용합니다.

```bash
MMR_ALLOW_RECALCULATE=1 python scripts/run_mmr_once.py
```

## 테스트

Windows 환경에서 pytest cache 권한 문제가 생길 수 있어 cache provider를 끄고 실행합니다.

```bash
pytest tests -q -p no:cacheprovider
```

현재 주요 테스트 범위:

- feature 생성
- Game Impact 계산
- MMR 입력 경기 구조 검증
- MMR 계산 설정 주입
- DB repository SQL 위치 및 조회 컬럼
- 결과 writer 반올림/컬럼 정리

## 원본 로직 비교 기준

원본 MMR 작업 소스는 `archive/notebooks/MMR 작업 소스.ipynb`와 `archive/notebooks/MMR 작업 소스.py`에 보관되어 있습니다.

현재 리팩토링된 로직은 원본의 핵심 계산 흐름을 모듈화한 구조입니다.

의도적으로 바뀐 부분:

- CSV 대신 DB/API adapter 기반 입출력
- 깨진 경기 구조 입력 시 MMR 계산 전 `ValueError`
- 상대 포지션 비교 점수의 index 보존
- MMR 설정값을 `MMRSettings`로 주입 가능
- position weight를 외부에서 주입하거나 현재 데이터로 학습 가능

원본 기준 Game Impact metric pool은 `features.py`의 `BASE_METRICS`에 반영되어 있습니다.
