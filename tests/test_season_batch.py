"""시즌별 전체 계산 배치(scripts/run_mmr_once.py)와 교체 저장 범위 검증."""

from __future__ import annotations

import importlib
from pathlib import Path
import random

import pandas as pd
import pytest

from harness.db_test import repository
from harness.season import normalize_season
from scripts import run_mmr_once
from scripts.calculate_baseline import build_season_baseline
from scripts.run_mmr_once import _calculate_season

ROOT = Path(__file__).resolve().parents[1]
POSITIONS = ("TOP", "JUG", "MID", "ADC", "SUP")


def _match(replay_code: str, day: int, season: str, rng: random.Random) -> list[dict]:
    rows = []
    for team_index, (team, result) in enumerate((("blue", 1), ("red", 0))):
        for position_index, position in enumerate(POSITIONS):
            player = f"p{team_index * 5 + position_index}"
            rows.append({
                "replay_code": replay_code,
                "player_code": player,
                "guild_id": "g",
                "season": season,
                "team": team,
                "position": position,
                "game_result": result,
                "kills": rng.randint(0, 10),
                "deaths": rng.randint(1, 10),
                "assists": rng.randint(0, 10),
                "gold": rng.randint(8000, 15000),
                "cc_time": rng.randint(0, 50),
                "game_duration": 1800,
                "damage_to_champions": rng.randint(5000, 30000),
                "damage_taken": rng.randint(5000, 30000),
                "vision_score": rng.randint(5, 60),
                "vision_bought": 2,
                "penta_kills": 0,
                "minions_killed": 150,
                "neutral_minions_killed": 10,
                "exp": 12000,
                "level": 15,
                "played_at": pd.Timestamp("2026-01-01") + pd.Timedelta(days=day),
            })
    return rows


def _season_rows(season: str, games: int, start_day: int = 0) -> pd.DataFrame:
    rng = random.Random(f"{season}-{games}")
    return pd.DataFrame([
        row
        for number in range(games)
        for row in _match(f"{season}-r{number}", start_day + number, season, rng)
    ])


def _baseline(season: str, games: int = 6) -> dict:
    # 합성 데이터는 경기 수가 적으므로 최소 경기 수만 낮춰 실제 계산 경로로 만든다.
    return build_season_baseline(
        _season_rows(season, games=games),
        season=season,
        baseline_version="test",
        min_matches=1,
    )


def _run(season_df: pd.DataFrame, season: str, baseline: dict | None = None):
    return _calculate_season(
        season_df,
        season=season,
        baseline_payload=baseline or _baseline(season),
        guild_id=None,
        calculation_id="test",
    )


def test_each_season_starts_from_initial_mmr_and_keeps_one_summary_row():
    first = _run(_season_rows("2026", games=6), "2026")
    second = _run(_season_rows("2027", games=6, start_day=30), "2027")

    for run, season in ((first, "2026"), (second, "2027")):
        matches = run["match_results"]
        opening_game = matches.loc[matches["replay_code"].eq(f"{season}-r0")]
        assert opening_game["pre_game_pos_mmr"].eq(1300).all()
        assert set(matches["season"]) == {season}
        assert set(run["user_summary"]["season"]) == {season}
        assert not run["user_summary"].duplicated(["guild_id", "player_code"]).any()

    combined = pd.concat([first["user_summary"], second["user_summary"]], ignore_index=True)
    assert not combined.duplicated(["guild_id", "player_code", "season"]).any()
    assert combined["season"].map(type).eq(str).all()


def test_new_season_can_use_previous_season_baseline():
    run = _run(_season_rows("2027", games=3, start_day=30), "2027", baseline=_baseline("2026"))

    assert run["baseline_payload"]["season"] == "2026"
    assert set(run["match_results"]["season"]) == {"2027"}
    opening_game = run["match_results"].loc[lambda df: df["replay_code"].eq("2027-r0")]
    assert opening_game["pre_game_pos_mmr"].eq(1300).all()


