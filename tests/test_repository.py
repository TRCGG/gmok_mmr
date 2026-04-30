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
