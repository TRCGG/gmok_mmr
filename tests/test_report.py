from __future__ import annotations

from datetime import datetime, timedelta
from pathlib import Path

import pandas as pd

from mmr.gold.report import (
    attach_position_report,
    build_user_position_report,
)

ROOT = Path(__file__).resolve().parents[1]


def _report_rows(user_count: int = 5, games: int = 20) -> pd.DataFrame:
    rows = []
    start = datetime(2026, 1, 1)
    for user_index in range(user_count):
        for game_index in range(games):
            score = 100 + user_index * 100
            rows.append(
                {
                    "guild_id": "guild-1",
                    "player_code": f"player-{user_index}",
                    "position": "TOP",
                    "replay_code": f"game-{user_index}-{game_index}",
                    "played_at": start + timedelta(days=game_index),
                    "game_result": game_index % 2,
                    "pos_cumulative_mmr": 1300 + user_index * 10 + game_index,
                    "mmr_change": 1,
                    "game_impact": score,
                    "game_n_person_contribution": score,
                    "game_impact_vs_opponent": score,
                    "damage_taken_per_min": score,
                    "dpm": score,
                    "gold_per_min": score,
                    "damage_dealt_per_death": score,
                    "damage_taken_per_death": score,
                    "vision_score": score,
                    "cc_time_per_min": score,
                    "kda": score,
                    "cs_per_min": score,
                    "exp_per_min": score,
                }
            )
    return pd.DataFrame(rows)


def test_position_report_classifies_with_five_eligible_users():
    report = build_user_position_report(_report_rows())
    strongest = report.loc[report["player_code"].eq("player-4")].iloc[0]

    assert strongest["games"] == 20
    assert strongest["reference_users"] == 5
    assert strongest["base_style"] == "생존형 딜러"
    assert strongest["position_style"] == "사이드 운영형 탑"


def test_position_report_holds_style_when_reference_group_is_too_small():
    report = build_user_position_report(_report_rows(user_count=4))

    assert set(report["base_style"]) == {"분류 준비 상태"}
    assert set(report["position_style"]) == {"분류 준비 상태"}
    assert set(report["reference_users"]) == {4}


def test_report_migration_extends_existing_summary_with_json():
    sql = open(ROOT / "migrations/006_mmr_report_season_baseline.sql", encoding="utf-8").read()

    assert "ALTER TABLE mmr_user_summary" in sql
    assert "position_report JSONB" in sql
    assert "CREATE TABLE" not in sql
    assert "USING GIN" not in sql


def test_position_report_is_attached_to_every_summary_row():
    # 탈퇴자 판정 없이 결과가 있는 모든 계정의 summary를 유지한다.
    report = build_user_position_report(_report_rows(user_count=1))
    summary = pd.DataFrame(
        [
            {"guild_id": "guild-1", "player_code": "player-0", "total_mmr": 1300},
            {"guild_id": "guild-1", "player_code": "player-1", "total_mmr": 1400},
        ]
    )

    enriched = attach_position_report(summary, report)

    assert enriched["player_code"].tolist() == ["player-0", "player-1"]
    top_report = enriched.iloc[0]["position_report"]["TOP"]
    assert top_report["base_style"] == "분류 준비 상태"
    assert top_report["dpm"] == 100
    # 포지션 MMR·판수·승률은 요약 고정 컬럼에만 저장한다.
    assert not {"mmr", "games", "winrate"} & set(top_report)
    # 리포트가 없는 계정도 행은 남고 빈 JSON이다.
    assert enriched.iloc[1]["position_report"] == {}


def test_result_unique_key_migration_matches_replace_keys():
    sql = open(ROOT / "migrations/006_mmr_report_season_baseline.sql", encoding="utf-8").read()

    assert "ON mmr_match_results (guild_id, replay_code, player_code)" in sql
    # 시즌 이전 요약 키 (guild_id, player_code)는 만들지 않는다.
    assert "ON mmr_user_summary (guild_id, player_code)\n" not in sql
    assert "ON mmr_user_summary (guild_id, player_code);" not in sql


def test_season_migration_moves_summary_key_to_season():
    sql = open(ROOT / "migrations/006_mmr_report_season_baseline.sql", encoding="utf-8").read()

    assert "ADD COLUMN IF NOT EXISTS season VARCHAR(64) NOT NULL" in sql
    assert "DROP INDEX IF EXISTS uq_mmr_user_summary_guild_player;" in sql
    assert "ON mmr_user_summary (guild_id, player_code, season)" in sql
