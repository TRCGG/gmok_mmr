# MMR 로직 개선 보고서

> **작성 기준**: 2026-06-18 현재 `src/mmr` 소스.
> **목적**: 기존 MMR 계산 로직에서 손볼 만한 지점을 정리한다. 각 항목은 위치·현상·영향·제안과 함께, **MMR 결과 수치를 바꾸는지 여부**를 표시한다(이게 가장 중요한 구분이다).
> **원칙**: "수치 영향 없음"은 결과를 그대로 두는 안전한 리팩터, "수치 영향 있음"은 제품/운영 결정이 필요한 변경이다. 후자는 합의 없이 적용하지 않는다.

---

## 0. 한눈에 보기 (우선순위)

| # | 항목 | 분류 | 우선순위 | 수치 영향 |
|---|------|------|:---:|:---:|
| 1 | 클라이언트 데이터 오류가 HTTP 500으로 나감 | 정확성/API | 높음 | 없음 |
| 2 | `print()` → 구조적 로깅 전환 | 운영/유지보수 | 높음 | 없음 |
| 3 | `calculate_total_mmr`가 settings 대신 모듈 기본값 사용 | 일관성 | 높음 | 거의 없음* |
| 4 | 매직넘버(±12 floor, factor clamp 0.5~2)가 설정 밖 하드코딩 | 유지보수 | 중간 | 없음(설정화만) |
| 5 | 행 단위 루프(`apply`/`iterrows`) 벡터화 | 성능 | 중간 | 없음 |
| 6 | 포지션 상수 2곳 중복 정의 | 유지보수 | 중간 | 없음 |
| 7 | 구조 검증 로직 이원화(`drop_invalid_matches` vs `validate_*`) | 설계 | 중간 | 없음 |
| 8 | `game_impact`(0~100) 컬럼은 계산되나 MMR 미사용 | 명확성 | 낮음 | 없음 |
| 9 | NaN/결측 처리 일관성(`fillna(0)` 광범위, f2 처리 차이) | 모델 품질 | 중간 | **있음** |
| 10 | API 스키마 미연결 + 필드/enum adapter 부재 | 아키텍처 | 높음(운영 전) | 없음→있음 |
| 11 | 서비스/엔드포인트 레벨 테스트 공백 | 품질 | 중간 | 없음 |
| 12 | RandomForest 가중치의 소표본 불안정성 | 모델 설계 | 낮음 | **있음** |
| 13 | `tests/harness`(DB 직접 접근) 삭제 조건/일정 미명시 | 정리 | 낮음 | 없음 |

\* 정상 흐름에서는 거의 도달하지 않는 분기지만, 커스텀 settings 사용 시 불일치 가능.

---

## 1. 클라이언트 데이터 오류가 HTTP 500으로 나간다 — 높음 / 수치 영향 없음

