# MMR 계산 로직 단계별 정리

> **목적**: `src/mmr`의 MMR 계산 파이프라인을 단계별로 설명한다. 각 단계의 입력/출력 컬럼, 산식, 관련 함수, 주의점을 정리한다.
> **검증 기준**: 2026-06-18 현재 `src/mmr` 소스 기준.
> **관련 문서**: 입력 테이블 구조는 [match_participant_metric_table_spec.md](match_participant_metric_table_spec.md), 컬럼 사용 현황은 [player_game_columns.md](player_game_columns.md), 백엔드 통신 계약은 [interface_spec.md](interface_spec.md).

---

## 0. 전체 흐름 한눈에

```text
raw player-game rows (한 경기 = 10 row)
  │
  ├─[1] clean_match_data        (silver.py)      정합성 클렌징, win→game_result, 초→분
  ├─[2] drop_invalid_matches    (silver.py)      5v5 구조 위반 경기 통째 제거
  ├─[3] add_basic_features      (features.py)    per-min / kda / lane_gold_diff 등 파생
  │
  ├─[4] Game Impact 산정        (game_impact.py)
  │     ├ position_weights        포지션별 RandomForest 중요도
  │     ├ raw_game_impact         포지션 가중합
  │     ├ game_impact             전체 MinMax 0~100
  │     ├ game_impact_winloss_norm  (position×승패) Quantile→MinMax
  │     ├ game_n_person_contribution  게임 내 인분(10인분 기준)
  │     └ game_impact_vs_opponent    동일 포지션 1:1 상대 비교 점수
  │
  ├─[5] baseline 통계            (mmr.py / baseline.py)  f1_mean, f2_mean
  │
  ├─[6] update_mmr_matches      (mmr.py)         ELO + 개인/상대 factor 로 포지션 MMR 갱신
  │
  └─[7] make_summary_df_wide    (mmr.py)         puuid별 total_mmr / 포지션별 요약
```

두 가지 실행 경로가 있다.

| 경로 | 진입 함수 | baseline | 용도 |
|---|---|---|---|
| **전체 계산** | `service.calculate_full_mmr` → `update_mmr_matches` | 입력 데이터에서 즉석 계산 or 주입 | 시즌 전체/RECALC |
| **단일 경기 증분** | `service.calculate_single_match_mmr` → `update_single_match_mmr` | **반드시 저장된 baseline 주입** | 경기 1건 추가 |

baseline을 주입하면 `apply_game_impact_baseline`이 [4]의 position_weights·정규화 기준을 **고정**해서 적용한다(매번 재학습 금지 → 증분과 전체 재계산 결과 일관성 유지).

---

## 1. 정합성 클렌징 — `clean_match_data`

**파일**: `mmr/silver/cleaning.py` · **입력**: raw DataFrame · **출력**: 클렌징된 DataFrame

적용 순서(원본 노트북과 동일):

1. **중복 행 제거** — `drop_duplicates()`
2. **`win` → `game_result`** — `win`이 있고 `game_result`가 없으면 `TRUE→1 / FALSE→0`으로 변환 후 `win` 컬럼 제거. (DB 로더가 이미 `game_result`를 주면 skip)
3. **서포트 지표 결측 → 0** — `heal_on_teammates`, `shield_on_teammates`의 NaN을 0으로
4. **`game_duration` 초→분** — `convert_duration_to_minutes=True`이면 `ROUND(game_duration / 60, 2)`

> ⚠️ `game_duration`이 이미 분 단위면 `convert_duration_to_minutes=False`로 호출. 이걸 틀리면 모든 per-min 지표가 60배 어긋난다.

---

## 2. 구조 검증 / 제거 — `drop_invalid_matches`

**파일**: `mmr/silver/cleaning.py`

5v5 구조가 아닌 경기는 `replay_code` 단위로 **통째 제거**한다. 하나라도 해당하면 제거:

1. 경기 총 row 수가 10이 아님
2. 포지션당 row 수가 정확히 2가 아님
3. 포지션당 (승자 1 + 패자 1) 구조가 아님 (`game_result` 합 ≠ 1)

제거된 경기는 콘솔에 `[drop_invalid_matches] ...`로 로깅된다. 전부 제거되면 상위 `build_base_feature_dataframe`에서 `RuntimeError`.

> MMR 계산 직전(`mmr.py validate_mmr_input_matches`)에 **동일 규칙 + puuid 중복 + game_result∈{0,1}**을 한 번 더 검증한다. 여기서 위반하면 제거가 아니라 `ValueError`로 중단된다.

---

## 3. 파생 feature — `add_basic_features`

**파일**: `mmr/silver/features.py`

안전 처리: `duration = game_duration.replace(0, NaN)`, `deaths_safe = deaths.replace(0, 1)`.

