# MMR 로직 리뷰 기록 - 2026-04-30

## 목적

MMR 계산 결과에 영향을 줄 수 있는 로직 변경 사항과 수정 이유를 기록한다.

이 문서는 단순 작업 로그가 아니라, MMR 점수 산식과 파이프라인 구조를 유지보수하기 위한 판단 근거를 남기는 문서다.

## 1. 상대 포지션 비교 점수 index 보존

### 대상 파일

- `src/mmr_refactor/game_impact.py`
- `tests/test_game_impact.py`

### 대상 함수

- `compute_vs_opponent`

### 기존 문제

`compute_vs_opponent()`는 같은 경기, 같은 포지션의 승자와 패자를 매칭해서 `game_impact_vs_opponent` 값을 계산한다.

기존 구현은 내부에서 새 DataFrame을 만든 뒤 새 `RangeIndex`를 가진 Series를 반환했다. 이후 pipeline에서 아래처럼 원본 DataFrame에 값을 대입하면 pandas는 row 순서가 아니라 index 기준으로 값을 정렬한다.

```python
feature_df["game_impact_vs_opponent"] = compute_vs_opponent(feature_df)
```

따라서 원본 `feature_df`의 index가 기본 `0..n-1` 형태가 아니면 다음 문제가 발생할 수 있었다.

- 상대 비교 점수가 다른 row에 들어감
- 일부 row가 NaN 처리됨
- 이후 MMR 계산에서 잘못된 상대 비교 점수를 사용함

### 수정 내용

원본 row index를 `_row_id`로 보존한 뒤, 최종 Series를 원본 `df.index` 기준으로 `reindex`하도록 변경했다.

이제 `compute_vs_opponent(df).index == df.index`가 보장된다.

### 수정 이유

이 변경은 점수 산식 자체를 바꾸지 않는다. 기존 산식으로 계산한 값을 원본 row에 안정적으로 매핑하기 위한 보정이다.

## 2. MMR 계산 전 경기 구조 검증 추가

### 대상 파일

- `src/mmr_refactor/mmr.py`
- `src/mmr_refactor/__init__.py`
- `tests/test_mmr.py`

### 대상 함수

- `validate_mmr_input_matches`
- `update_mmr_elo`

### 기존 문제

`update_mmr_elo()`는 `replay_code` 단위로 경기 데이터를 순회하면서 같은 포지션의 상대를 찾는다.

기존 구현은 입력 데이터가 정상적인 10명 경기라는 전제를 가지고 있었다. 입력이 깨진 경우에는 다음 문제가 발생할 수 있었다.

- 경기 row 수가 10명이 아니어도 계산이 진행됨
- 특정 포지션에 1명 또는 3명 이상이 있어도 첫 번째 상대를 임의로 선택함
- 같은 포지션에 승자/패자가 1명씩 존재하지 않아도 계산이 진행됨
- 같은 유저가 한 경기 안에 중복 row로 들어와도 계산이 진행됨

### 수정 내용

`validate_mmr_input_matches()`를 추가하고 `update_mmr_elo()` 진입 시점에 호출하도록 변경했다.

검증 조건:

- 필수 컬럼 존재
- 입력 DataFrame이 비어 있지 않음
- `replay_code`별 row 수가 정확히 10개
- `game_result` 값이 0 또는 1
- 같은 경기 안에서 `puuid` 중복 없음
- 각 `replay_code + position` 조합이 정확히 2개 row를 가짐
- 각 `replay_code + position` 조합에 승자 1명, 패자 1명이 존재

### 수정 이유

MMR은 누적 점수이므로 잘못된 입력으로 계산을 진행하는 것보다 초기에 중단하는 것이 안전하다.

정상 데이터의 계산식은 바꾸지 않고, 깨진 경기 구조가 들어왔을 때 잘못된 MMR 결과가 저장되는 것을 막았다.

## 3. 기본 feature 생성 로직 분리

### 대상 파일

- `src/mmr_refactor/features.py`
- `scripts/main_pipeline.py`
- `src/mmr_refactor/__init__.py`
- `tests/test_main_pipeline.py`

### 대상 함수

- `add_basic_features`
- `select_available_metrics`

### 기존 문제

`scripts/main_pipeline.py` 안에 MMR pipeline 실행 로직과 기본 파생 feature 생성 로직이 같이 있었다.

이 구조에서는 다음 문제가 있었다.

- feature 생성 로직을 테스트하거나 재사용할 때 script 모듈에 의존해야 함
- 추후 API 서버나 배치 작업에서 같은 feature 생성 로직을 쓰기 어려움
- pipeline orchestration 코드와 순수 계산 코드의 책임이 섞임

### 수정 내용

기본 metric 목록과 feature 생성 함수를 `src/mmr_refactor/features.py`로 분리했다.

분리한 항목:

- `BASE_METRICS`
- `add_basic_features`
- `select_available_metrics`

`main_pipeline.py`는 이제 feature를 직접 정의하지 않고 패키지 모듈에서 import해서 사용한다.

### 수정 이유

feature 생성은 MMR 계산 전처리의 일부이므로 `scripts`가 아니라 `src/mmr_refactor` 패키지에서 관리하는 것이 맞다.

이 변경으로 DB 테스트, API 연동, 배치 실행이 같은 feature 생성 함수를 공유할 수 있다.

## 4. position weight 학습과 적용 경계 분리

### 대상 파일

- `src/mmr_refactor/game_impact.py`
- `scripts/main_pipeline.py`
- `src/mmr_refactor/__init__.py`
- `tests/test_game_impact.py`

### 대상 함수

- `derive_position_weights`
- `resolve_position_weights`

### 기존 문제

기존 pipeline은 실행할 때마다 현재 입력 데이터로 position별 RandomForest feature importance를 새로 학습했다.

```python
position_weights = derive_position_weights(feature_df, metrics=metrics)
```

이 구조에서는 테스트나 운영에서 고정 weight를 적용하기 어렵다.

예를 들어 추후 다음 요구가 생기면 pipeline 내부를 직접 수정해야 했다.

- 검증된 weight 테이블을 DB에서 읽어서 적용
- 특정 버전의 weight를 운영에 고정
- API에서 받은 weight를 사용
- 학습 단계와 점수 계산 단계를 별도 배치로 분리

### 수정 내용

`resolve_position_weights()`를 추가했다.

동작 방식:

- `position_weights`가 전달되면 전달된 weight를 복사해서 그대로 사용
- `position_weights`가 없으면 기존처럼 `derive_position_weights()`로 현재 데이터에서 학습

`run_pipeline()`도 선택적으로 `position_weights`를 받을 수 있도록 변경했다.

### 수정 이유

현재 기본 동작은 유지하면서, weight 학습과 적용의 경계를 분리했다.

MMR 운영에서는 weight가 바뀌면 최종 점수도 바뀐다. 따라서 추후에는 학습된 weight를 별도 버전으로 관리하고, 계산 시점에는 특정 weight를 적용하는 방식이 더 적합하다.

이번 변경은 그 구조로 넘어가기 위한 최소 변경이다.

## 검증

실행한 검증:

```bash
python -m compileall src scripts
pytest tests -q -p no:cacheprovider
```

검증 결과는 작업 시점 기준으로 별도 커맨드 출력에서 확인한다.