**위치**: [serving/service.py:138](../src/mmr/serving/service.py#L138), [serving/service.py:154](../src/mmr/serving/service.py#L154) · [serving/api_server.py](../src/mmr/serving/api_server.py)

**현상**: 입력에 유효한 5v5 경기가 하나도 없거나 metric 컬럼이 없을 때 `RuntimeError`를 던진다. `api_server`는 `ValueError`만 400으로 매핑하고 그 외 예외는 500(`CALCULATION_FAILED`)으로 처리한다. 결과적으로 **"잘못된 입력"이 서버 내부 오류(500)로 보고**된다.

**영향**: 백엔드가 재시도/관리자 알림 정책을 5xx 기준으로 돌리면(인터페이스 정의서 §9), 사실상 데이터 문제인데 서버 장애처럼 처리된다.

**제안**: 입력 검증 실패는 `ValueError`(또는 `MMRInputError` 전용 예외)로 통일해 400/422로 매핑. 산식 내부 예외만 500. 인터페이스 정의서 §4.3/§5.3의 `error_code`(`INSUFFICIENT_DATA`, `INVALID_MATCH_STRUCTURE` 등)와 매핑 테이블을 추가.

---

## 2. `print()` 디버그 출력 → 구조적 로깅 — 높음 / 수치 영향 없음

**위치**: [silver/game_impact.py:104](../src/mmr/silver/game_impact.py#L104), [:113](../src/mmr/silver/game_impact.py#L113), [:222](../src/mmr/silver/game_impact.py#L222) · [silver/cleaning.py:105](../src/mmr/silver/cleaning.py#L105)

**현상**: 포지션 제외 안내, 정규화 스킵 경고, 제외 경기 목록을 `print()`로 stdout에 찍는다.

**영향**: 라이브러리/서비스 코드가 stdout을 오염시킨다. API 서버에서는 로그 레벨 제어·수집이 불가능하고, 경고가 응답 추적과 분리되지 않는다.

**제안**: 모듈별 `logging.getLogger(__name__)`로 전환(`warning`/`info`). 호출 측에서 레벨/핸들러 제어. 동작·수치 변화 없음.

---

## 3. `calculate_total_mmr`가 settings를 무시하고 모듈 기본값 사용 — 높음 / 수치 영향 거의 없음

**위치**: [gold/mmr.py:129](../src/mmr/gold/mmr.py#L129)

**현상**: 전적이 0인 분기에서 `DEFAULT_MMR_SETTINGS.initial_mmr`(모듈 전역)을 반환한다. `MMRRuntimeState`는 어떤 `MMRSettings`로 호출되든 이 전역값을 쓴다.

**영향**: `initial_mmr`을 커스텀 settings로 바꿔도 total MMR 계산이 1300을 고정 참조 → 설정 주입의 의미가 깨진다. 정상 경기 흐름에서는 도달하기 어려운 분기지만, `pre_match_user_summary`에 0게임 포지션이 있는 단일 경기 경로에서 노출될 수 있다.

**제안**: `MMRRuntimeState`가 생성 시 `settings`(또는 `initial_mmr`)를 보관하도록 하고 그 값을 사용. 기본값 사용 시 결과 동일.

---

## 4. 정책 매직넘버가 `MMRSettings` 밖에 하드코딩 — 중간 / 수치 영향 없음(설정화만)

**위치**: [gold/mmr.py:399](../src/mmr/gold/mmr.py#L399), [:402](../src/mmr/gold/mmr.py#L402) (승 +12 / 패 −12 하한) · [gold/mmr.py:171-172](../src/mmr/gold/mmr.py#L171-L172) (factor clamp `0.5~2`)

**현상**: `BASE_WIN/LOSS`, `min/max_change`, `alpha/beta/gamma`는 `MMRSettings`로 조정 가능한데, **변동 하한 ±12**와 **개인 factor clamp [0.5, 2]**는 함수 본문에 상수로 박혀 있다.

**영향**: MMR 정책을 튜닝/실험할 때 일부는 설정으로, 일부는 코드 수정으로 바꿔야 해서 일관성이 없고 실수하기 쉽다. 또 +12/−12는 `base_win/base_loss`와 의미가 겹쳐 혼동을 준다.

**제안**: `min_win_gain`(=12), `min_loss_drop`(=−12), `factor_clamp=(0.5, 2.0)`를 `MMRSettings`로 승격. 기본값을 현재값으로 두면 수치 불변.

---

## 5. 행 단위 파이썬 루프 벡터화 — 중간 / 수치 영향 없음

**위치**: [silver/game_impact.py:176](../src/mmr/silver/game_impact.py#L176) (`df.apply(_row_impact, axis=1)`), [:283](../src/mmr/silver/game_impact.py#L283) (`apply_outcome_normalization_stats`의 `iterrows`), [:389](../src/mmr/silver/game_impact.py#L389) (`compute_vs_opponent`의 `iterrows`)

**현상**: Game Impact 핵심 단계들이 행 단위 파이썬 루프로 구현됐다.

**영향**: 시즌 전체(수만 row) 계산 시 느리다. 특히 `compute_raw_game_impact`의 `apply(axis=1)`와 두 `iterrows`가 병목.

**제안**:
- `compute_raw_game_impact`: 포지션별 가중치를 정렬해 `(df[metrics] * weights)` 행렬 연산으로 대체.
- `apply_outcome_normalization_stats`: `(position, result)`별 `lower/upper`를 컬럼에 merge 후 벡터 산술.
- 동일 입력→동일 출력이 되도록 단위 테스트로 골든값 고정 후 교체. 수치 변화 없음(부동소수 미세차만 검증).

> 단, ELO 갱신(`_apply_mmr_game`)은 경기 순서 의존이라 본질적으로 순차다. 게임 단위 루프는 유지하되 게임 내부만 정리하는 선에서.

---

## 6. 포지션 상수 중복 정의 — 중간 / 수치 영향 없음

**위치**: [gold/mmr.py:40](../src/mmr/gold/mmr.py#L40) `DEFAULT_POSITIONS = (TOP, BOTTOM, MIDDLE, JUNGLE, UTILITY)` vs [silver/cleaning.py:70](../src/mmr/silver/cleaning.py#L70) `("TOP", "JUNGLE", "MIDDLE", "BOTTOM", "UTILITY")`

**현상**: 5개 포지션 집합이 두 곳에 따로 정의되어 있고 순서도 다르다.

**영향**: 포지션 enum이 바뀌면(예: 라이엇 표기→계약 표기 전환) 한 곳만 고칠 위험.

**제안**: 단일 상수(`POSITIONS`)를 공용 모듈에 두고 양쪽이 참조. 집합 비교라 순서 무관하지만 정의를 통일.

---

## 7. 구조 검증 로직 이원화 — 중간 / 수치 영향 없음

**위치**: [silver/cleaning.py `drop_invalid_matches`](../src/mmr/silver/cleaning.py) vs [gold/mmr.py `validate_mmr_input_matches`](../src/mmr/gold/mmr.py#L188)

**현상**: 같은 "10 row / 포지션 2개 / 승1패1" 규칙을 두 함수가 각각 구현한다. 하나는 **조용히 제외**, 하나는 **예외 발생**.

**영향**: 규칙이 갈라질 위험(한쪽만 수정), 그리고 "어디까지 허용/거부인지" 경계가 코드 두 곳에 흩어져 파악이 어렵다.

**제안**: 검증 규칙을 한 곳(예: `validation.py`)에 함수로 모으고, drop/raise는 그 규칙을 호출하는 얇은 래퍼로. 정책(제외 vs 거부)은 호출 측에서 선택.

---

## 8. `game_impact`(0~100) 컬럼은 MMR에 안 쓰이지만 계산된다 — 낮음 / 수치 영향 없음

**위치**: `normalize_minmax_0_100` 결과 `game_impact` (game_impact.py)

**현상**: MMR 변동은 `game_n_person_contribution`, `game_impact_vs_opponent`만 사용. `game_impact`는 표시/분석용 출력 컬럼.

**영향**: 핫패스에서 MinMax 스케일 1회가 불필요하게 돌고, "이 값이 MMR에 쓰이나?" 혼동을 준다.

**제안**: 용도를 주석/문서로 명시하거나, 출력에 필요 없으면 결과 직렬화 단계로 미룬다(미세 비용). 수치 불변.

---

## 9. 결측/NaN 처리 일관성 — 중간 / **수치 영향 있음(주의)**

**위치**: [silver/features.py `add_basic_features`](../src/mmr/silver/features.py) 말미의 `fillna(0)` · [gold/mmr.py `calculate_personal_factor`](../src/mmr/gold/mmr.py#L164) f2 NaN→1 · `MMRBaselineStats.from_df`의 `.mean()`(NaN skip)

**현상**:
- 모든 숫자 파생값의 결측을 일괄 `0`으로 채운다(예: 측정 안 된 지표가 0으로 둔갑 → RandomForest 가중치/impact에 영향).
- `game_impact_vs_opponent`가 NaN이면 per-row factor에서는 `1`로 취급하지만, baseline `f2_mean`은 NaN을 제외한 평균으로 계산 → 두 경로의 NaN 의미가 다르다.

**영향**: "결측"과 "진짜 0"을 구분하지 않아 모델 입력이 왜곡될 수 있고, NaN 정책 불일치가 미묘한 편향을 만든다. **고치면 결과 수치가 바뀐다.**

**제안**: 결측 정책을 명시적으로 설계(지표별 0 채움이 타당한지 검토, 필요 시 mask/결측 인디케이터). 변경은 수치에 영향을 주므로 baseline 재계산·검증을 동반하는 별도 과제로.

---

## 10. API 스키마 미연결 + 필드/enum adapter 부재 — 높음(운영 전) / 수치 영향 없음→있음

**위치**: [serving/schemas.py](../src/mmr/serving/schemas.py)(초안) · [serving/api_server.py](../src/mmr/serving/api_server.py)(raw dict 수신)

**현상**: 엔드포인트가 타입 없는 `dict` payload를 그대로 받는다. 스키마(초안)는 만들어 뒀지만 연결되지 않았고, 계약(`custom_match_id`/`kill`/`JUG·MID…`)과 계산 코어(`replay_code`/`kills`/`JUNGLE·MIDDLE…`)의 **필드명·enum 갭을 메우는 adapter가 없다**.

**영향**: 운영에서 백엔드와 실제로 계약대로 주고받으려면 변환 계층이 필수. 지금은 내부 컬럼명에 의존.

**제안**: ① 스키마 확정 → ② 엔드포인트 시그니처를 Pydantic 모델로 교체(검증 자동화) → ③ `adapter.py`에서 계약↔코어 필드/enum 매핑. enum 매핑(JUG↔JUNGLE 등)은 결과 자체는 안 바꾸지만, 잘못 매핑하면 수치가 틀어지므로 매핑 테이블 테스트 필수. (interface_spec.md가 기준 문서)

---

## 11. 서비스/엔드포인트 레벨 테스트 공백 — 중간 / 수치 영향 없음

**현상**: 단위 테스트는 silver/gold 함수 위주. `calculate_full_mmr`/`calculate_single_match_mmr` 같은 **서비스 e2e**, `api_server` 엔드포인트, `_normalize_source_columns`, schemas는 테스트가 없다.

**영향**: 페이로드 변환·증분 경로·에러 매핑 회귀를 잡지 못한다.

**제안**: 합성 10인 경기 payload로 `calculate_full_mmr` 골든 테스트, 단일 경기 증분 테스트, FastAPI `TestClient`로 엔드포인트(200/400/422/500) 테스트 추가.

---

## 12. RandomForest 포지션 가중치의 소표본 불안정성 — 낮음 / **수치 영향 있음**

**위치**: [silver/game_impact.py `derive_position_weights`](../src/mmr/silver/game_impact.py#L66)

**현상**: 포지션별 RandomForest `feature_importances_`를 가중치로 쓴다. 표본이 적은 시즌 초반/소규모 길드에서는 중요도가 노이즈에 민감하고, 트리 분할 특성상 상관 지표 간 중요도가 임의 분배된다.

**영향**: baseline마다 가중치가 흔들리면 Game Impact의 기준이 출렁인다. (baseline을 고정 저장·재사용하는 현재 설계가 이 위험을 일부 완화)

**제안**: 설계 한계로 문서화하고, 대안(정규화 회귀 계수, 도메인 고정 가중치, 또는 importance 평활/하한)을 별도 실험 과제로. 변경 시 수치 영향 큼 → 제품 결정 필요.

---

## 13. `tests/harness`(DB 직접 접근) 삭제 조건/일정 — 낮음 / 수치 영향 없음

**위치**: [tests/harness/](../tests/harness/), [tests/cli/](../tests/cli/)

**현상**: 백엔드 연동 전 임시 DB 입출력 도구. 각 파일 주석에 "연동 후 삭제"라고만 있고 **트리거 조건·담당·시점**이 없다.

**제안**: 삭제 기준(예: "백엔드 baseline 저장 API + raw-matches API 연동 완료")과 점검 항목을 이 보고서나 이슈로 명시. 운영 패키지(`src/mmr`)가 harness를 import하지 않는 현 상태를 회귀 테스트로 못박기.

---

## 부록: 권장 진행 순서

1. **안전 리팩터 먼저(수치 불변)**: 1(예외/에러매핑) → 2(로깅) → 6(상수 통일) → 4(설정화) → 3(total_mmr settings) → 5(벡터화, 골든값 고정 후).
2. **운영 준비**: 10(스키마 연결+adapter) → 11(서비스/엔드포인트 테스트).
3. **제품 결정 동반(수치 변동)**: 9(결측 정책), 12(가중치 모델) — baseline 재계산·검증 계획과 함께 별도 과제.
4. **정리**: 7(검증 일원화), 8(game_impact 용도 정리), 13(harness 폐기 조건).

> 5번(벡터화)과 1·2·3·4·6은 결과 수치를 바꾸지 않으므로 회귀 테스트만 통과하면 바로 적용 가능하다. 9·12는 MMR 점수가 달라지므로 반드시 합의 후 진행한다.
