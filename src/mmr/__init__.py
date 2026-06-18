"""MMR 계산 파이프라인 패키지 (운영용, API 전용).

데이터 엔지니어링 메달리온 아키텍처의 계산 계층만 포함한다.

- ``silver``  : 정합성 클렌징, 파생 feature, Game Impact 산정
- ``gold``    : baseline 통계, ELO 기반 MMR 갱신/요약
- ``serving`` : API service 함수, FastAPI 진입점, 요청/응답 스키마

운영에서는 백엔드 API가 HTTP로 raw 데이터를 전달하고, 계산 결과도 HTTP 응답으로
돌려받는다. DB 직접 접근/로컬 배치 같은 입출력 도구는 운영 패키지에 두지 않고
``tests/harness`` 로 분리한다.

하위 호환을 위해 자주 쓰는 공개 심볼을 패키지 최상위에서 재노출한다.
"""

from .silver import (
    BASE_METRICS,
    GameImpactBaseline,
    OutcomeNormalizationStats,
    add_basic_features,
    apply_game_impact_baseline,
    apply_outcome_normalization_stats,
    clean_match_data,
    compute_n_person_contribution,
    compute_raw_game_impact,
    compute_vs_opponent,
    derive_outcome_normalization_stats,
    derive_position_weights,
    find_rows_with_na,
    normalize_by_position_outcome,
    normalize_minmax_0_100,
    resolve_position_weights,
    select_available_metrics,
)
from .gold import (
    DEFAULT_MMR_SETTINGS,
    MMRBaselineStats,
    MMRRuntimeState,
    MMRSettings,
    ServiceBaseline,
    calculate_service_baseline,
    make_summary_df_wide,
    service_baseline_to_payload,
    update_mmr_elo,
    update_mmr_matches,
    update_single_match_mmr,
    validate_mmr_input_matches,
)
from .serving import (
    calculate_baseline_payload,
    calculate_full_mmr,
    calculate_single_match_mmr,
)

__all__ = [
    # silver
    "BASE_METRICS",
    "add_basic_features",
    "select_available_metrics",
    "clean_match_data",
    "find_rows_with_na",
    "GameImpactBaseline",
    "OutcomeNormalizationStats",
    "apply_game_impact_baseline",
    "apply_outcome_normalization_stats",
    "derive_outcome_normalization_stats",
    "derive_position_weights",
    "resolve_position_weights",
    "compute_raw_game_impact",
    "normalize_minmax_0_100",
    "normalize_by_position_outcome",
    "compute_n_person_contribution",
    "compute_vs_opponent",
    # gold
    "ServiceBaseline",
    "calculate_service_baseline",
    "service_baseline_to_payload",
    "DEFAULT_MMR_SETTINGS",
    "MMRBaselineStats",
    "MMRRuntimeState",
    "MMRSettings",
    "update_mmr_elo",
    "update_mmr_matches",
    "update_single_match_mmr",
    "make_summary_df_wide",
    "validate_mmr_input_matches",
    # serving
    "calculate_baseline_payload",
    "calculate_full_mmr",
    "calculate_single_match_mmr",
]
