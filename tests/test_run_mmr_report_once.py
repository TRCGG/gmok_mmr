from __future__ import annotations

from scripts import run_mmr_report_once


def test_combined_report_runner_applies_migration_before_batch(monkeypatch):
    calls = []
    monkeypatch.setattr(
        run_mmr_report_once, "apply_report_migration", lambda: calls.append("migration")
    )
    monkeypatch.setattr(
        run_mmr_report_once, "run_mmr_once", lambda: calls.append("batch")
    )

    run_mmr_report_once.main()

    assert calls == ["migration", "batch"]
