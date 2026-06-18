from __future__ import annotations

import pandas as pd
import pytest

from harness import config
from harness.db_test import config as db_config
from harness.data_writer import _stamp, save_mmr_results


def test_config_defaults(monkeypatch):
    monkeypatch.delenv("MMR_DATA_SOURCE", raising=False)
    monkeypatch.delenv("MMR_RESULT_SINK", raising=False)
    monkeypatch.delenv("MMR_MATCH_RESULT_TABLE", raising=False)
    monkeypatch.delenv("MMR_SUMMARY_TABLE", raising=False)
    monkeypatch.delenv("MMR_PLAYER_GAME_TABLE", raising=False)
    monkeypatch.delenv("MMR_PLAYER_TABLE", raising=False)

    assert config.get_data_source() == "db"
    assert config.get_result_sink() == "db"
    assert db_config.get_mmr_match_result_table() == "mmr_match_results"
    assert db_config.get_mmr_summary_table() == "mmr_user_summary"
    assert db_config.get_player_game_table() == "player_game"
    assert db_config.get_player_table() == "player"


def test_config_environment_overrides(monkeypatch):
    monkeypatch.setenv("MMR_DATA_SOURCE", "api")
    monkeypatch.setenv("MMR_RESULT_SINK", "api")
    monkeypatch.setenv("MMR_MATCH_RESULT_TABLE", "custom_match")
    monkeypatch.setenv("MMR_SUMMARY_TABLE", "custom_summary")
    monkeypatch.setenv("MMR_PLAYER_GAME_TABLE", "custom_player_game")
    monkeypatch.setenv("MMR_PLAYER_TABLE", "custom_player")

    assert config.get_data_source() == "api"
    assert config.get_result_sink() == "api"
    assert db_config.get_mmr_match_result_table() == "custom_match"
    assert db_config.get_mmr_summary_table() == "custom_summary"
    assert db_config.get_player_game_table() == "custom_player_game"
    assert db_config.get_player_table() == "custom_player"


def test_config_rejects_unsafe_table_names(monkeypatch):
    monkeypatch.setenv("MMR_PLAYER_GAME_TABLE", "player_game;drop")

    with pytest.raises(ValueError, match="Unsafe SQL identifier"):
        db_config.get_player_game_table()


def test_writer_stamp_normalizes_columns_before_save():
    out = _stamp(
        pd.DataFrame(
            {
                "TOP_mmr": [1300.123],
                "PUUID": ["p1"],
                "player_game_id": [123],
            }
        )
    )

    assert "top_mmr" in out.columns
    assert "puuid" in out.columns
    assert "player_game_id" not in out.columns
    assert out["top_mmr"].item() == 1300.12
    assert "calculated_at" in out.columns


def test_save_mmr_results_rejects_unknown_sink():
    with pytest.raises(ValueError, match="Unsupported MMR_RESULT_SINK"):
        save_mmr_results(pd.DataFrame(), pd.DataFrame(), sink="file")
