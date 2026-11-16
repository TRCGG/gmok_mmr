"""원천 경기의 시즌 값 정규화.

시즌은 계산 시점 값이 아니라 경기의 ``custom_match.season``을 따른다.
"""

from __future__ import annotations

import pandas as pd


def normalize_season(raw_df: pd.DataFrame) -> pd.Series:
    """경기의 custom_match.season을 공백 없는 문자열로 맞추고 빈 값은 거부한다."""
    if "season" not in raw_df.columns:
        raise RuntimeError("Raw matches require custom_match.season values.")
    seasons = raw_df["season"]
    blank = seasons.isna() | seasons.astype(str).str.strip().eq("")
    if blank.any():
        missing = raw_df.loc[blank]
        sample = (
            missing["replay_code"].drop_duplicates().head(5).tolist()
            if "replay_code" in missing.columns
            else missing.index[:5].tolist()
        )
        raise RuntimeError(
            f"Raw matches require custom_match.season values. Missing for: {sample}"
        )
    return seasons.astype(str).str.strip()
