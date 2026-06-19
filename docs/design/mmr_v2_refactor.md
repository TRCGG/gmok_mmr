# 설계: MMR 산식 v2 리팩토링 (팀 평균 Elo + robust-z 퍼포먼스 + 승부격차)

> **상태**: 설계(draft) — 구현 전. CLAUDE.md 워크플로우(설계 → docs → 구현 → docs)의 1·2단계.
> **브랜치**: `feat/game-impact-position-balance`
> **작성 기준**: 2026-06-19 현재 `src/mmr` 소스 + [MMR 산식 문서](../MMR_산식_문서.md) + [`mmr_participant_metric` DDL](../mmr_pariticipant_metric_ddl.sql).
> **성격**: **전 모듈을 새 산식으로 교체하는 대규모 변경.** 모든 MMR 결과 수치가 바뀐다.
> **관계**: 본 설계는 이전 v1 진단(Game Impact 산식의 부호·스케일·RF importance 결함)을 **흡수**한다. 해당 결함은 v2에서 robust-z 퍼포먼스 점수로 전면 대체되어 해소된다.

---

## 0. 확정된 의사결정 (사용자 확인 완료, 2026-06-19)

| # | 결정 | 값 |
|---|---|---|
| D1 | v1과의 관계 | **in-place 교체** — `src/mmr`를 v2 산식으로 직접 교체. v1 산식 코드는 제거. |
| D2 | 운영 경로 | **증분 단일경기 계산 유지** — baseline 저장 + 3-API(baseline/full/single) 구조 유지. baseline에 robust-z·blowout 기준통계 저장. |
| D3 | 내부 컬럼명 | **DDL(`mmr_participant_metric`) 기준 정렬** — 내부 파이프라인은 DDL 컬럼명 사용. |
| D4 | 계정 통합 | **백엔드 책임** — 부계정→메인 병합은 백엔드가 데이터 저장 시점에 처리해 **이미 병합된 행**을 보낸다. gmok_mmr은 계정 통합 로직을 갖지 않는다. |

---

## 1. v1 → v2 산식 변경 요약

| 영역 | v1 (현재) | v2 (새 산식) |
|------|-----------|--------------|
| 퍼포먼스 | RandomForest `feature_importance` 가중합 (부호 없음·스케일 불일치·표본 노이즈) | **포지션별 robust z-score**(중앙값/IQR clip[−3,3]) 가중합 → 전역 재표준화 `perf_z` clip[−2.5,2.5] |
| 정규화 | MinMax 0~100 + (position×승패) Quantile→MinMax + 인분 + vs_opponent | (없음 — perf_z가 대체) |
| Elo | 포지션별 1:1, `personal_factor·relative_factor` | **팀 5인 평균 Elo** 기대승률 |
| K-factor | `BASE_WIN=20`/`BASE_LOSS=-15` 비대칭 + MMR decay + 클램프(±12~30) | `K = 32 × 배치(×1.5) × 퍼포먼스(1±0.35·tanh) × 승부격차(1+0.25·blow)`, `K=max(K,4)` |
| 승부격차 | 없음 | **blowout**: 팀 골드차 + 게임시간 robust 표준화 → tanh[−1,1] |
| 점수 갱신 | Δ를 포지션 MMR에만 누적, total = 포지션 MMR 경기수 가중평균 | `Δ = K·(s−E)`를 **total_mmr과 line_mmr[pos]에 동시 누적** |
| 초기 MMR | 1300 | **1500** |
| 랭킹 컷 | 없음(요약만) | **20판 컷** → 정식 / 배치중(provisional) 구분 |
| 계정 통합 | 없음 | 부계정 puuid → 메인 puuid 치환(Elo 이전) |

### 1.1 하이퍼파라미터 (산식 문서 §2)

| 코드명 | 값 | 의미 |
|--------|-----|------|
| `INIT_MMR` | 1500 | 신규 시작 MMR |
| `K_BASE` | 32 | 기본 K-factor |
| `SCALE` | 400 | Elo 로지스틱 스케일 |
| `PERF_GAIN` | 0.35 | 퍼포먼스 K 조정 최대비율 |
| `BLOWOUT_GAIN` | 0.25 | 승부격차 K 조정 최대비율 |
| `PROV_GAMES` | 10 | 배치 경기 수 |
| `PROV_MULT` | 1.5 | 배치 K 배수 |
| `CUT` | 20 | 정식 랭킹 최소 경기수 |

---

