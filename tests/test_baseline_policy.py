"""baseline 정책 검증: 200판 기준, 덮어쓰기 금지, 선택 규칙, 배치 흐름."""

from __future__ import annotations

import json
import math

import pandas as pd
import pytest
from sqlalchemy import create_engine, text

from harness.db_test import baseline_repository
from mmr.gold.baseline import validate_baseline_payload
from scripts import run_mmr_once
from test_season_batch import _season_rows

POSITIONS = ("TOP", "JUG", "MID", "ADC", "SUP")


def _valid_payload(**metadata) -> dict:
    return {
        "season": "2026",
        "baseline_version": "v1",
        "mmr_baseline": {
            "f1_mean": 1.0,
            "f2_mean": 50.0,
            "f1_position_mean": {pos: 1.0 for pos in POSITIONS},
            "f2_position_mean": {pos: 50.0 for pos in POSITIONS},
        },
        "game_impact_baseline": {
            "position_weights": {pos: {"dpm": 0.6, "kda": 0.4} for pos in POSITIONS},
            "outcome_stats": [
                {"position": pos, "game_result": result, "lower": 0.0, "upper": 10.0}
                for pos in POSITIONS
                for result in (0, 1)
            ],
            "impact_range": {"lower": -5.0, "upper": 120.0},
        },
        "metadata": {"match_count": 200, "scope": "all_guilds", **metadata},
    }


# ----------------------------------------------------------------------------
# validate_baseline_payload
# ----------------------------------------------------------------------------

def test_valid_baseline_passes():
    validate_baseline_payload(_valid_payload())


@pytest.mark.parametrize(
    ("match_count", "message"),
    [
        (199, "match_count=199 < 200"),
        (None, "is not an integer"),
        (math.nan, "is not an integer"),
        ("200", "is not an integer"),
        (True, "is not an integer"),
    ],
)
def test_match_count_must_be_an_integer_of_at_least_200(match_count, message):
    with pytest.raises(ValueError, match=message):
        validate_baseline_payload(_valid_payload(match_count=match_count))


def test_degenerate_parts_are_rejected():
    payload = _valid_payload()
    payload["mmr_baseline"]["f1_mean"] = 0
    payload["game_impact_baseline"]["position_weights"]["TOP"] = {"dpm": 0.0, "kda": 0.0}
    payload["game_impact_baseline"]["position_weights"]["JUG"] = {"dpm": math.nan}
    payload["game_impact_baseline"]["impact_range"] = {"lower": 3.0, "upper": 3.0}
    payload["game_impact_baseline"]["outcome_stats"] = [
        row for row in payload["game_impact_baseline"]["outcome_stats"]
        if not (row["position"] == "SUP" and row["game_result"] == 0)
    ]

    with pytest.raises(ValueError) as exc:
        validate_baseline_payload(payload)

    message = str(exc.value)
    assert "f1_mean=0" in message
    assert "invalid Game Impact weights for TOP" in message
    assert "invalid Game Impact weights for JUG" in message
    assert "no outcome_stats for ['SUP/0']" in message
    assert "invalid game_impact impact_range" in message


# ----------------------------------------------------------------------------
# baseline 선택 규칙 (SQLite로 실제 SQL 실행)
# ----------------------------------------------------------------------------

@pytest.fixture
def baseline_db(tmp_path, monkeypatch):
    url = f"sqlite:///{tmp_path / 'baselines.db'}"
    engine = create_engine(url)
    with engine.begin() as conn:
        conn.execute(text(
            "CREATE TABLE mmr_baselines (id INTEGER PRIMARY KEY, season TEXT, "
            "baseline_version TEXT, is_active BOOLEAN, mmr_baseline TEXT, "
            "game_impact_baseline TEXT, metadata TEXT, saved_at TEXT)"
        ))
    monkeypatch.setattr(baseline_repository, "get_db_url", lambda: url)
    monkeypatch.setattr(baseline_repository, "get_db_test_mmr_baseline_table", lambda: "mmr_baselines")

    def insert(row_id, season, version, active, saved_at):
        with engine.begin() as conn:
            conn.execute(
                text("INSERT INTO mmr_baselines VALUES (:id, :season, :version, :active, "
                     "'{}', '{}', :metadata, :saved_at)"),
                {"id": row_id, "season": season, "version": version, "active": active,
                 "metadata": json.dumps({"match_count": 200}), "saved_at": saved_at},
            )

    return insert


def test_season_uses_its_own_active_baseline_even_if_older(baseline_db):
    baseline_db(1, "2026", "v-2026", True, "2026-01-01")
    baseline_db(2, "2027", "v-2027", True, "2027-06-01")

    assert baseline_repository.load_baseline_for_season("2026")["baseline_version"] == "v-2026"


def test_season_without_baseline_uses_latest_saved_active_one(baseline_db):
    # 시즌 문자열 순서로는 2026-S10 < 2026-S2지만 saved_at 기준으로 고른다.
    baseline_db(1, "2026-S10", "v-s10", True, "2026-09-01")
    baseline_db(2, "2026-S2", "v-s2", True, "2026-03-01")
    baseline_db(3, "2026-S11", "v-s11-old", False, "2026-12-01")

    picked = baseline_repository.load_baseline_for_season("2026-S11")

    assert picked["baseline_version"] == "v-s10"
    assert picked["season"] == "2026-S10"


