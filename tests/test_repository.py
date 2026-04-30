from __future__ import annotations

import inspect

from mmr_refactor import data_loader
from mmr_refactor import repository


def test_sql_is_owned_by_repository_module():
    repository_source = inspect.getsource(repository)
    loader_source = inspect.getsource(data_loader)

    assert "FROM {player_game_table} pg" in repository_source
    assert "FROM {player_table}" in repository_source
    assert "FROM {player_game_table} pg" not in loader_source


def test_raw_match_sql_selects_original_mmr_metric_source_columns():
    repository_source = inspect.getsource(repository)

    expected_columns = [
        "pg.exp",
        "pg.damage_to_turrets",
        "pg.minions_killed",
        "pg.neutral_minions_killed",
        "pg.wards_placed",
        "pg.wards_killed",
        "pg.heal_on_teammates",
        "pg.shield_on_teammates",
    ]

    for column in expected_columns:
        assert column in repository_source
