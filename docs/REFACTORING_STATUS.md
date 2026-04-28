# Refactoring Status

> 최종 업데이트: 2026-04-28
> 브랜치: `claude/review-codebase-7cn2o`

이 문서는 코드베이스 점검 후 진행한 리팩토링 작업과 남은 작업을 정리한다.
**원칙**: 결과값(MMR/score)을 변경하지 않는 순수 리팩토링만 수행했다.

---

## 1. 진행한 작업

### 1.1 인프라 / 설정 (Stage 1·2)

| 항목 | 파일 | 비고 |
|---|---|---|
| `.gitignore` | 신규 | `.env`, `__pycache__/`, 산출물 제외 |
| `requirements.txt` | 신규 | pandas / sklearn / SQLAlchemy / psycopg2 / dotenv. `requests`는 API 전환 시 활성화 |
| `.env.example` | 신규 | DB 연결 정보 + API_BASE_URL/TOKEN(주석) + OUTPUT_DIR |
| `src/mmr_refactor/config.py` | 신규 | `.env` 자동 로드, `get_db_url()`, `get_output_dir()` |

### 1.2 데이터 로더 (DB 버전)

`src/mmr_refactor/data_loader.py`

- `load_match_dataframe()` — `player_game` JOIN `player` 조회
- `load_user_name_dataframe()` — `player` puuid ↔ riot_name 매핑
- `_load_*_from_api()` — TODO 주석 블록으로 보존 (백엔드 API 전환 시 사용)

### 1.3 핵심 계산 모듈 추출

| 모듈 | 추출 대상 | 핵심 함수 |
|---|---|---|
| `silver.py` | `03_*` | `clean_match_data`, `find_rows_with_na` |
| `game_impact.py` | `04/05/07/09_*` | `derive_position_weights`, `compute_raw_game_impact`, `normalize_minmax_0_100`, `normalize_by_position_outcome`, `compute_n_person_contribution`, `compute_vs_opponent` |
| `mmr.py` | `10_*` | `update_mmr_elo`, `make_summary_df_wide`, `expected_performance`, `calculate_personal_factor`, `calculate_k_factor` |

추출 후 `refactored_sources/` 의 해당 셀들은 모듈을 호출하는 얇은 wrapper로 축소되었다 (시각화/출력만 보존).

### 1.4 노트북 셀 정리

- `01_environment_setup.py` — Jupyter 매직(`!pip`, `%config`) 제거 (스크립트 모드 호환)
- `02_load_raw_match_data.py` — 하드코딩 CSV 경로 제거 → `load_match_dataframe()` 호출
- `04_*` — `sys.exit()` → `raise KeyError` (파이프라인이 죽지 않도록)
- `11_*` — 유저명 DB 로더 사용, Excel 출력은 `OUTPUT_DIR` + `openpyxl` 명시
- `12_*` — DB 로더 사용, `user_name` 중복 로드 제거, `display()` fallback, 자동 실행을 `if __name__ == "__main__":` 로 가드

### 1.5 splitter 개선

`src/mmr_refactor/splitter.py` — 분리 출력 파일 상단에 `import numpy / pandas` 자동 prepend.

### 1.6 SQL 미사용 표시

`league_postgres (2).sql` 최상단에 `-- TODO: 현재 미사용. 추후 정리(삭제처리) 예정.` 주석 추가.

---

## 2. 커밋 이력

| 커밋 | 요약 |
|---|---|
| `5320226` | `docs(sql)`: SQL 스키마 미사용 표시 |
| `d226aa0` | `refactor`: DB 로더 도입 + 노트북 셀 정리 |
| `ca1d1ce` | `refactor`: `game_impact` 모듈 추출 |
| `90aca6f` | `refactor`: `silver` / `mmr` 모듈 추출 |

---

## 3. 의도적으로 손대지 않은 영역

| 영역 | 사유 |
|---|---|
| `09`/`10` 의 `iterrows()` 벡터화 | 결과값 미세 변경 가능 (부동소수 처리 순서 등) |
| 통계/모델 보정 (`04` train/test split, `05` position-wise norm 등) | MMR/score 산출값 변경 |
| ELO `±12` 클램프와 K-factor 충돌 정리 | 결과값 변경 |
| `played_at` 정렬 키 | 결과값 변경 |
| SQL 스키마/트리거 | 미사용으로 표시됨, 추후 삭제 예정 |