def test_baseline_requires_minimum_matches():
    raw = _season_rows("2026", games=6)

    assert build_season_baseline(raw, season="2026", baseline_version="v", min_matches=6)
    with pytest.raises(SystemExit, match="match_count=6 < 7"):
        build_season_baseline(raw, season="2026", baseline_version="v", min_matches=7)


def test_baseline_default_minimum_is_200_matches():
    with pytest.raises(SystemExit, match="match_count=6 < 200"):
        build_season_baseline(_season_rows("2026", games=6), season="2026", baseline_version="v")


def test_degenerate_baseline_is_rejected_even_above_minimum():
    with pytest.raises(SystemExit, match="no Game Impact weights"):
        build_season_baseline(
            _season_rows("2027", games=1), season="2027", baseline_version="v", min_matches=1
        )


def test_baseline_uses_only_the_requested_season():
    raw = pd.concat([_season_rows("2026", games=6), _season_rows("2027", games=3)])

    payload = build_season_baseline(raw, season="2026", baseline_version="v", min_matches=1)

    assert payload["metadata"]["match_count"] == 6


def test_season_baseline_falls_back_and_is_validated(monkeypatch):
    built = _baseline("2026")
    # DB에 저장된 baseline은 생성 시 200판 이상이어야 한다(합성 데이터 경기 수만 보정).
    previous = {**built, "metadata": {**built["metadata"], "match_count": 200}}
    monkeypatch.setattr(run_mmr_once, "load_baseline_for_season", lambda season: previous)

    assert run_mmr_once._load_season_baseline("2027") is previous

    tiny = {**previous, "metadata": {**previous["metadata"], "match_count": 50}}
    monkeypatch.setattr(run_mmr_once, "load_baseline_for_season", lambda season: tiny)
    with pytest.raises(SystemExit, match="match_count=50 < 200"):
        run_mmr_once._load_season_baseline("2027")


def test_season_without_valid_5v5_match_is_skipped():
    broken = _season_rows("2027", games=1).iloc[:9]

    assert _run(broken, "2027") is None


def test_season_values_are_stripped_strings_and_blank_is_rejected():
    raw = pd.DataFrame({"replay_code": ["a", "b"], "season": [2026, " 2027 "]})

    assert normalize_season(raw).tolist() == ["2026", "2027"]
    with pytest.raises(RuntimeError, match=r"Missing for: \['b'\]"):
        normalize_season(pd.DataFrame({"replay_code": ["a", "b"], "season": ["2026", " "]}))


def test_replace_scopes_require_season_and_cover_saved_rows():
    matches = pd.DataFrame({"guild_id": ["g"], "season": ["2026"]})
    summary = pd.DataFrame({"guild_id": ["g"], "season": ["2026"]})

    with pytest.raises(ValueError, match="missing replace-scope columns"):
        repository._resolve_replace_scopes(matches.drop(columns="season"), summary, None)
    with pytest.raises(ValueError, match="outside the replace scopes"):
        repository._resolve_replace_scopes(
            matches, summary, pd.DataFrame({"guild_id": ["g"], "season": ["2027"]})
        )


def test_replace_scopes_keep_target_scope_without_results():
    matches = pd.DataFrame({"guild_id": ["g"], "season": ["2026"]})
    summary = pd.DataFrame({"guild_id": ["g"], "season": ["2026"]})
    target = pd.DataFrame({"guild_id": ["g", "h"], "season": ["2026", "2026"]})

    scopes = repository._resolve_replace_scopes(matches, summary, target)

    assert scopes.to_dict("records") == [
        {"guild_id": "g", "season": "2026"},
        {"guild_id": "h", "season": "2026"},
    ]


