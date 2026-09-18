from __future__ import annotations

import pandas as pd

from mmr.silver import clean_match_data, drop_invalid_matches, find_rows_with_na


def test_clean_match_data_removes_duplicates_and_converts_basic_fields():
    df = pd.DataFrame(
        [
            {
                "puuid": "p1",
                "win": True,
                "game_duration": 120,
                "heal_on_teammates": None,
                "shield_on_teammates": None,
            },
            {
                "puuid": "p1",
                "win": True,
                "game_duration": 120,
                "heal_on_teammates": None,
                "shield_on_teammates": None,
            },
            {
                "puuid": "p2",
                "win": False,
                "game_duration": 90,
                "heal_on_teammates": 7,
                "shield_on_teammates": 3,
            },
        ]
    )

    out = clean_match_data(df)

    assert len(out) == 2
    assert "win" not in out.columns
    assert out.loc[out["puuid"] == "p1", "game_result"].item() == 1
    assert out.loc[out["puuid"] == "p2", "game_result"].item() == 0
    assert out.loc[out["puuid"] == "p1", "game_duration"].item() == 2.0
    assert out.loc[out["puuid"] == "p1", "heal_on_teammates"].item() == 0
    assert out.loc[out["puuid"] == "p1", "shield_on_teammates"].item() == 0


def test_find_rows_with_na_ignores_excluded_columns():
    df = pd.DataFrame(
        {
            "puuid": ["p1", "p2", "p3"],
            "kills": [1, None, 3],
            "dragon_kills": [None, None, None],
        }
    )

    out = find_rows_with_na(df, na_exclude_cols=("dragon_kills",))

    assert out["puuid"].tolist() == ["p2"]


def test_invalid_match_in_one_guild_does_not_drop_same_replay_in_another():
    rows = []
    for guild_id in ("guild-a", "guild-b"):
        for position in ("TOP", "JUG", "MID", "ADC", "SUP"):
            for result in (1, 0):
                rows.append({
                    "guild_id": guild_id,
                    "replay_code": "shared-replay",
                    "position": position,
                    "game_result": result,
                })
    df = pd.DataFrame(rows).iloc[:-1]

    valid = drop_invalid_matches(df)

    assert len(valid) == 10
    assert valid["guild_id"].unique().tolist() == ["guild-a"]