→ 위 항목은 별도 PR 로 회귀 테스트와 함께 진행 권장.

---

## 4. 남은 작업 (TODO)

### 우선순위 ★ (모듈화 마무리)

#### 4.1 `reporting.py` 모듈 추출
- 대상: `11_build_user_summary_tables.py`, `12_generate_player_style_report.py`
- 작업 내용:
  - `build_position_summary(mmr_df_updated, summary_df, user_names) -> dict[pos, df]`
  - `export_summary_to_excel(summary_dfs, output_path)`
  - `generate_player_report(player_name, ...) -> dict`
  - 상수(`POS_LIST`, `BASE_KPI_MAP`, `POS_RADAR_WEIGHTS`, `STYLE_RULES`, `POSITION_TENDENCY_RULES` 등)을 모듈 상수로 이동
- 기대 효과: API 서비스에서 단일 유저 리포트 호출 가능

#### 4.2 `scripts/main_pipeline.py` 오케스트레이터
- bronze → silver → game_impact → mmr → reporting 호출하는 단일 진입점
- CLI: `python scripts/main_pipeline.py [--positions ...] [--output ...]`
- 기존 모듈을 import 만 해서 호출, 새 로직 추가 없음

### 우선순위 ☆ (테스트)

#### 4.3 단위 테스트 추가
- `tests/test_splitter.py` — 작은 노트북 fixture 로 분리/prepend 검증
- `tests/test_silver.py` — `clean_match_data`, `find_rows_with_na`
- `tests/test_game_impact.py` — 합성 입력으로 함수별 검증
- `tests/test_mmr.py` — 1게임/2게임 합성 데이터로 MMR 갱신 결과 검증
- `pytest.ini` 또는 `pyproject.toml` 에 pytest 설정

### 우선순위 ☆ (저장소 정리)

#### 4.4 노트북 원본 아카이빙
- `MMR 작업 소스.py` / `.ipynb`, `MMR_RAW.py` / `.ipynb` (각 약 2~3MB)
- `archive/` 디렉토리로 이동 후 `archive/README.md` 에 보존 사유 기록

#### 4.5 README 갱신
- `.env` 사용법 (`.env.example` 복사)
- `pip install -r requirements.txt`
- 새 모듈 구조 다이어그램
- `main_pipeline.py` 실행 예시

#### 4.6 폰트 통일
- `Malgun Gothic` 하드코딩이 4개 파일에 분산. 공통 헬퍼(`config` 또는 `viz_utils.set_korean_font()`)로 일원화

#### 4.7 EDA 셀 (옵션)
- `06_inspect_position_distribution.py`, `08_validate_normalization_results.py` — QA 전용. 모듈화 우선순위는 낮으나, 정합성 검증을 자동화하려면 함수화 필요

### 우선순위 ☆ (DB 스키마 확정 후)

#### 4.8 `data_loader.py` 의 SQL 조정
- 현재 SQL 은 `league_postgres (2).sql` 의 `player_game` 스키마를 가정한 placeholder
- 실제 운영 스키마 확정 시 컬럼 매핑 / per-min 파생 SQL 보완 필요
- `data_loader.py` 한 곳만 수정하면 파이프라인은 영향 없음

#### 4.9 백엔드 API 버전 활성화
- `_load_match_from_api()` / `_load_user_name_from_api()` 주석 해제
- `requirements.txt` 에 `requests` 활성화
- `config.py` 의 `get_api_base_url()`, `get_api_token()` 주석 해제
- `load_match_dataframe()` 본체에서 DB 대신 API 호출로 전환

---

## 5. 권장 다음 PR 단위

1. **PR-A**: `reporting.py` 추출 + `main_pipeline.py` 추가
2. **PR-B**: 단위 테스트 추가 + CI (GitHub Actions) 도입
3. **PR-C**: 저장소 정리 (archive 이동, README 갱신, 폰트 통일)
4. **PR-D**: 통계/모델 보정 (결과값 변경 — 회귀 테스트 동반 필수)