## 2. 모듈 구조 (in-place 교체)

메달리온 아키텍처(silver→gold→serving)는 유지하고 내용물을 교체한다.

```
src/mmr/
├── silver/
│   ├── cleaning.py       # (수정) DDL 컬럼 기준 정제 + 계정 통합(부계정→메인)
│   ├── features.py       # (수정) DDL 파생 feature, perf/blowout 입력 지표 정의
│   └── performance.py    # (신규, game_impact.py를 git mv 후 전면 재작성)
│                         #   robust-z perf_z + blowout 강도
├── gold/
│   ├── baseline.py       # (수정) v2 baseline = perf-z params + blowout params + 재표준화 stats
│   └── mmr.py            # (수정) 팀평균 Elo + K보정 + Δ(total·line 동시)
└── serving/
    ├── service.py        # (수정) 3-API 와이어 ↔ 내부 변환
    ├── schemas.py        # (수정)
    └── api_server.py     # (대체로 유지)
```

- `silver/game_impact.py` → `silver/performance.py`로 **`git mv` 후 내용 재작성**(이력 보존, CLAUDE.md 규칙).
- 제거 대상 공개 심볼: `derive_position_weights`, `resolve_position_weights`, `compute_raw_game_impact`, `normalize_minmax_0_100`, `normalize_by_position_outcome`, `compute_n_person_contribution`, `compute_vs_opponent`, `OutcomeNormalizationStats`, `GameImpactBaseline`. → `mmr/__init__.py`·`silver/__init__.py` 재노출 목록 갱신.

---

## 3. 단계별 구현 명세

산식 문서 §3의 단계(0~3-5)를 코드 함수로 매핑한다.

### 3-0. 정제 · 계정 통합 (`silver/cleaning.py`)

- 유효 경기 필터: `is_mmr_eligible == True AND is_deleted == False`.
- 5v5 구조 검증(`drop_invalid_matches`)은 유지하되 DDL 컬럼명(`custom_match_id`, `position`, `game_result`) 기준.
- **계정 통합은 하지 않는다 (D4)**: 부계정→메인 병합은 백엔드가 저장 시점에 끝내고 이미 병합된 행을 보낸다. gmok_mmr은 받은 `puuid`를 그대로 신뢰한다.
- `game_duration`(초) → 분 변환은 blowout·perf 입력에서 분 단위가 필요한 지표에만. (DDL은 초 단위 `game_duration` + 이미 분환산된 `*_per_min` 컬럼 동시 보유 → 가능하면 DDL 사전계산 컬럼 사용.)

### 3-1. 퍼포먼스 점수 `perf_z` (`silver/performance.py`)

**(1) robust z** — 포지션별 모집단 내:
```
robust_z(x) = clip( (x − median_pos(x)) / (Q3_pos(x) − Q1_pos(x)), −3, +3 )
```
IQR==0이면 std로 대체. (median/IQR은 baseline에 저장 → 증분 시 재사용, D2.)

**(2) 가중 합산** `raw_perf = Σ w_feat · robust_z(feat)`. 지표·가중치는 산식 문서 §3-1과 동일:

| 분류 | 지표(DDL 컬럼) · 가중치 |
|------|--------------------------|
| 공통 | `kda`(0.8), `dpm`(0.5), `gold_per_min`(0.4) |
| 라인전 | `lane_gold_diff`(0.8), `takedowns_before_15min`(0.7), `turret_plates_destroyed`(0.4) |
| TOP | `damage_to_champions`(0.4), `damage_self_mitigated`(0.3) |
| JUNGLE | `damage_to_objectives`(0.7), `dragon_kills`(0.4), `vision_score`(0.3) |
| MIDDLE | `damage_to_champions`(0.6), `cs_per_min`(0.3) |
| BOTTOM | `damage_to_champions`(0.7), `cs_per_min`(0.4) |
| UTILITY | `vision_score`(0.7), `heal_on_teammates`(0.3), `shield_on_teammates`(0.3), `cc_time`(0.3) |

> 모든 지표 DDL에 존재 확인 완료. 누락 컬럼은 0 처리(robust_z=0 기여).

**(3) 전역 재표준화** `perf_z = clip( (raw_perf − mean(raw_perf)) / std(raw_perf), −2.5, +2.5 )`.
- mean/std는 baseline 저장(증분 재사용).
- ⚠️ 산식 문서대로 **전역** 표준화. 포지션별 raw_perf 스케일 차이가 잔존할 수 있으나 문서 SoT를 따른다(잔여 편향은 검증 §7에서 재측정).

