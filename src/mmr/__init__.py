"""MMR 계산 파이프라인 패키지 (운영용, API 전용) — 산식 v2.

데이터 엔지니어링 메달리온 아키텍처의 계산 계층만 포함한다.

- ``silver``  : 적격 필터·클렌징, 파생 feature, 퍼포먼스(perf_z)·승부격차(blow) 산정
- ``gold``    : baseline 통계, 팀 평균 Elo 기반 MMR 갱신/요약
- ``serving`` : API service 함수, FastAPI 진입점, 요청/응답 스키마

운영에서는 백엔드 API가 HTTP로 raw 데이터를 전달하고, 계산 결과도 HTTP 응답으로
돌려받는다. DB 직접 접근/로컬 배치 같은 입출력 도구는 운영 패키지에 두지 않고
``tests/harness`` 로 분리한다.

하위 호환을 위해 자주 쓰는 공개 심볼을 패키지 최상위에서 재노출한다.
"""

from .silver import (
    BlowoutBaseline,
    DERIVED_METRICS,
    PerformanceBaseline,
    RobustParam,
    StandardizeParam,
    add_basic_features,
    all_perf_metrics,
    apply_performance_features,
    clean_match_data,
    compute_blowout,
    compute_perf_z,
    derive_blowout_baseline,
    derive_performance_baseline,
    drop_invalid_matches,
    filter_eligible,
    find_rows_with_na,
    position_metric_weights,
)
from .gold import (
    DEFAULT_MMR_SETTINGS,
    MMRRuntimeState,
    MMRSettings,
    ServiceBaseline,
    blowout_baseline_from_payload,
    blowout_baseline_to_payload,
    calculate_k_factor,
    calculate_service_baseline,
    expected_performance,
    make_summary_df_wide,
    performance_baseline_from_payload,
    performance_baseline_to_payload,
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
    "add_basic_features",
    "DERIVED_METRICS",
    "clean_match_data",
    "filter_eligible",
    "drop_invalid_matches",
    "find_rows_with_na",
    "PerformanceBaseline",
    "BlowoutBaseline",
    "RobustParam",
    "StandardizeParam",
    "all_perf_metrics",
    "position_metric_weights",
    "apply_performance_features",
    "compute_perf_z",
    "compute_blowout",
    "derive_performance_baseline",
    "derive_blowout_baseline",
    # gold
    "ServiceBaseline",
    "calculate_service_baseline",
    "service_baseline_to_payload",
    "performance_baseline_to_payload",
    "performance_baseline_from_payload",
    "blowout_baseline_to_payload",
    "blowout_baseline_from_payload",
    "DEFAULT_MMR_SETTINGS",
    "MMRRuntimeState",
    "MMRSettings",
    "calculate_k_factor",
    "expected_performance",
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
