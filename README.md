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
  -> game_impact_winloss_norm
  -> game_n_person_contribution
  -> game_impact_vs_opponent
  -> update_mmr_elo
  -> save_mmr_results
```

## MMR 계산 개요

파이프라인은 단순 승패만 보지 않고 다음 값을 같이 반영합니다.

- `Game Impact`: 포지션별 feature importance 기반 경기 영향도
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
├── docs/                           # 작업 로그, 로직 리뷰, 통합 로직 참고 문서
├── migrations/                     # DB DDL migration
├── scripts/
│   └── main_pipeline.py            # 실행 진입점
├── src/mmr_refactor/
│   ├── config.py                   # env 기반 설정
│   ├── data_loader.py              # DB/API raw 데이터 로딩 라우터
│   ├── data_writer.py              # DB/API 결과 저장 라우터
│   ├── features.py                 # 파생 feature 생성, metric 목록
│   ├── game_impact.py              # Game Impact 계산
│   ├── mmr.py                      # ELO 기반 MMR 계산
│   ├── repository.py               # DB SQL read/write
│   └── silver.py                   # 기본 정제
└── tests/                          # 단위 테스트
```

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

MMR_MATCH_RESULT_TABLE=mmr_match_results
MMR_SUMMARY_TABLE=mmr_user_summary
```

## DB migration

결과 저장 테이블을 먼저 생성합니다.

```bash
psql -d <DB_NAME> -f migrations/001_create_mmr_result_tables.sql
psql -d <DB_NAME> -f migrations/002_drop_player_game_id_from_mmr_match_results.sql
```

현재 결과 저장 테이블은 계산 결과 중심 컬럼만 저장합니다. DB 조회 단계에서는 원본 notebook 기준 Game Impact metric을 맞추기 위해 더 많은 raw/derived 컬럼을 사용하지만, 저장 시에는 실제 결과 테이블에 존재하는 컬럼만 저장됩니다.

추가 metric 컬럼까지 결과 테이블에 남기려면 별도 migration으로 `mmr_match_results`를 확장해야 합니다.

## 실행

DB에서 raw 데이터를 읽고 계산 결과를 DB에 저장합니다.

```bash
python scripts/main_pipeline.py --source db --sink db
```

기본값은 `.env`의 `MMR_DATA_SOURCE`, `MMR_RESULT_SINK`를 따릅니다.

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
