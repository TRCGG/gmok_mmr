"""백엔드 <-> MMR 서비스 HTTP 요청/응답 스키마 (초안).

이 모듈은 백엔드(loltrix_be)와 주고받을 JSON 형태를 Pydantic 모델로 "미리" 잡아두기
위한 **초안**이다. 와이어 계약의 기준 문서는 `docs/interface_spec.md`이며, 본 모델은
그 계약을 대략적으로 옮긴 스케치 수준이다.

TODO(스키마 확정 전 미해결):
  - [ ] 아직 계약이 확정되지 않았다. 필드/타입은 interface_spec.md 기준으로 대략만 적음.
  - [ ] 식별자/필드명 갭: 계약은 `custom_match_id`/`kill`/`death`/`assist`를 쓰지만
        현재 계산 코어(`mmr.silver`, `mmr.gold`)는 `replay_code`/`kills`/`deaths`/`assists`를
        사용한다. 확정 시 service 레이어에 adapter(필드 매핑)를 둔다.
  - [ ] position enum 갭: 계약은 `TOP/JUG/MID/ADC/SUP`, 코어는 `TOP/JUNGLE/MIDDLE/BOTTOM/UTILITY`.
  - [ ] `mmr_history` 응답은 계약에만 있고 코어 미구현. 확정 후 추가.
  - [ ] 이 모델들을 `api_server.py` 엔드포인트 시그니처에 실제로 연결할지 결정.
        (현재 엔드포인트는 raw `dict` payload를 그대로 받는다.)
  - [ ] 에러 응답 포맷(`error_code`/`message`/`details`)과 검증 규칙 반영.
"""

from __future__ import annotations

from typing import Any, Literal

from pydantic import BaseModel, Field

# TODO: 계약 확정 시 enum으로 고정. 현재는 계약(interface_spec) 표기를 임시로 둔다.
Position = Literal["TOP", "JUG", "MID", "ADC", "SUP"]
GameTeam = Literal["blue", "red"]
GameResult = Literal[0, 1]


class PlayerGameRow(BaseModel):
    """경기 참가자 1명의 1경기 데이터 (한 경기 = 10 row).

    TODO: interface_spec.md §3 기준 초안. 권장 필드(누락 시 0)는 Optional로 둠.
    """

    custom_match_id: str
    match_participant_id: int
    guild_id: str
    season: str
    puuid: str
    champion_id: str
    game_team: GameTeam
    position: Position
    game_result: GameResult
    played_date: str  # TODO: ISO8601 datetime 타입으로 강화
    time_played: int

    kill: int
    death: int
    assist: int
    gold: int
    ccing: int
    exp: int
    total_damage_champions: int
    total_damage_taken: int
    vision_score: int

    # 권장(누락 시 0으로 간주) — TODO: 기본값/검증 정책 확정
    total_damage_dealt_to_buildings: int | None = None
    vision_bought: int | None = None
    minions_killed: int | None = None
    neutral_minions_killed: int | None = None
    wards_placed: int | None = None
    wards_killed: int | None = None
    time_spent_dead: int | None = None
    heal_on_teammates: int | None = None
    shield_on_teammates: int | None = None


class MMRBaselinePayload(BaseModel):
    """MMR 변동 factor 기준 통계. interface_spec.md §6."""

    f1_mean: float
    f2_mean: float
    # TODO: 키 추가만 허용, 제거/이름변경 금지 (안정성 정책)


class GameImpactBaselinePayload(BaseModel):
    """Game Impact 고정 baseline. interface_spec.md §6."""

    position_weights: dict[str, dict[str, float]]
    outcome_stats: list[dict[str, Any]]  # [{position, game_result, lower, upper}]


# ---------------------------------------------------------------------------
# API #1 — Baseline 계산
# ---------------------------------------------------------------------------
class BaselineCalculateRequest(BaseModel):
    season: str
    baseline_version: str
    min_match_count: int  # TODO: 미만이면 422 INSUFFICIENT_DATA
    matches: list[PlayerGameRow]


class BaselineCalculateResponse(BaseModel):
    season: str
    baseline_version: str
    mmr_baseline: MMRBaselinePayload
    game_impact_baseline: GameImpactBaselinePayload
    metadata: dict[str, Any]  # {match_count, player_game_row_count, calculated_at}


# ---------------------------------------------------------------------------
# API #2 — 단일 경기 MMR 계산 (incremental/RECALC 공용)
# ---------------------------------------------------------------------------
class UserPositionState(BaseModel):
    position: Position
    pos_mmr: int = 1300
    pos_games: int = 0
    pos_wins: int = 0


class PreMatchUserSummary(BaseModel):
    puuid: str
    positions: list[UserPositionState]


class MatchCalculateRequest(BaseModel):
    guild_id: str
    season: str
    calculation_id: str
    custom_match_id: str
    baseline_version: str
    mmr_baseline: MMRBaselinePayload
    game_impact_baseline: GameImpactBaselinePayload
    match_rows: list[PlayerGameRow] = Field(..., min_length=10, max_length=10)
    pre_match_user_summary: list[PreMatchUserSummary]


class MatchResultRow(BaseModel):
    custom_match_id: str
    match_participant_id: int
    puuid: str
    position: Position
    game_result: GameResult
    pre_game_mmr: int
    expected_score: float
    actual_score: float
    relative_factor: float
    personal_factor: float
    final_factor: float
    mmr_change: int
    post_game_mmr: int


class MatchCalculateResponse(BaseModel):
    guild_id: str
    season: str
    calculation_id: str
    custom_match_id: str
    baseline_version: str
    match_results: list[MatchResultRow]
    updated_user_summary: list[dict[str, Any]]
    mmr_history: list[dict[str, Any]]  # TODO: 코어 미구현 — 확정 후 모델화
    metadata: dict[str, Any]


# ---------------------------------------------------------------------------
# 공통 에러 응답 — interface_spec.md §7
# ---------------------------------------------------------------------------
class ErrorResponse(BaseModel):
    error_code: str
    message: str
    details: dict[str, Any] | None = None