| 파생 컬럼 | 산식 | 조건 |
|---|---|---|
| `gold_per_min` | `gold / 분` | 항상 |
| `dpm` | `damage_to_champions / 분` | 항상 |
| `damage_taken_per_min` | `damage_taken / 분` | 항상 |
| `cc_time_per_min` | `cc_time / 분` | 항상 |
| `kda` | `(kills + assists) / deaths_safe` | 항상 |
| `damage_taken_per_death` | `damage_taken / deaths_safe` | 항상 |
| `damage_dealt_per_death` | `damage_to_champions / deaths_safe` | 항상 |
| `exp_per_min` | `exp / 분` | `exp` 있을 때 |
| `damage_to_turrets_per_min` | `damage_to_turrets / 분` | `damage_to_turrets` 있을 때 |
| `cs_per_min` | `(minions_killed + neutral_minions_killed) / 분` | 둘 다 있을 때 |
| `wards_placed_per_min` | `wards_placed / 분` | 있을 때 |
| `wards_killed_per_min` | `wards_killed / 분` | 있을 때 |
| `dead_time_pct` | `time_spent_dead / (분 * 60) * 100` | 있을 때 |
| `lane_gold_diff` | 같은 (replay_code, position) 상대 평균 gold와의 차 | 컬럼 없고 키 있을 때 |

마지막에 **`inf/-inf → NaN`, 그리고 모든 숫자 컬럼 `NaN → 0`** 처리.

**`lane_gold_diff` 상세** (`_compute_lane_gold_diff`):
```text
opponent_gold = (그룹 gold 합 - 본인 gold) / (그룹 인원 - 1)
lane_gold_diff = gold - opponent_gold     # 정상 5v5면 상대 1명과 1:1 차이
```

**`BASE_METRICS`** (Game Impact 입력 후보 19개): `kills, deaths, assists, gold_per_min, exp_per_min, dpm, damage_to_turrets_per_min, damage_taken_per_min, vision_score, cs_per_min, kda, damage_taken_per_death, damage_dealt_per_death, wards_placed_per_min, wards_killed_per_min, cc_time_per_min, heal_on_teammates, shield_on_teammates, lane_gold_diff`. 이 중 실제 DataFrame에 존재하는 것만 `select_available_metrics`로 추린다.

---

## 4. Game Impact 산정

**파일**: `mmr/silver/game_impact.py`. raw 스탯을 "이 경기에서 얼마나 잘했는가"를 나타내는 점수로 변환하는 단계.

### 4-1. 포지션별 가중치 — `derive_position_weights`

포지션마다 **별도 `RandomForestClassifier`** (`n_estimators=200`, `random_state=42`)를 학습해, `game_result`(승패)를 가장 잘 설명하는 metric의 `feature_importances_`를 가중치로 쓴다.

- 입력 metric은 `StandardScaler`로 표준화(원본 df는 미변경).
- 포지션별로 **승/패가 모두 있고**(클래스 ≥ 2) **표본 ≥ 5**여야 학습. 부족하면 그 포지션 제외(안내 출력).
- 반환: `DataFrame(index=metric, columns=position, values=importance)`, 빈 셀은 0.
- baseline 주입 시에는 학습 안 하고 저장된 weights를 그대로 사용(`resolve_position_weights`가 분기).

### 4-2. raw_game_impact — `compute_raw_game_impact`

row마다 자기 포지션의 가중치로 **metric 가중합**:
```text
raw_game_impact = Σ (metric_value × position_weight[metric])
```
포지션 가중치가 없으면 `NaN`.

### 4-3. game_impact — `normalize_minmax_0_100`

`raw_game_impact` 전체를 `MinMaxScaler(0~100)`로 스케일. (현재 MMR 변동에는 직접 안 쓰이고, 표시/분석용)

### 4-4. game_impact_winloss_norm — 정규화 (경로별 2가지)

(position × game_result) 그룹별로 `raw_game_impact`를 0~100으로 정규화한다. 승자끼리, 패자끼리 분리해 상대 비교의 기준을 만든다. 이 컬럼이 이후 인분/상대비교의 **기반 점수**다.

**(A) baseline 적용 경로 — 운영 기본** (`apply_game_impact_baseline` → `apply_outcome_normalization_stats`)

미리 계산해 저장한 baseline의 `outcome_stats`(그룹별 `lower`/`upper`)를 그대로 적용한다.
```text
(raw - lower) / (upper - lower) × 100   → [0, 100] 클립
```
- `outcome_stats`는 baseline 생성 시 이력 데이터의 5/95 분위로 미리 산출(`derive_outcome_normalization_stats`).
- **전체(RECALC)와 단일 경기 증분이 같은 기준을 써서 결과가 일치한다.** `calculate_full_mmr`, `calculate_single_match_mmr`, baseline f1/f2 계산이 모두 이 경로.

