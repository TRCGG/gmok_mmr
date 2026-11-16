"""시즌별 전체 계산 배치(scripts/run_mmr_once.py)와 교체 저장 범위 검증."""

from __future__ import annotations

import importlib
import random

import pandas as pd
import pytest

from harness.db_test import repository
from scripts import run_mmr_once
from scripts.run_mmr_once import _calculate_season

POSITIONS = ("TOP", "JUG", "MID", "ADC", "SUP")


def _match(replay_code: str, day: int, season: str, rng: random.Random) -> list[dict]:
    rows = []
    for team_index, (team, result) in enumerate((("blue", 1), ("red", 0))):
        for position_index, position in enumerate(POSITIONS):
            player = f"p{team_index * 5 + position_index}"
            rows.append({
                "replay_code": replay_code,
                "player_code": player,
                "mmr_player_account": player,
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


def _members() -> pd.DataFrame:
    return pd.DataFrame([
        {"guild_id": "g", "account": f"p{i}", "status": "1"}
        for i in range(10)
    ])


def _run(season_df: pd.DataFrame, season: str):
    return _calculate_season(
        season_df,
        season=season,
        baseline_version="test",
        guild_id=None,
        calculation_id="test",
        members=_members(),
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


def test_calculate_season_does_not_write_baseline(monkeypatch):
    monkeypatch.setattr(
        run_mmr_once,
        "save_mmr_baseline_to_db_test",
        lambda *args, **kwargs: pytest.fail("baseline must be saved after every season"),
    )

    run = _run(_season_rows("2026", games=6), "2026")

    assert run["baseline_payload"]["season"] == "2026"


def test_tiny_season_baseline_is_rejected_before_saving():
    with pytest.raises(RuntimeError, match="unusable"):
        _run(_season_rows("2027", games=1), "2027")


def test_season_without_valid_5v5_match_is_skipped():
    broken = _season_rows("2027", games=1).iloc[:9]

    assert _run(broken, "2027") is None


def test_season_values_are_stripped_strings_and_blank_is_rejected():
    raw = pd.DataFrame({"replay_code": ["a", "b"], "season": [2026, " 2027 "]})

    assert run_mmr_once._season_values(raw).tolist() == ["2026", "2027"]
    with pytest.raises(RuntimeError, match=r"Missing for: \['b'\]"):
        run_mmr_once._season_values(pd.DataFrame({"replay_code": ["a", "b"], "season": ["2026", " "]}))


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


def test_unique_key_migration_skips_summary_dedupe_after_season_exists():
    sql = open("migrations/007_add_result_unique_keys.sql", encoding="utf-8").read()
    guard = sql.index("column_name = 'season'")

    assert guard < sql.index("DELETE FROM mmr_user_summary")
    assert guard < sql.index("ON mmr_user_summary (guild_id, player_code)")


def test_cli_db_save_paths_are_blocked(monkeypatch):
    main_pipeline = importlib.import_module("cli.main_pipeline")

    with pytest.raises(SystemExit, match="run_mmr_once.py"):
        main_pipeline.run_pipeline(source="db", sink="db")


def test_alt_account_keeps_its_own_mmr_and_summary_row():
    season_df = _season_rows("2026", games=6)
    alt_games = season_df["player_code"].eq("p0") & season_df["replay_code"].isin(["2026-r0", "2026-r1"])
    season_df.loc[alt_games, ["player_code", "mmr_player_account"]] = "p0-alt"
    members = pd.concat(
        [_members(), pd.DataFrame([{"guild_id": "g", "account": "p0-alt", "status": "1"}])],
        ignore_index=True,
    )

    run = _calculate_season(
        season_df,
        season="2026",
        baseline_version="test",
        guild_id=None,
        calculation_id="test",
        members=members,
    )
    summary = run["user_summary"].set_index("player_code")
    matches = run["match_results"]

    assert summary.loc["p0-alt", "total_games"] == 2
    assert summary.loc["p0", "total_games"] == 4
    # 본캐 첫 경기는 부캐 MMR을 이어받지 않고 초기값에서 시작한다.
    first_main_game = matches[matches["player_code"].eq("p0")].sort_values("played_at").iloc[0]
    assert first_main_game["pre_game_pos_mmr"] == 1300


def test_season_with_no_current_members_stops_before_saving():
    nobody = pd.DataFrame({"guild_id": ["g"], "account": ["someone-else"], "status": ["1"]})

    with pytest.raises(RuntimeError, match="no current guild members"):
        _calculate_season(
            _season_rows("2026", games=6),
            season="2026",
            baseline_version="test",
            guild_id=None,
            calculation_id="test",
            members=nobody,
        )


def test_match_results_reject_alt_account_attribution():
    rows = [{"guild_id": "g", "replay_code": "r1", "player_code": "p0-alt", "mmr_player_account": "p0"}]

    with pytest.raises(RuntimeError, match="must equal player_code"):
        run_mmr_once._prepare_match_results(rows, guild_id=None)
