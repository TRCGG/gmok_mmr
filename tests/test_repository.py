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
    assert "INSERT INTO {table_name}" in baseline_repository_source
    # 같은 (season, baseline_version)은 덮어쓰지 않는다.
    assert "ON CONFLICT (season, baseline_version) DO NOTHING" in baseline_repository_source
    assert "DO UPDATE" not in baseline_repository_source
    assert "is_active = true" in baseline_repository_source
    assert "CAST(:mmr_baseline AS jsonb)" in baseline_repository_source


def test_full_mmr_db_test_script_loads_baseline_before_calculation():
    script_path = (
        Path(__file__).resolve().parent
        / "cli"
        / "calculate_full_mmr_with_db_baseline.py"
    )
    script_source = script_path.read_text(encoding="utf-8")

    assert "DB baseline으로 한 시즌의 전체 MMR을 계산만 하는" in script_source
    assert "load_mmr_baseline_from_db_test" in script_source
    assert "calculate_full_mmr" in script_source
    assert "load_baseline_for_season" in script_source
    assert "validate_baseline_payload" in script_source
    # 결과 저장은 scripts/run_mmr_once.py로만 한다.
    assert "--save-results" not in script_source


def test_position_report_is_bound_as_jsonb_for_psycopg2():
    import json

    import pandas as pd
    from sqlalchemy.dialects.postgresql import JSONB, psycopg2

    summary = pd.DataFrame(
        [{"guild_id": "g", "player_code": "p", "position_report": {"TOP": {"games": 20}}}]
    )
    dtype = repository._jsonb_dtype(summary)

    assert set(dtype) == {"position_report"}
    assert isinstance(dtype["position_report"], JSONB)
    bind = dtype["position_report"].bind_processor(psycopg2.dialect())
    assert json.loads(bind({"TOP": {"games": 20}})) == {"TOP": {"games": 20}}


def test_jsonb_dtype_skips_frames_without_report_column():
    import pandas as pd

    assert repository._jsonb_dtype(pd.DataFrame({"guild_id": ["g"]})) == {}


def test_replace_delete_is_scoped_to_guild_and_season():
    import pandas as pd

    class _Conn:
        def execute(self, statement, params):
            self.sql = str(statement)
            self.params = params

    conn = _Conn()
    matches = pd.DataFrame(
        {
            "guild_id": ["g", "g", "g"],
            "season": ["2026", "2026", "2027"],
            "replay_code": ["r1", "r2", "r3"],
        }
    )

    repository._delete_existing_season_scope(matches, conn, "mmr_match_results")

    assert "guild_id = :guild_id AND season = :season" in conn.sql
    assert conn.params == [
        {"guild_id": "g", "season": "2026"},
        {"guild_id": "g", "season": "2027"},
    ]


def test_raw_match_sql_reads_season_from_custom_match():
    repository_source = inspect.getsource(repository)

    assert "cm.season                                      AS season" in repository_source
    assert "LEFT JOIN custom_match cm ON cm.id = pg.custom_match_id" in repository_source


def test_raw_match_sql_reads_only_regular_custom_games():
    repository_source = inspect.getsource(repository)

    # 일반내전(game_type 1)만 1회 계산 대상이다. 스크림·대회는 제외한다.
    assert "\"pg.game_type = '1'\"" in repository_source