### 3-2. 승부격차 `blow` (`silver/performance.py`)

경기 단위 값(10명 공통):
```
gold_diff   = |Σ gold_earned(blue) − Σ gold_earned(red)|
blow_raw    = rz(gold_diff) − rz(game_duration)        # rz = robust z(전역)
blow        = tanh( clip( (blow_raw − mean)/std, −3, 3 ) )   # → [−1,1]
```
- `rz(gold_diff)`, `rz(duration)`의 median/IQR, `blow_raw`의 mean/std를 baseline 저장(증분 재사용).

### 3-3. 시간순 Elo 갱신 (`gold/mmr.py`)

`played_date` 순으로 경기 1판씩:

**(1) 기대승률** — 팀 5인 현재 **total_mmr** 평균:
```
E_blue = 1 / (1 + 10^((R_red − R_blue)/400)),  E_red = 1 − E_blue
```
**(2) 실제결과** `s`: 승팀 1, 패팀 0.

**(3) K 보정**:
```
K = 32
  × (1.5 if 누적경기 < 10 else 1.0)          # 배치
  × (1 + 0.35·tanh(perf_z)  if 승  else  1 − 0.35·tanh(perf_z))   # 퍼포먼스
  × (1 + 0.25·blow)                           # 승부격차
K = max(K, 4)
```
> 배치 누적경기 기준은 **total 누적경기**(라인 무관)로 해석. (열린 결정 Q1)

**(4) 갱신**:
```
Δ = K·(s − E)
total_mmr[player]      += Δ
line_mmr[player, pos]  += Δ
```
같은 Δ를 total과 해당 포지션 line에 **동시** 누적. (v1과 가장 큰 구조 차이: total이 독립 누적기가 됨.)

### 3-4. 결과 집계 (`gold/mmr.py`)

- 종합 MMR = 누적 total_mmr
- 종합 승률 = `100 × wins / total_games`
- 라인별 MMR/승률/게임수 = 포지션별 누적 line_mmr·승패·경기수
- 주 포지션 = 게임수 최다 포지션

### 3-5. 랭킹 컷 (`gold/mmr.py`)

- `total_games ≥ 20` → 정식, MMR 내림차순 순위 부여
- `< 20` → 배치중(`is_ranked=false`), 순위 미부여
- 요약(summary)에 `is_ranked`(또는 `status`) 필드 추가.

---

## 4. v2 baseline 구조 (증분 지원 핵심, D2)

증분 단일경기 계산이 전체 재계산과 **동일 결과**를 내려면(interface_spec §10), 전체 모집단 표준화 기준을 baseline에 고정 저장해야 한다.

```
PerformanceBaseline:
  robust_params:  { position: { metric: {median, iqr} } }   # 3-1(1)
  raw_perf_stats: { mean, std }                              # 3-1(3) 전역
BlowoutBaseline:
  gold_diff:  {median, iqr}                                  # 3-2 rz
  duration:   {median, iqr}                                  # 3-2 rz
  blow_raw:   {mean, std}                                    # 3-2 표준화
```

- 전체 baseline 계산(`/v1/mmr/baselines/calculate`) 시 위 통계를 산출·반환.
- 증분(`/v1/mmr/matches/calculate`) 시: 새 10행을 저장된 robust_params로 robust_z → raw_perf → raw_perf_stats로 perf_z; blowout도 저장된 stats로 변환. 그 뒤 `pre_match_user_summary`(현 상태)에 Elo Δ 적용.
- **계약 영향**: interface_spec §6 baseline 구조가 `position_weights`/`outcome_stats`/`f1_mean`/`f2_mean` → 위 구조로 **전면 교체**. §5.2의 `personal_factor`/`relative_factor`/`game_impact_*` 응답 필드도 v2에서 `perf_z`/`blow`/`expected_score` 등으로 재정의 필요. → **백엔드 합의 필수**(§6).

---

## 5. 컬럼 네이밍 3계층 정렬 정책

