from __future__ import annotations

import pandas as pd
import pytest

from scripts.run_mmr_once import _prepare_match_results, _prepare_user_summary


def test_global_summary_repeats_combined_mmr_for_each_calculated_guild():
    matches = _prepare_match_results(
        [
            {"puuid": "alice", "guild_id": "guild-a", "replay_code": "game-1"},
            {"puuid": "alice", "guild_id": "guild-a", "replay_code": "game-2"},
            {"puuid": "alice", "guild_id": "guild-b", "replay_code": "game-3"},
            {"puuid": "bob", "guild_id": "guild-b", "replay_code": "game-3"},
        ],
        guild_id=None,
    )

    summary = _prepare_user_summary(
        [
            {"puuid": "alice", "total_mmr": 1450},
            {"puuid": "bob", "total_mmr": 1320},
        ],
        matches,
    )

    assert summary[["player_code", "guild_id", "total_mmr"]].to_dict("records") == [
        {"player_code": "alice", "guild_id": "guild-a", "total_mmr": 1450},
        {"player_code": "alice", "guild_id": "guild-b", "total_mmr": 1450},
        {"player_code": "bob", "guild_id": "guild-b", "total_mmr": 1320},
    ]


def test_scoped_summary_uses_calculated_match_guild():
    matches = pd.DataFrame({"player_code": ["alice"], "guild_id": ["guild-a"]})

    summary = _prepare_user_summary([{"puuid": "alice", "total_mmr": 1450}], matches)

    assert summary["guild_id"].tolist() == ["guild-a"]


def test_summary_rejects_missing_guild_id_before_saving():
    matches = pd.DataFrame({"player_code": ["alice"], "guild_id": [None]})

    with pytest.raises(RuntimeError, match="missing guild_id"):
        _prepare_user_summary([{"puuid": "alice", "total_mmr": 1450}], matches)
