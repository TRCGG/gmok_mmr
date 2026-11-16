"""시즌 baseline을 계산해 DB에 저장한다(로컬 수동 실행).

전체 길드의 해당 시즌 경기(``custom_match.season``)로 baseline을 만든다.
5v5 검증을 통과한 경기가 200판 미만이거나 baseline이 퇴화하면 저장하지 않고
중단한다. 같은 (season, baseline_version)이 이미 있으면 덮어쓰지 않고 중단한다.
저장하면 같은 시즌의 기존 baseline은 비활성화되고, 이후 MMR 계산은 새 baseline을
쓴다. 이미 계산된 결과는 다시 계산하지 않는다.

Usage::

    python scripts/calculate_baseline.py --season 2026 --baseline-version 20261117 --dry-run
    python scripts/calculate_baseline.py --season 2026 --baseline-version 20261117
"""

from __future__ import annotations

import argparse
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[1]
for _path in (ROOT / "src", ROOT / "tests"):
    if str(_path) not in sys.path:
        sys.path.insert(0, str(_path))

try:
    from dotenv import load_dotenv
except ImportError as exc:  # pragma: no cover - dependency is in requirements.txt
    raise SystemExit("python-dotenv is required. Run: pip install -r requirements.txt") from exc

load_dotenv(ROOT / ".env")

from mmr.gold.baseline import (
    MIN_BASELINE_MATCHES,
    calculate_service_baseline,
    service_baseline_to_payload,
    validate_baseline_payload,
)
from mmr.serving.service import NoValidMatchesError, build_base_feature_dataframe
from harness.db_test.baseline_repository import (
    BASELINE_SCOPE_ALL_GUILDS,
    baseline_version_exists,
    save_mmr_baseline_to_db_test,
)
from harness.db_test.repository import load_match_dataframe_from_db


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--season", required=True, help="custom_match.season 값")
    parser.add_argument("--baseline-version", required=True)
    parser.add_argument("--dry-run", action="store_true", help="계산만 하고 저장하지 않는다")
    args = parser.parse_args()

    season = args.season.strip()
    baseline_version = args.baseline_version.strip()
    if not args.dry_run and baseline_version_exists(season, baseline_version):
        raise SystemExit(
            f"Baseline {baseline_version!r} for season {season!r} already exists. "
            "Use a new --baseline-version; existing baselines are never overwritten."
        )

    print(f"Loading raw MMR rows for season {season!r} (all guilds) ...")
    raw_df = load_match_dataframe_from_db(guild_id=None)
    payload = build_season_baseline(raw_df, season=season, baseline_version=baseline_version)
    metadata = payload["metadata"]
    summary = (
        f"baseline {baseline_version!r} for season {season!r} "
        f"({metadata['match_count']:,} matches, "
        f"{metadata['player_game_row_count']:,} player-game rows)"
    )
    if args.dry_run:
        print(f"DRY RUN: calculated {summary}. Not saved.")
        return
    try:
        save_mmr_baseline_to_db_test(payload, is_active=True)
    except ValueError as exc:
        raise SystemExit(f"Baseline not saved. {exc}") from exc
    print(f"APPLIED: saved active {summary}.")
    print(
        f"Season {season!r} now uses this baseline. Seasons without their own active "
        "baseline also fall back to it, because it is now the most recently saved one."
    )


def build_season_baseline(
    raw_df,
    *,
    season: str,
    baseline_version: str,
    min_matches: int = MIN_BASELINE_MATCHES,
) -> dict:
    """한 시즌의 원천 경기로 baseline payload를 만들고 사용 가능 여부를 검증한다.

    ``min_matches``는 테스트용 인자다. CLI는 항상 200판 기준을 쓴다.
    """
    if "season" not in raw_df.columns:
        raise SystemExit("Raw matches require custom_match.season values.")
    # 요청 시즌 행만 고른다. 다른 시즌의 빈 season 값 때문에 실패하지 않게 한다.
    season_values = raw_df["season"].astype("string").str.strip()
    season_df = raw_df[season_values.eq(season).fillna(False).astype(bool)]
    if season_df.empty:
        raise SystemExit(f"No eligible matches were found for season {season!r}.")
    try:
        feature_df = build_base_feature_dataframe(season_df)
    except NoValidMatchesError as exc:
        raise SystemExit(f"Season {season!r}: {exc}") from exc
    baseline = calculate_service_baseline(
        feature_df,
        baseline_version=baseline_version,
        season=season,
    )
    payload = service_baseline_to_payload(
        baseline,
        match_count=feature_df[["guild_id", "replay_code"]].drop_duplicates().shape[0],
        player_game_row_count=len(feature_df),
    )
    payload["metadata"].update({"scope": BASELINE_SCOPE_ALL_GUILDS, "source_season": season})
    try:
        validate_baseline_payload(payload, min_matches=min_matches)
    except ValueError as exc:
        raise SystemExit(f"Baseline not saved. {exc}") from exc
    return payload


if __name__ == "__main__":
    main()