| 계층 | 예시 | 정책 |
|------|------|------|
| 와이어 계약 (interface_spec) | `kill`, `death`, `gold`, `total_damage_champions`, `time_played`, position `TOP/JUG/MID/ADC/SUP`, team `blue/red` | **SoT 미래 계약** — v2 산식이 요구하는 신규 지표(`takedowns_before_15min`, `damage_self_mitigated`, `damage_to_objectives`, `dragon_kills`, `turret_plates_destroyed` 등) 추가는 백엔드 합의 후 §3에 반영 |
| 내부 파이프라인 (DDL) | `kills`, `deaths`, `gold_earned`, `damage_to_champions`, `game_duration`, position `TOP/JUNGLE/MIDDLE/BOTTOM/UTILITY` | **D3: 내부 표준** |
| serving 변환 | `service._normalize_source_columns` | 와이어 → DDL-내부 매핑을 한곳에 집중 |

- 포지션 enum 불일치(`JUG/MID/ADC/SUP` ↔ `JUNGLE/MIDDLE/BOTTOM/UTILITY`)는 변환 테이블로 흡수.
- v1 내부명(`replay_code`, `played_at`, `gold`)은 DDL명(`custom_match_id`, `played_date`, `gold_earned`)으로 전면 치환.

---

## 6. 계약 영향 / 백엔드 합의 필요 항목

CLAUDE.md: interface_spec은 미래 계약(SoT)이라 임의로 현재 구현에 맞춰 덮어쓰지 않는다. v2는 **의도된 계약 변경**이므로 별도 합의 후 갱신한다.

1. **baseline payload 구조 교체** (§4) — `mmr_baseline`/`game_impact_baseline` → `performance_baseline`/`blowout_baseline`.
2. **match_results 응답 필드 재정의** (§5.2) — v1 factor 필드 → v2 `perf_z`/`blow`/`expected_score`/`mmr_change`.
3. **신규 입력 지표** (§5) — perf 산식이 요구하는 컬럼들을 Player-Game Row 필수/권장에 추가.
4. **summary `is_ranked`(20판 컷)** 필드 추가.
5. URL 버전: 파괴적 변경이므로 `/v2/` 승격 검토.

---

## 7. 검증 / 테스트

1. **골든 테스트**: 합성 경기 세트로 perf_z·blow·Elo Δ·summary를 단위 고정(리팩터 안전망). 산식 문서 §3 작동 예시(blow≈+0.91 / −0.95 등)를 케이스화.
2. **증분 = 전체 일치 테스트**: 동일 데이터에 대해 full 재계산과 single 반복호출 결과가 일치(interface_spec §10).
3. **포지션 균형 재측정**: 포지션별 MMR/perf_z 분포를 집계해 v2 결과의 포지션 편향 여부 확인(서폿 과대 해소).
4. **회귀**: `python -m pytest -q` 그린 유지. v1 산식 전제 테스트는 v2 기준으로 재작성/삭제(골든값 교체).
5. 산식 문서 §4 검증값(라인 골드차 vs 종합 MMR 상관 ≈0.78) 재현 여부 확인.

---

## 8. 결정 사항 (확정 + 검증)

확정된 가정과 검증 방법:

| 가정 | 결정 | 검증 |
|---|---|---|
| **배치(provisional) 기준** | **total 누적경기** (포지션별 아님) | `test_mmr.py::test_provisional_uses_total_games_not_position_games` — total 10경기면 신규 포지션 첫 경기도 비배치(K=32). |
| **전역 재표준화(3-1(3))** | 산식 문서대로 **전역** 유지 (v2 오리지널) | 합성 대칭 데이터에선 편향 없음(`test_global_restandardization_does_not_bias_positions`, 격차<0.5). **단, 실데이터(2,689경기)에선 경미한 서폿 편향 확인** — 아래 §8.1. |
| **포지션 enum** | 내부 DDL식(`JUNGLE/MIDDLE/...`), 와이어 계약식(`JUG/MID/...`) | `test_main_pipeline.py` 서비스 왕복(wire `JUG`→내부 `JUNGLE`→응답 `JUG`)으로 검증. |
| **계정 통합** | 백엔드 책임(D4), gmok_mmr 미처리 | — |
| **interface_spec 갱신** | 백엔드 합의 완료 → §6/§5 v2로 갱신 완료 | — |

> 전역 재표준화는 잔여 편향이 데이터로 확인되면 P1(포지션별 정규화)로 전환 가능(설계 여지 유지).

### 8.1 실데이터 검증 (2026-06-19, mmr_participant_metric 2,689경기 / 203 메인유저)

`tests/cli/build_v2_report.py`로 실데이터 전체 파이프라인 실행 결과:

