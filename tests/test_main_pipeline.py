"""serving 계층 통합 테스트: 와이어(interface_spec) → 내부 → MMR.

증분(단일경기) 반복 호출이 전체 재계산과 동일한 결과를 내는지(interface_spec §10)
서비스 레벨에서 검증한다.
"""

from __future__ import annotations

from mmr.serving.service import (
    calculate_baseline_payload,
    calculate_full_mmr,
    calculate_single_match_mmr,
)


WIRE_POSITIONS = ("TOP", "JUG", "MID", "ADC", "SUP")


def _wire_match(match_id: str, date: str, blue_wins: bool, seed: int) -> list[dict]:
    rows = []
    pid_counter = seed * 100
    for i, pos in enumerate(WIRE_POSITIONS):
        for team, base in (("blue", 1), ("red", 0)):
            win = (team == "blue") == blue_wins
            pid_counter += 1
            rows.append({
                "custom_match_id": match_id,
                "match_participant_id": pid_counter,
                "guild_id": "G1",
                "season": "2026",
                "puuid": f"{pos}_{team}",
                "champion_id": "1",
                "game_team": team,
                "position": pos,
                "game_result": 1 if win else 0,
                "played_date": date,
                "time_played": 1800 + i * 60 + base,
                "kill": 5 + i + base,
                "death": 3 + base,
                "assist": 7 + i,
                "gold": 12000 + i * 500 + (1500 if team == "blue" else 0),
                "ccing": 20 + i,
                "exp": 15000 + i * 100,
                "total_damage_champions": 18000 + i * 1000 + base * 500,
                "total_damage_taken": 22000 + i * 800,
                "vision_score": 20 + i * 2,
                "minions_killed": 150 + i * 5,
                "neutral_minions_killed": 10 + i,
                "wards_placed": 12 + i,
                "wards_killed": 4 + i,
                "time_spent_dead": 60 + i * 10,
                "heal_on_teammates": 100 * i,
                "shield_on_teammates": 50 * i,
                "damage_self_mitigated": 9000 + i * 300,
                "damage_to_objectives": 3000 + i * 200,
                "dragon_kills": i % 3,
                "takedowns_before_15min": 2 + i,
                "turret_plates_destroyed": i % 4,
            })
    return rows


def _two_matches() -> tuple[list[dict], list[dict]]:
    m1 = _wire_match("g1", "2026-01-01T10:00:00", blue_wins=True, seed=1)
    m2 = _wire_match("g2", "2026-01-02T10:00:00", blue_wins=False, seed=2)
    return m1, m2


def test_calculate_baseline_payload_structure():
    m1, m2 = _two_matches()
    payload = calculate_baseline_payload({
        "season": "2026",
        "baseline_version": "2026-06",
        "matches": m1 + m2,
    })
    assert payload["performance_baseline"]["robust_params"]
    assert payload["blowout_baseline"]["gold_diff"]
    assert payload["metadata"]["match_count"] == 2


def test_calculate_full_mmr_structure_and_direction():
    m1, m2 = _two_matches()
    baseline = calculate_baseline_payload({
        "season": "2026", "baseline_version": "2026-06", "matches": m1 + m2,
    })
    result = calculate_full_mmr({
        "guild_id": "G1", "season": "2026", "baseline_version": "2026-06",
        "matches": m1 + m2,
        "performance_baseline": baseline["performance_baseline"],
        "blowout_baseline": baseline["blowout_baseline"],
    })

    assert result["match_results"]
    assert result["user_summary"]
    # 응답 포지션은 와이어 enum으로 복원
    positions = {r["position"] for r in result["match_results"]}
    assert positions <= set(WIRE_POSITIONS)


def test_incremental_matches_full_recompute_at_service_level():
    m1, m2 = _two_matches()
    baseline = calculate_baseline_payload({
        "season": "2026", "baseline_version": "2026-06", "matches": m1 + m2,
    })
    perf_bl = baseline["performance_baseline"]
    blow_bl = baseline["blowout_baseline"]

    full = calculate_full_mmr({
        "guild_id": "G1", "season": "2026", "baseline_version": "2026-06",
        "matches": m1 + m2,
        "performance_baseline": perf_bl, "blowout_baseline": blow_bl,
    })

    # 증분 1: 빈 상태에서 g1
    single1 = calculate_single_match_mmr({
        "guild_id": "G1", "season": "2026", "baseline_version": "2026-06",
        "custom_match_id": "g1", "match_rows": m1,
        "performance_baseline": perf_bl, "blowout_baseline": blow_bl,
        "pre_match_user_summary": [],
    })
    # 증분 2: g1 이후 상태를 받아 g2
    single2 = calculate_single_match_mmr({
        "guild_id": "G1", "season": "2026", "baseline_version": "2026-06",
        "custom_match_id": "g2", "match_rows": m2,
        "performance_baseline": perf_bl, "blowout_baseline": blow_bl,
        "pre_match_user_summary": single1["updated_user_summary"],
    })

    inc_rows = single1["match_results"] + single2["match_results"]
    inc = {(r["custom_match_id"], r["puuid"]): r["total_mmr"] for r in inc_rows}
    full_map = {(r["custom_match_id"], r["puuid"]): r["total_mmr"] for r in full["match_results"]}

    assert inc == full_map