**(B) baseline 없는 레거시 경로** (`normalize_by_position_outcome`)

baseline을 전달하지 않는 옛날 배치(`tests/cli/main_pipeline.py`) 전용. 현재 데이터에서 그룹별로 즉석 정규화한다.
```text
각 (position, win/loss) 그룹:
  QuantileTransformer(output_distribution="normal", n_quantiles=min(n,1000)) → MinMaxScaler(0~100)
```
그룹 표본이 2개 미만이면 `NaN`(경고 출력). 단일 경기엔 그룹 분포가 없어 NaN이 되므로, 운영은 반드시 (A) 경로를 쓴다.

### 4-5. game_n_person_contribution (인분) — `compute_n_person_contribution`

게임 내 본인 비중 × 10. "10인분 중 몇 인분을 했나".
```text
game_n_person_contribution = winloss_norm / (게임 내 winloss_norm 합) × 10
```
합이 0이면 0. → **MMR 개인 factor의 f1**.

### 4-6. game_impact_vs_opponent — `compute_vs_opponent`

같은 (game, position)의 **승자 vs 패자 1:1** 점수 배분(0~100).
```text
total = winner_norm + loser_norm
winner_score = winner_norm / total × 100
loser_score  = loser_norm  / total × 100
```
매칭 안 되는 row는 `NaN`. → **MMR 상대 factor의 f2 + ELO 실제 성과(actual)**.

---

## 5. baseline 통계 — `MMRBaselineStats`

**파일**: `mmr/gold/mmr.py`. MMR factor를 "평균 대비"로 환산하기 위한 기준값.

```text
f1_mean = game_n_person_contribution.mean()   # 인분 평균
f2_mean = game_impact_vs_opponent.mean()       # 상대비교 평균
```

전체 계산은 입력 데이터에서 `MMRBaselineStats.from_df`로 즉석 계산하거나 주입. 단일 경기 증분은 **반드시 저장된 baseline 주입**(단일 경기로는 평균이 무의미하므로).

`ServiceBaseline`(`mmr/gold/baseline.py`)은 이 `mmr_baseline`(f1/f2 평균) + `game_impact_baseline`(weights + outcome_stats)를 묶어 payload로 직렬화/복원한다.

---

## 6. MMR 갱신 (ELO + factor) — `update_mmr_matches` → `_apply_mmr_game`

**파일**: `mmr/gold/mmr.py`. 경기를 **시간순**(`played_at, replay_code, puuid`)으로 순회하며 (puuid × position) MMR을 갱신한다. 각 경기 내부:

### 6-1. 경기 전 MMR 스냅샷
참가자 전원의 `(pid, pos)` 현재 MMR을 먼저 저장(같은 경기 내 동시 갱신 방지). 신규는 `INITIAL_MMR=1300`.

### 6-2. 플레이어별 변동량 계산

```text
opponent_mmr   = 같은 포지션 상대의 경기 전 MMR (없으면 1300)
expected       = 1 / (1 + 10^((opponent_mmr - current_mmr) / 400))     # ELO 기대 승률

actual         = game_impact_vs_opponent / 100   (NaN이면 expected로 대체)
relative_factor= actual / expected               (expected>0, 아니면 1)

personal_factor= f1^ALPHA × f2^BETA              # 아래 6-3
final_factor   = personal_factor × relative_factor^GAMMA

k              = calculate_k_factor(current_mmr)  # 아래 6-4

승리: delta = BASE_WIN(20)  × final_factor × k,  clip(max(delta,12),  12, MMR_MAX_CHANGE=30)
패배: delta = BASE_LOSS(-15)× final_factor × k,  clip(min(delta,-12), MMR_MIN_CHANGE=-25, -12)

delta   = round(delta)            # 정수
new_mmr = current_mmr + delta
```

즉 **이긴 사람은 최소 +12 ~ 최대 +30, 진 사람은 최소 -12 ~ 최대 -25**로 고정 범위 클램핑.

### 6-3. 개인 factor — `calculate_personal_factor`
```text
f1 = game_n_person_contribution / f1_mean    (f1_mean=0이면 1)
f2 = game_impact_vs_opponent / f2_mean        (NaN 또는 f2_mean=0이면 1)
f1, f2 ∈ clip[0.5, 2]
personal_factor = f1^ALPHA × f2^BETA
```

### 6-4. K factor — `calculate_k_factor`
MMR이 높을수록 변동폭 축소:
```text
mmr ≤ 1500:  k = 1.0
mmr > 1500:  k = 1.0 - (mmr - 1500) × 0.002,   하한 K_MIN=0.35
```

