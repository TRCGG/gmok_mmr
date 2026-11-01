from __future__ import annotations

from datetime import datetime, timedelta

import pandas as pd

from mmr.gold.report import (
    build_mmr_history,
    build_user_position_report,
    filter_active_guild_members,
)


def _report_rows(user_count: int = 5, games: int = 20) -> pd.DataFrame:
    rows = []
    start = datetime(2026, 1, 1)
    for user_index in range(user_count):
        for game_index in range(games):
            score = 100 + user_index * 100
            rows.append(
                {
                    "guild_id": "guild-1",
                    "player_code": f"alt-{user_index}",
                    "mmr_player_account": f"main-{user_index}",
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


def test_history_uses_main_account_and_keeps_game_mmr():
    history = build_mmr_history(_report_rows(user_count=1, games=2))

    assert history["player_code"].tolist() == ["main-0", "main-0"]
    assert history["mmr"].tolist() == [1300, 1301]


def test_position_report_classifies_with_five_eligible_users():
    report = build_user_position_report(_report_rows())
    strongest = report.loc[report["player_code"].eq("main-4")].iloc[0]

    assert strongest["games"] == 20
    assert strongest["reference_users"] == 5
    assert strongest["base_style"] == "생존형 딜러"
    assert strongest["position_style"] == "사이드 운영형 탑"


def test_position_report_holds_style_when_reference_group_is_too_small():
    report = build_user_position_report(_report_rows(user_count=4))

    assert set(report["base_style"]) == {"분류 준비 상태"}
    assert set(report["position_style"]) == {"분류 준비 상태"}
    assert set(report["reference_users"]) == {4}


def test_report_migration_contains_required_unique_keys():
    sql = open(
        "migrations/006_create_mmr_report_tables.sql", encoding="utf-8"
    ).read()

    assert "CREATE TABLE IF NOT EXISTS mmr_history" in sql
    assert "UNIQUE (guild_id, player_code, position, replay_code)" in sql
    assert "CREATE TABLE IF NOT EXISTS mmr_user_position_summary" in sql
    assert "UNIQUE (guild_id, player_code, position)" in sql


def test_active_member_filter_merges_alt_account_and_excludes_departed_member():
    report = build_user_position_report(_report_rows(user_count=2))
    members = pd.DataFrame(
        [
            {
                "guild_id": "guild-1",
                "account": "alt-active",
                "main_account": "main-0",
                "status": "1",
            },
            {
                "guild_id": "guild-1",
                "account": "main-1",
                "main_account": None,
                "status": "2",
            },
        ]
    )

    active = filter_active_guild_members(report, members)

    assert active["player_code"].tolist() == ["main-0"]
