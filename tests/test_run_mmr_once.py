from __future__ import annotations

import pandas as pd
import pytest

from scripts.run_mmr_once import _prepare_match_results, _prepare_user_summary


def test_summary_keeps_separate_player_guild_results():
    matches = _prepare_match_results(
        [
            {"player_code": "alice", "guild_id": "guild-a", "replay_code": "game-1"},
            {"player_code": "alice", "guild_id": "guild-b", "replay_code": "game-2"},
        ],
        guild_id=None,
    )
    summary = _prepare_user_summary(
        [
            {"player_code": "alice", "guild_id": "guild-a", "total_mmr": 1450},
            {"player_code": "alice", "guild_id": "guild-b", "total_mmr": 1300},
        ],
        matches,
    )

    assert summary[["player_code", "guild_id", "total_mmr"]].to_dict("records") == [
        {"player_code": "alice", "guild_id": "guild-a", "total_mmr": 1450},
        {"player_code": "alice", "guild_id": "guild-b", "total_mmr": 1300},
    ]


def test_scoped_matches_reject_another_guild():
    with pytest.raises(RuntimeError, match="different guild_id"):
        _prepare_match_results(
            [{"player_code": "alice", "guild_id": "guild-b", "replay_code": "game-1"}],
            guild_id="guild-a",
        )


def test_summary_rejects_missing_guild_id_before_saving():
    matches = pd.DataFrame({"player_code": ["alice"], "guild_id": ["guild-a"]})

    with pytest.raises(RuntimeError, match="require guild_id"):
        _prepare_user_summary(
            [{"player_code": "alice", "guild_id": None, "total_mmr": 1450}], matches
        )