### 6-5. 결과 반영 & total MMR
경기 결과를 `MMRRuntimeState`에 반영하고 포지션 전적(win/total) 갱신. **total_mmr은 포지션별 경기수 가중평균**:
```text
total_mmr = round( Σ(pos_mmr × pos_games) / Σ(pos_games) )    # 전적 없으면 1300
```

각 row에 기록되는 컬럼: `pre_game_pos_mmr, expected_score, actual_score, relative_factor, personal_factor, final_factor, mmr_change, pos_cumulative_mmr, total_mmr`.

### 조정 가능 상수 (`MMRSettings`, 기본값)

| 상수 | 값 | 의미 |
|---|---|---|
| `BASE_WIN` / `BASE_LOSS` | 20 / -15 | 기본 변동량 |
| `ALPHA` / `BETA` / `GAMMA` | 0.6 / 0.4 / 0.2 | 개인 기여 / 상대 대비 / ELO 반영 지수 |
| `INITIAL_MMR` | 1300 | 신규 시작 MMR |
| `MMR_MIN_CHANGE` / `MMR_MAX_CHANGE` | -25 / 30 | 변동 클램프 |
| `MMR_K_DECAY_START` | 1500 | K 감쇠 시작 MMR |
| `MMR_K_DECAY_RATE` | 0.002 | K 감쇠율 |
| `MMR_K_MIN` | 0.35 | K 하한 |
| `DEFAULT_POSITIONS` | TOP/BOTTOM/MIDDLE/JUNGLE/UTILITY | 라이엇 원본 포지션 |

---

## 7. 요약 생성 — `make_summary_df_wide`

**파일**: `mmr/gold/mmr.py`. row 단위 결과를 puuid별 wide 요약으로 정리.

- **포지션별**: 마지막 경기 기준 `{POS}_mmr`(`pos_cumulative_mmr`의 최신값), `{POS}_winrate`(`pos_wins/pos_games×100`), `{POS}_games`.
- **전체**: `total_mmr`(최신), `total_games`, `overall_winrate`.
- 없는 포지션 컬럼은 `mmr/winrate=NaN`, `games=0`으로 채움.
- `total_mmr` 내림차순 정렬.

컬럼 순서: `puuid, total_mmr, total_games, overall_winrate, {각 포지션}_mmr/_winrate/_games`.

---

## 8. 입력 검증 규칙 — `validate_mmr_input_matches`

MMR 계산 직전 필수 검증(위반 시 `ValueError`):

- 필수 컬럼: `played_at, replay_code, puuid, position, game_result, game_impact_vs_opponent, game_n_person_contribution`
- 경기당 정확히 10 row
- `game_result` ∈ {0, 1}
- (replay_code, puuid) 중복 없음
- (replay_code, position)당 정확히 2 row
- (replay_code, position)당 승자 1 + 패자 1 (`game_result` 합 = 1)

---

## 9. 결과 저장 시 처리 — `data_writer._stamp`

DB 저장 직전(`tests/harness/data_writer.py` — 운영이 아닌 **테스트 하네스**. 운영에서는 결과를 API 응답으로 반환한다):
- 컬럼명 소문자화
- `player_game_id` 컬럼 drop
- **float 컬럼만 소수점 2자리 반올림** (파생 입력이 아니라 *결과* 한정)
- `calculated_at` (UTC now) 추가
- 대상 테이블에 실제 존재하는 컬럼만 남겨 append (`_align_to_table_columns`)

---

## 부록: 핵심 함수 맵

| 단계 | 함수 | 파일 |
|---|---|---|
| 클렌징 | `clean_match_data`, `drop_invalid_matches` | mmr/silver/cleaning.py |
| 파생 feature | `add_basic_features`, `select_available_metrics` | mmr/silver/features.py |
| 포지션 가중치 | `derive_position_weights`, `resolve_position_weights` | mmr/silver/game_impact.py |
| Game Impact | `compute_raw_game_impact`, `normalize_minmax_0_100`, `normalize_by_position_outcome`, `compute_n_person_contribution`, `compute_vs_opponent` | mmr/silver/game_impact.py |
| baseline 적용 | `GameImpactBaseline`, `apply_game_impact_baseline`, `derive/apply_outcome_normalization_stats` | mmr/silver/game_impact.py |
| baseline 조립 | `calculate_service_baseline`, `service_baseline_to_payload` | mmr/gold/baseline.py |
| MMR 갱신 | `update_mmr_matches`, `update_single_match_mmr`, `_apply_mmr_game`, `calculate_personal_factor`, `calculate_k_factor`, `expected_performance` | mmr/gold/mmr.py |
| 요약 | `make_summary_df_wide` | mmr/gold/mmr.py |
| 검증 | `validate_mmr_input_matches` | mmr/gold/mmr.py |
| 서비스 진입 | `calculate_full_mmr`, `calculate_single_match_mmr`, `calculate_baseline_payload` | mmr/serving/service.py |