def test_merged_migration_changes_schema_only():
    sql = open(ROOT / "migrations/006_mmr_report_season_baseline.sql", encoding="utf-8").read()
    statements = [
        line.strip().upper() for line in sql.splitlines()
        if line.strip() and not line.strip().startswith("--")
    ]

    # 기존 데이터를 고치지 않는다(테이블을 비운 뒤 1회 계산 전에 적용한다).
    for keyword in ("DELETE ", "UPDATE ", "INSERT ", "DO $$", "TRUNCATE"):
        assert not any(statement.startswith(keyword) for statement in statements), keyword
    # 다시 실행해도 안전한 형태만 쓴다.
    for line in statements:
        if line.startswith(("CREATE ", "DROP ")):
            assert "IF NOT EXISTS" in line or "IF EXISTS" in line, line
        if "ADD COLUMN" in line:
            assert "ADD COLUMN IF NOT EXISTS" in line, line


def test_cli_db_save_paths_are_blocked(monkeypatch):
    main_pipeline = importlib.import_module("cli.main_pipeline")

    with pytest.raises(SystemExit, match="run_mmr_once.py"):
        main_pipeline.run_pipeline(source="db", sink="db")


def test_alt_account_keeps_its_own_mmr_and_summary_row():
    season_df = _season_rows("2026", games=6)
    alt_games = season_df["player_code"].eq("p0") & season_df["replay_code"].isin(["2026-r0", "2026-r1"])
    season_df.loc[alt_games, "player_code"] = "p0-alt"

    run = _run(season_df, "2026")
    summary = run["user_summary"].set_index("player_code")
    matches = run["match_results"]

    assert summary.loc["p0-alt", "total_games"] == 2
    assert summary.loc["p0", "total_games"] == 4
    # 본캐 첫 경기는 부캐 MMR을 이어받지 않고 초기값에서 시작한다.
    first_main_game = matches[matches["player_code"].eq("p0")].sort_values("played_at").iloc[0]
    assert first_main_game["pre_game_pos_mmr"] == 1300


def test_summary_keeps_every_player_with_results():
    # 길드원 판정 없이 결과가 있는 모든 계정(탈퇴자 포함)이 summary 한 행씩을 갖는다.
    run = _run(_season_rows("2026", games=6), "2026")

    accounts = run["match_results"][["guild_id", "player_code"]].drop_duplicates()
    assert len(run["user_summary"]) == len(accounts) == 10
    assert run["user_summary"]["position_report"].map(bool).all()


def test_mmr_player_account_is_gone():
    sql = open(ROOT / "migrations/006_mmr_report_season_baseline.sql", encoding="utf-8").read()

    # 계정 키는 player_code 하나다. 006이 005의 mmr_player_account를 지운다.
    assert "ALTER TABLE mmr_match_results DROP COLUMN IF EXISTS mmr_player_account;" in sql
    assert "ON mmr_match_results (guild_id, player_code, position, played_at)" in sql
    assert sql.index("DROP COLUMN IF EXISTS mmr_player_account") < sql.index(
        "idx_mmr_match_results_history_lookup\n"
    )
    # 계산·리포트·저장 코드는 이 컬럼을 쓰지 않는다(입력 정리와 남은 컬럼 검사만 이름을 쓴다).
    for path in ("src/mmr/gold/mmr.py", "src/mmr/gold/report.py", "tests/harness/db_test/repository.py"):
        assert "mmr_player_account" not in (ROOT / path).read_text(encoding="utf-8"), path


def test_stale_account_column_in_input_is_ignored_and_keyed_by_player_code():
    # 예전 입력처럼 mmr_player_account가 player_code와 다른 값으로 들어와도 계정 키는 player_code다.
    season_df = _season_rows("2026", games=6).assign(mmr_player_account="someone-else")

    run = _run(season_df, "2026")

    assert "mmr_player_account" not in run["match_results"].columns
    assert sorted(run["user_summary"]["player_code"]) == [f"p{i}" for i in range(10)]


