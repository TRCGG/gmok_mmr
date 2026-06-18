from __future__ import annotations

import inspect
from pathlib import Path

from harness import data_loader
from harness.db_test import baseline_repository
from harness.db_test import repository


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


def test_db_test_module_owns_temporary_baseline_storage_sql():
    repository_source = inspect.getsource(repository)
    baseline_repository_source = inspect.getsource(baseline_repository)

    assert "mmr_baselines" not in repository_source
    assert "DB 테스트" in baseline_repository_source
    assert "INSERT INTO {table_name}" in baseline_repository_source
    assert "ON CONFLICT (season, baseline_version) DO UPDATE" in baseline_repository_source
    assert "is_active = true" in baseline_repository_source
    assert "CAST(:mmr_baseline AS jsonb)" in baseline_repository_source


def test_full_mmr_db_test_script_loads_baseline_before_calculation():
    script_path = (
        Path(__file__).resolve().parent
        / "cli"
        / "calculate_full_mmr_with_db_baseline.py"
    )
    script_source = script_path.read_text(encoding="utf-8")

    assert "DB 테스트용 전체 MMR 계산 스크립트" in script_source
    assert "load_mmr_baseline_from_db_test" in script_source
    assert "calculate_full_mmr" in script_source
    assert "--save-results" in script_source
