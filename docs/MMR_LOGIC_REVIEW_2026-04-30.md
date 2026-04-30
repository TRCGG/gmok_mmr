# MMR 로직 리뷰 기록 - 2026-04-30

## 목적

MMR 계산 로직을 점검하면서 발견한 정확도 이슈와 수정 이유를 기록한다.

이 문서는 단순 작업 로그가 아니라, MMR 점수에 영향을 줄 수 있는 계산 로직 변경의 근거를 남기기 위한 문서다.

## 1. 상대 포지션 비교 지표 index 보존

### 대상 파일

- `src/mmr_refactor/game_impact.py`

### 대상 함수

- `compute_vs_opponent`

### 기존 문제

`compute_vs_opponent()`는 같은 경기, 같은 포지션의 승자와 패자를 매칭해서 `game_impact_vs_opponent` 값을 계산한다.

기존 구현은 내부에서 새 DataFrame을 만든 뒤 아래 형태로 Series를 반환했다.

```python
return merged_back["game_impact_vs_opponent"].rename("game_impact_vs_opponent")
```

이 반환값은 원본 DataFrame의 index가 아니라 새로 생성된 `RangeIndex`를 가진다.

파이프라인에서는 이 값을 다시 원본 DataFrame에 대입한다.

```python
feature_df["game_impact_vs_opponent"] = compute_vs_opponent(feature_df)
```

pandas는 Series를 DataFrame 컬럼에 대입할 때 위치 기준이 아니라 index 기준으로 값을 정렬한다.

따라서 `feature_df`의 index가 기본 `0..n-1` 형태가 아니면 다음 문제가 발생할 수 있다.

- 계산된 상대 비교 점수가 다른 row에 들어갈 수 있음
- 일부 row가 NaN으로 들어갈 수 있음
- 이후 MMR 계산이 잘못된 상대 비교 점수를 기반으로 진행될 수 있음

### 영향 범위

`game_impact_vs_opponent`는 MMR 계산에서 직접 사용된다.

관련 계산:

- `actual_score`
- `personal_factor`
- `relative_factor`
- `final_factor`
- `mmr_change`

따라서 이 문제는 단순 표시 오류가 아니라 최종 MMR 변화량에 영향을 줄 수 있는 계산 정확도 문제다.

### 수정 내용

원본 row index를 `_row_id`로 보존하도록 변경했다.

수정 흐름:

1. `df_comp` 생성 시 원본 index를 `_row_id` 컬럼으로 저장
2. winner/loser 매칭 결과를 만들 때 각각의 `_row_id`를 같이 전달
3. 최종 Series를 `_row_id` 기준으로 재구성
4. 반환 전 원본 `df.index`로 `reindex`

수정 후 반환값은 항상 입력 DataFrame과 같은 index를 가진다.

```python
compute_vs_opponent(df).index == df.index
```

### 추가 테스트

파일:

- `tests/test_game_impact.py`

추가한 테스트:

- `test_compute_vs_opponent_preserves_original_index`

검증 내용:

- 원본 DataFrame이 `[101, 205]` 같은 비연속 index를 가져도 반환 Series가 같은 index를 유지하는지 확인
- 각 index에 기대한 상대 비교 점수가 들어가는지 확인

### 검증 결과

```bash
pytest tests/test_game_impact.py -q -p no:cacheprovider
```

결과:

```text
6 passed
```

전체 테스트:

```bash
pytest tests -q -p no:cacheprovider
```

결과:

```text
20 passed
```

## 결론

이번 변경은 점수 산식 자체를 바꾼 것이 아니다.

기존 산식에서 계산한 값을 원본 row에 안정적으로 매핑하도록 보정한 변경이다. 따라서 의도한 정상 케이스에서는 값이 동일해야 하며, index가 보존된 DataFrame이 입력될 때 발생할 수 있는 오정렬 문제를 제거한다.

## 2. MMR 계산 전 경기 구조 검증 추가

### 대상 파일

- `src/mmr_refactor/mmr.py`
- `src/mmr_refactor/__init__.py`

### 대상 함수

- `validate_mmr_input_matches`
- `update_mmr_elo`

### 기존 문제

`update_mmr_elo()`는 `replay_code` 단위로 경기 데이터를 순회하면서 같은 포지션의 상대를 찾는다.

기존 구현에서는 같은 경기/포지션의 상대를 아래 방식으로 선택했다.

```python
opponent_df = game_df[
    (game_df["position"] == pos) & (game_df["puuid"] != pid)
]
opp_id = opponent_df.iloc[0]["puuid"]
```

이 방식은 입력 데이터가 정상적인 10인 경기라는 전제를 가진다.

하지만 입력 데이터가 깨져 있으면 다음 문제가 발생할 수 있다.

- 경기 row 수가 10명이 아닌데도 MMR 계산이 진행됨
- 특정 포지션에 1명 또는 3명 이상이 있어도 첫 번째 상대를 임의로 선택함
- 같은 포지션에 승자/패자가 1명씩 존재하지 않아도 계산이 진행됨
- 같은 유저가 한 경기 안에 중복 row로 들어와도 계산이 진행됨

이 경우 MMR 변화량이 데이터 오류에 의해 왜곡될 수 있다.

### 영향 범위

검증 대상은 MMR 계산 진입점이다.

`update_mmr_elo()`는 이제 계산 전에 `validate_mmr_input_matches(df)`를 호출한다.

검증 조건:

- 필수 컬럼 존재
- 입력 DataFrame이 비어 있지 않음
- `replay_code`별 row 수가 정확히 10개
- `game_result` 값이 0 또는 1
- 한 경기 안에서 같은 `puuid`가 중복되지 않음
- 각 `replay_code + position` 조합이 정확히 2개 row를 가짐
- 각 `replay_code + position` 조합에 승자 1명, 패자 1명이 존재

### 수정 내용

새 함수 `validate_mmr_input_matches()`를 추가했다.

검증 실패 시 조용히 계산하지 않고 `ValueError`를 발생시킨다.

오류 메시지에는 잘못된 경기나 포지션의 샘플을 포함한다. 운영 중 데이터 문제를 추적하기 위한 목적이다.

### 추가 테스트

파일:

- `tests/test_mmr.py`

추가/변경한 테스트:

- `test_validate_mmr_input_matches_accepts_valid_ten_player_match`
- `test_validate_mmr_input_matches_rejects_incomplete_match`
- `test_validate_mmr_input_matches_rejects_position_without_winner_and_loser`

기존 MMR 업데이트 테스트도 2명짜리 최소 fixture에서 10명짜리 정상 경기 fixture로 변경했다.

### 기대 효과

이 변경은 정상 데이터의 MMR 산식을 바꾸지 않는다.

대신 잘못된 경기 구조가 들어왔을 때 임의 opponent 선택으로 MMR을 계산하는 문제를 차단한다. MMR은 누적 점수이므로, 입력 데이터 오류를 초기에 중단시키는 편이 잘못된 누적 결과를 저장하는 것보다 안전하다.