def test_single_match_state_is_keyed_by_player_code():
    from mmr.serving.service import calculate_single_match_mmr

    baseline = _baseline("2026")
    rows = _season_rows("2026", games=1).assign(mmr_player_account="someone-else")
    rows["played_at"] = rows["played_at"].astype(str)

    result = calculate_single_match_mmr({
        "guild_id": "g",
        "season": "2026",
        "baseline_version": baseline["baseline_version"],
        "match_rows": rows.to_dict(orient="records"),
        "current_user_state": [],
        "baseline_stats": baseline["mmr_baseline"],
        "game_impact_baseline": baseline["game_impact_baseline"],
    })

    assert {row["player_code"] for row in result["updated_user_summary"]} == {f"p{i}" for i in range(10)}
    assert all("mmr_player_account" not in row for row in result["match_results"])


def test_batch_stops_when_removed_account_column_is_still_present(monkeypatch):
    class _Inspector:
        def has_table(self, name):
            return True

        def get_columns(self, name):
            columns = {"replay_code", "player_code", "guild_id", "season", "baseline_season",
                       "baseline_version", "position_report", "mmr_player_account"}
            return [{"name": column} for column in columns]

    class _Conn:
        def __enter__(self):
            return self

        def __exit__(self, *exc):
            return False

    class _Engine:
        def connect(self):
            return _Conn()

    monkeypatch.setattr(run_mmr_once, "create_engine", lambda url: _Engine())
    monkeypatch.setattr(run_mmr_once, "get_db_url", lambda: "fake://")
    monkeypatch.setattr(run_mmr_once, "inspect", lambda conn: _Inspector())

    with pytest.raises(RuntimeError, match="Re-apply migrations/006"):
        run_mmr_once._assert_result_tables_ready()

def test_results_record_the_baseline_used():
    own = _run(_season_rows("2026", games=6), "2026")
    carried = _run(_season_rows("2027", games=3, start_day=30), "2027", baseline=_baseline("2026"))

    assert set(own["match_results"]["baseline_season"]) == {"2026"}
    assert set(carried["match_results"]["baseline_season"]) == {"2026"}
    assert set(carried["match_results"]["season"]) == {"2027"}
    assert set(carried["match_results"]["baseline_version"]) == {"test"}
    assert "baseline_season" not in carried["user_summary"].columns


def test_result_baseline_migration_adds_columns():
    sql = open(ROOT / "migrations/006_mmr_report_season_baseline.sql", encoding="utf-8").read()

    assert "ADD COLUMN IF NOT EXISTS baseline_season" in sql
    assert "ADD COLUMN IF NOT EXISTS baseline_version" in sql


def test_batch_game_impact_equals_notebook_season_minmax():
    import numpy as np

    from mmr.silver.game_impact import normalize_minmax_0_100

    run = _run(_season_rows("2026", games=6), "2026")
    matches = run["match_results"]

    # 시즌 자기 baseline으로 계산하면 노트북처럼 시즌 전체 MinMax와 같다.
    assert np.allclose(matches["game_impact"], normalize_minmax_0_100(matches["raw_game_impact"]))
    # 한 경기만 떼어 다시 계산해도 같은 점수가 나온다.
    one_game = _season_rows("2026", games=6).loc[lambda df: df["replay_code"].eq("2026-r3")]
    single = _run(one_game, "2026", baseline=run["baseline_payload"])["match_results"]
    same_game = matches[matches["replay_code"].eq("2026-r3")].set_index("player_code")
    expected = same_game.loc[single["player_code"], "game_impact"]
    assert np.allclose(single["game_impact"], expected.to_numpy())


def test_summary_guard_rejects_missing_rows_and_empty_reports():
    run = _run(_season_rows("2026", games=6), "2026")
    matches, summary = run["match_results"], run["user_summary"]

    with pytest.raises(RuntimeError, match="summary has 9 rows for 10 accounts"):
        run_mmr_once._assert_summary_covers_all_players(matches, summary.iloc[1:], "2026")
    blank = summary.assign(position_report=[{}] + summary["position_report"].iloc[1:].tolist())
    with pytest.raises(RuntimeError, match="1 summary rows have an empty position_report"):
        run_mmr_once._assert_summary_covers_all_players(matches, blank, "2026")
