from __future__ import annotations

import pandas as pd
import pytest

from harness.db_test.account_mapping import attach_mmr_player_account, reject_duplicate_mmr_accounts
from mmr.gold.mmr import update_mmr_elo
from scripts.run_mmr_once import _prepare_user_summary


def _members() -> pd.DataFrame:
    return pd.DataFrame([
        {"guild_id": "g", "account": "A001", "main_account": "B002", "is_main": False},
        {"guild_id": "g", "account": "B002", "main_account": None, "is_main": True},
    ])


def _two_games() -> pd.DataFrame:
    rows = []
    for number, account in ((1, "A001"), (2, "B002")):
        for position in ("TOP", "JUG", "MID", "ADC", "SUP"):
            for result in (1, 0):
                code = account if position == "TOP" and result == 1 else f"{position}-{result}-{number}"
                rows.append({
                    "guild_id": "g", "replay_code": f"game-{number}",
                    "played_at": pd.Timestamp(f"2026-01-0{number}"),
                    "player_code": code, "position": position, "game_result": result,
                    "game_n_person_contribution": 1.2 if result else 0.8,
                    "game_impact_vs_opponent": 70.0 if result else 30.0,
                })
    return pd.DataFrame(rows)


def test_alt_and_main_share_continuous_mmr_and_one_summary():
    mapped = attach_mmr_player_account(_two_games(), _members())
    calculated, summary = update_mmr_elo(mapped)
    owner_rows = calculated.loc[calculated["mmr_player_account"].eq("B002")]

    assert owner_rows["player_code"].tolist() == ["A001", "B002"]
    assert owner_rows["pre_game_pos_mmr"].iloc[1] == owner_rows["pos_cumulative_mmr"].iloc[0]
    assert summary.loc[summary["player_code"].eq("B002"), "total_games"].item() == 2
    assert "A001" not in summary["player_code"].tolist()
    _prepare_user_summary(summary.to_dict("records"), calculated)


def test_missing_main_account_stops_mapping():
    members = _members()
    members.loc[members["account"].eq("A001"), "main_account"] = None
    with pytest.raises(ValueError, match="MISSING_MAIN_ACCOUNT"):
        attach_mmr_player_account(_two_games(), members)


def test_same_game_main_and_alt_rejects_whole_game():
    rows = pd.DataFrame([
        {"guild_id": "g", "replay_code": "bad", "player_code": "A001"},
        {"guild_id": "g", "replay_code": "bad", "player_code": "B002"},
        {"guild_id": "g", "replay_code": "good", "player_code": "B002"},
    ])
    mapped = attach_mmr_player_account(rows, _members())
    valid, rejected = reject_duplicate_mmr_accounts(mapped)

    assert valid["replay_code"].tolist() == ["good"]
    assert rejected == [{
        "guild_id": "g", "replay_code": "bad", "reason_code": "DUPLICATE_MMR_ACCOUNT",
        "mmr_player_accounts": ["B002"], "player_codes": ["A001", "B002"],
    }]


def test_gold_rejects_duplicate_owner_if_batch_filter_is_bypassed():
    from mmr.gold.mmr import validate_mmr_input_matches

    game = _two_games().loc[lambda frame: frame["replay_code"].eq("game-1")].copy()
    game.loc[game["position"].eq("TOP") & game["game_result"].eq(0), "player_code"] = "B002"
    mapped = attach_mmr_player_account(game, _members())
    with pytest.raises(ValueError, match="duplicated MMR accounts"):
        validate_mmr_input_matches(mapped)


def test_invalid_target_is_not_silently_treated_as_self():
    members = _members().loc[lambda frame: frame["account"].ne("B002")]
    with pytest.raises(ValueError, match="INVALID_MAIN_ACCOUNT"):
        attach_mmr_player_account(_two_games(), members)