- **파이프라인 정상**: 무효경기 0, perf_z∈[−2.5,2.5]/평균≈0, blow∈[−1,1]/평균≈0. 정식 144 / 배치중 59.
- **산식 검증 재현**: 라인 골드차 vs 종합 MMR 상관 = **0.760** (산식 문서 §4 ≈0.78 재현).
- **계정 통합**: participant의 `player_code`가 이미 부계정을 메인으로 해소(멀티계정 puuid 8건 → 메인 병합). 백엔드 책임(D4)과 일치.
- **⚠️ 경미한 서폿(UTILITY) 편향 확인**: 포지션 평균 MMR 격차 max−min = **20** (서폿 1506 vs 최저 1486). 원인은 서폿 전용 지표(`heal_on_teammates` rz평균 +0.49, `shield_on_teammates` +0.31)의 강한 우편향 → robust_z 평균이 +로 떠 전역 재표준화에서 서폿 perf_z를 끌어올림(서폿 perf_z 평균 +0.119).
- **P1 시뮬레이션**: 포지션별 재표준화 시 격차 **20 → 6**, 라인 상관 **0.760 → 0.765**(손실 없음). → **P1이 데이터상 정당**하나, 본 PR은 v2 오리지널(전역) 그대로 두고 **서폿 편향 보정은 다음 이터레이션으로 연기**(사용자 결정 2026-06-19).

---

## 9. 구현 상태 (2026-06-19)

**완료 (운영 패키지 `src/mmr` 전면 v2 교체):**

| 모듈 | 내용 |
|---|---|
| `silver/performance.py` | `game_impact.py` git mv 후 재작성. `perf_z`(robust-z 가중합+전역 재표준화), `blow`(골드차·시간 robust→tanh). `PerformanceBaseline`/`BlowoutBaseline` 저장·적용. |
| `silver/features.py` | DDL 컬럼명 기준 파생. 이미 있는 DDL 컬럼은 덮어쓰지 않음(`_ensure`). |
| `silver/cleaning.py` | `filter_eligible`(is_mmr_eligible/is_deleted), `custom_match_id` 기준 구조검증. 계정통합 미수행(D4). |
| `gold/mmr.py` | 팀 평균 Elo, K=32×배치×퍼포먼스×승부격차, Δ를 total·line 동시 누적(정수 상태). `is_ranked`(20판 컷)·`main_position` 요약. |
| `gold/baseline.py` | v2 `ServiceBaseline`(performance+blowout), payload 직렬화/역직렬화. |
| `serving/service.py` | 와이어↔내부 어댑터(`WIRE_TO_DDL_COLUMNS`, 포지션 enum 양방향), 3-API. |
| `serving/schemas.py` | v2 baseline/응답 모델로 갱신(초안). |
| 테스트 | `test_performance`/`test_mmr`/`test_baseline`/`test_silver`/`test_main_pipeline` v2 교체. **45 passed.** 증분=전체 일치 통합 테스트 포함. |

**완료 (계약·harness):**

- `interface_spec.md` — 백엔드 합의 완료 후 v2로 갱신(§3 입력 지표, §4.2/§5.1/§5.2 baseline·응답 필드, §6 baseline 구조). 와이어 URL은 `/v1/` 유지.
- `tests/harness/db_test/repository.py` — 원천 테이블 `mmr_participant_metric`(DDL)로 변경, `mpm.*` + `id AS match_participant_id`, read 단계 적격 필터.
- `tests/harness/db_test/baseline_repository.py` + `migrations/db_test/001` — baseline 키 `performance_baseline`/`blowout_baseline`로 교체.
- `migrations/007_recreate_mmr_result_tables_v2.sql` — 결과 테이블 v2 컬럼(custom_match_id/perf_z/blow/is_ranked 등) 재생성.
- harness 테스트(`test_repository`, `test_config_and_writer`) v2로 갱신. **전체 47 passed.**

> harness/db_test·migrations·CLI는 라이브 DB 없이 정적으로만 검증됨(코드/SQL 정합성). 실 DB 적용은 백엔드 연동 시 확인. CLAUDE.md상 백엔드 연동 후 삭제 대상.

**남은 후속:**

- 실데이터로 포지션 균형·라인골드차 상관(≈0.78) 재측정(§7).

## 10. 다음 단계

1. **서폿 편향 보정(P1)** — §8.1에서 정당성 확인됨(격차 20→6, 상관 유지). 다음 이터레이션에서 `raw_perf` 재표준화를 포지션별 mean/std로 전환하고 baseline에 포지션별 통계 저장.
2. 백엔드 연동 완료 시 harness/db_test·CLI 삭제.