def test_saved_at_ties_break_by_latest_id(baseline_db):
    baseline_db(1, "2025", "first", True, "2026-01-01")
    baseline_db(2, "2026", "second", True, "2026-01-01")

    assert baseline_repository.load_baseline_for_season("2027")["baseline_version"] == "second"


def test_no_active_baseline_raises(baseline_db):
    baseline_db(1, "2026", "inactive", False, "2026-01-01")

    with pytest.raises(ValueError, match="No active MMR baseline"):
        baseline_repository.load_baseline_for_season("2026")


# ----------------------------------------------------------------------------
# 저장: 검증 후 저장, 같은 버전 덮어쓰기 금지
# ----------------------------------------------------------------------------

class _FakeConn:
    def __init__(self, rowcount):
        self.rowcount = rowcount
        self.statements = []

    def execute(self, statement, params=None):
        self.statements.append(str(statement))
        return self


class _FakeEngine:
    def __init__(self, conn):
        self.conn = conn

    def begin(self):
        engine = self

        class _Ctx:
            def __enter__(self):
                return engine.conn

            def __exit__(self, *exc):
                return False

        return _Ctx()


def test_saving_existing_version_is_refused(monkeypatch):
    conn = _FakeConn(rowcount=0)
    monkeypatch.setattr(baseline_repository, "create_engine", lambda url: _FakeEngine(conn))
    monkeypatch.setattr(baseline_repository, "get_db_url", lambda: "fake://")

    with pytest.raises(ValueError, match="already exists"):
        baseline_repository.save_mmr_baseline_to_db_test(_valid_payload())
    assert any("DO NOTHING" in sql for sql in conn.statements)


def test_invalid_baseline_is_never_sent_to_db(monkeypatch):
    monkeypatch.setattr(
        baseline_repository, "create_engine", lambda url: pytest.fail("must not connect")
    )

    with pytest.raises(ValueError, match="match_count=10 < 200"):
        baseline_repository.save_mmr_baseline_to_db_test(_valid_payload(match_count=10))


# ----------------------------------------------------------------------------
# run_mmr_once.main() 흐름
# ----------------------------------------------------------------------------

@pytest.fixture
def batch(monkeypatch, tmp_path):
    from test_season_batch import _baseline

    built = _baseline("2026")
    baseline = {**built, "metadata": {**built["metadata"], "match_count": 200}}
    # 원천에 예전 부캐 귀속 컬럼이 섞여 들어와도 저장 결과에는 남지 않아야 한다.
    raw = pd.concat(
        [_season_rows("2026", games=6), _season_rows("2027", games=1).iloc[:9]],
        ignore_index=True,
    ).assign(mmr_player_account="stale-main-account")
    saved = {}
    state = {"existing": 0, "baseline": baseline}

    for name in ("MMR_SEASON", "MMR_GUILD_ID", "MMR_CALCULATION_ID", "MMR_ALLOW_RECALCULATE"):
        monkeypatch.delenv(name, raising=False)
    monkeypatch.setenv("MMR_OUTPUT_FILE", str(tmp_path / "report.json"))
    monkeypatch.setattr(run_mmr_once, "load_match_dataframe_from_db", lambda guild_id: raw.copy())
    monkeypatch.setattr(run_mmr_once, "_assert_result_tables_ready", lambda: None)
    monkeypatch.setattr(run_mmr_once, "_assert_baseline_table_ready", lambda: None)
    monkeypatch.setattr(run_mmr_once, "count_existing_results", lambda scopes: state["existing"])
    monkeypatch.setattr(run_mmr_once, "load_baseline_for_season", lambda season: state["baseline"])

    def fake_save(match_results, user_summary, sink, replace_scopes):
        saved.update(matches=match_results, summary=user_summary, scopes=replace_scopes)

    monkeypatch.setattr(run_mmr_once, "save_mmr_results", fake_save)
    return {"saved": saved, "state": state, "report": tmp_path / "report.json"}


def test_main_skips_invalid_season_but_replaces_its_scope(batch):
    run_mmr_once.main()

    saved = batch["saved"]
    assert set(saved["matches"]["season"]) == {"2026"}
    assert "mmr_player_account" not in saved["matches"].columns
    assert "stale-main-account" not in set(saved["summary"]["player_code"])
    assert set(saved["matches"]["baseline_season"]) == {"2026"}
    assert sorted(saved["scopes"]["season"]) == ["2026", "2027"]
    report = json.loads(batch["report"].read_text(encoding="utf-8"))
    assert report["seasons"] == ["2026"]
    assert report["metadata"]["seasons"]["2026"]["baseline_version"] == "test"


def test_main_refuses_to_overwrite_existing_results(batch):
    batch["state"]["existing"] = 5

    with pytest.raises(SystemExit, match="MMR_ALLOW_RECALCULATE=1"):
        run_mmr_once.main()
    assert not batch["saved"]


def test_main_replaces_existing_results_when_allowed(batch, monkeypatch):
    batch["state"]["existing"] = 5
    monkeypatch.setenv("MMR_ALLOW_RECALCULATE", "1")

    run_mmr_once.main()

    assert batch["saved"]


def test_main_rejects_baseline_made_by_old_path(batch):
    old = batch["state"]["baseline"]
    batch["state"]["baseline"] = {**old, "metadata": {"match_count": 200}}

    with pytest.raises(SystemExit, match="old path"):
        run_mmr_once.main()
    assert not batch["saved"]
