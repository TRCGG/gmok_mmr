"""Reference-only consolidated MMR calculation logic.

This file collects the current MMR-side logic in one place for review.
It is not imported by the runtime pipeline. Runtime code remains in:

- src/mmr_refactor/silver.py
- src/mmr_refactor/game_impact.py
- src/mmr_refactor/mmr.py
- scripts/main_pipeline.py

Scope:
    raw match DataFrame
    -> basic cleaning
    -> derived features
    -> Game Impact
    -> n-person contribution
    -> opponent comparison
    -> ELO-based MMR update
    -> user summary

Excluded:
    DB load/save
    API load/save
    migrations
    reporting/radar chart code
"""

from __future__ import annotations

import numpy as np
import pandas as pd
from sklearn.ensemble import RandomForestClassifier
from sklearn.preprocessing import MinMaxScaler, QuantileTransformer, StandardScaler


# =============================================================================
# Constants
# =============================================================================

DEFAULT_NA_EXCLUDE_COLS: tuple[str, ...] = (
    "jungle_cs_own",
    "jungle_cs_enemy",
    "dragon_kills",
    "baron_kills",
    "herald_kills",
    "horde_kills",
    "damage_to_epic_monsters",
    "objectives_stolen",
    "barracks_killed",
)

BASE_METRICS: list[str] = [
    "kills",
    "deaths",
    "assists",
    "gold_per_min",
    "exp_per_min",
    "dpm",
    "damage_to_turrets_per_min",
    "damage_taken_per_min",
    "vision_score",
    "cs_per_min",
    "kda",
    "damage_taken_per_death",
    "damage_dealt_per_death",
    "wards_placed_per_min",
    "wards_killed_per_min",
    "cc_time_per_min",
    "heal_on_teammates",
    "shield_on_teammates",
    "lane_gold_diff",
]

BASE_WIN: int = 20
BASE_LOSS: int = -15

ALPHA: float = 0.6
BETA: float = 0.4
GAMMA: float = 0.2

INITIAL_MMR: int = 1300
MMR_MIN_CHANGE: int = -25
MMR_MAX_CHANGE: int = 30

MMR_K_DECAY_START: int = 1500
MMR_K_DECAY_RATE: float = 0.002
MMR_K_MIN: float = 0.35

DEFAULT_POSITIONS: tuple[str, ...] = (
    "TOP",
    "BOTTOM",
    "MIDDLE",
    "JUNGLE",
    "UTILITY",
)


# =============================================================================
# 1. Basic cleaning
# =============================================================================

def clean_match_data(
    df: pd.DataFrame,
    na_exclude_cols: tuple[str, ...] = DEFAULT_NA_EXCLUDE_COLS,
    convert_duration_to_minutes: bool = True,
) -> pd.DataFrame:
    """Clean raw match rows before feature engineering.

    Args:
        df: Raw match-level player rows.
        na_exclude_cols: Columns ignored by NA inspection.
        convert_duration_to_minutes: Convert ``game_duration`` from seconds to minutes.

    Returns:
        Cleaned DataFrame with duplicate rows removed and ``game_result`` normalized.
    """
    del na_exclude_cols
    out = df.drop_duplicates().copy()

    if "win" in out.columns and "game_result" not in out.columns:
        out["game_result"] = (
            out["win"].astype(str).str.upper().map({"TRUE": 1, "FALSE": 0})
        )
        out = out.drop(columns=["win"])

    for col in ("heal_on_teammates", "shield_on_teammates"):
        if col in out.columns:
            out[col] = out[col].fillna(0)

    if convert_duration_to_minutes and "game_duration" in out.columns:
        out["game_duration"] = (out["game_duration"] / 60).round(2)

    return out


def find_rows_with_na(
    df: pd.DataFrame,
    na_exclude_cols: tuple[str, ...] = DEFAULT_NA_EXCLUDE_COLS,
) -> pd.DataFrame:
    """Return rows that contain NA values outside explicitly excluded columns."""
    drop_cols = [c for c in na_exclude_cols if c in df.columns]
    check_df = df.drop(columns=drop_cols)
    return df[check_df.isnull().any(axis=1)]


# =============================================================================
# 2. Basic derived features
# =============================================================================

def add_basic_features(df: pd.DataFrame) -> pd.DataFrame:
    """Create derived numeric features used by Game Impact and MMR logic.

    Expected input columns:
        game_duration, deaths, kills, assists, gold, damage_to_champions,
        damage_taken, cc_time.
    """
    out = df.copy()
    duration = out["game_duration"].replace(0, np.nan)
    deaths = out["deaths"].replace(0, np.nan)

    out["gold_per_min"] = out["gold"] / duration
    out["dpm"] = out["damage_to_champions"] / duration
    out["damage_taken_per_min"] = out["damage_taken"] / duration
    out["cc_time_per_min"] = out["cc_time"] / duration
    out["kda"] = (out["kills"] + out["assists"]) / deaths
    out["damage_taken_per_death"] = out["damage_taken"] / deaths
    out["damage_dealt_per_death"] = out["damage_to_champions"] / deaths

    if "exp" in out.columns:
        out["exp_per_min"] = out["exp"] / duration
    if "damage_to_turrets" in out.columns:
        out["damage_to_turrets_per_min"] = out["damage_to_turrets"] / duration
    if {"minions_killed", "neutral_minions_killed"}.issubset(out.columns):
        out["cs_per_min"] = (
            out["minions_killed"] + out["neutral_minions_killed"]
        ) / duration
    if "wards_placed" in out.columns:
        out["wards_placed_per_min"] = out["wards_placed"] / duration
    if "wards_killed" in out.columns:
        out["wards_killed_per_min"] = out["wards_killed"] / duration
    if "time_spent_dead" in out.columns:
        out["dead_time_pct"] = out["time_spent_dead"] / (duration * 60) * 100

    if "lane_gold_diff" not in out.columns and {
        "replay_code",
        "position",
        "puuid",
        "gold",
    }.issubset(out.columns):
        opponent_gold_sum = (
            out.groupby(["replay_code", "position"])["gold"].transform("sum")
            - out["gold"]
        )
        opponent_count = (
            out.groupby(["replay_code", "position"])["gold"].transform("count")
            - 1
        )
        opponent_gold = opponent_gold_sum / opponent_count.replace(0, np.nan)
        out["lane_gold_diff"] = out["gold"] - opponent_gold

    out = out.replace([np.inf, -np.inf], np.nan)
    numeric_cols = out.select_dtypes(include="number").columns
    out[numeric_cols] = out[numeric_cols].fillna(0)
    return out


# =============================================================================
# 3. Game Impact
# =============================================================================

def derive_position_weights(
    df: pd.DataFrame,
    metrics: list[str],
    target: str = "game_result",
    position_col: str = "position",
    n_estimators: int = 200,
    random_state: int = 42,
    min_samples: int = 5,
) -> pd.DataFrame:
    """Calculate RandomForest feature importance by position.

    Returns:
        DataFrame where index is feature name and columns are positions.
    """
    scaler = StandardScaler()
    df_scaled = df.copy()
    df_scaled[metrics] = scaler.fit_transform(df_scaled[metrics])

    position_importances: dict[str, dict[str, float]] = {}

    for pos in df_scaled[position_col].dropna().unique():
        df_pos = df_scaled[df_scaled[position_col] == pos].copy()
        x = df_pos[metrics]
        y = df_pos[target]

        if len(y.unique()) < 2 or len(df_pos) < min_samples:
            continue

        x = x.replace([np.inf, -np.inf], np.nan).dropna()
        y = y.loc[x.index]

        if x.shape[0] == 0:
            continue

        model = RandomForestClassifier(
            n_estimators=n_estimators,
            random_state=random_state,
        )
        model.fit(x, y)
        position_importances[pos] = dict(zip(metrics, model.feature_importances_))

    return pd.DataFrame(position_importances).fillna(0)


def compute_raw_game_impact(
    df: pd.DataFrame,
    position_importances_df: pd.DataFrame,
    position_col: str = "position",
) -> pd.Series:
    """Calculate row-level weighted Game Impact by position."""
    weights_dict = position_importances_df.to_dict()

    def _row_impact(row: pd.Series) -> float:
        pos = row[position_col]
        if pos not in weights_dict:
            return np.nan

        impact = 0.0
        for feature, weight in weights_dict[pos].items():
            if feature in row.index and pd.notnull(row[feature]):
                impact += row[feature] * weight
        return impact

    return df.apply(_row_impact, axis=1)


def normalize_minmax_0_100(series: pd.Series) -> pd.Series:
    """Scale a numeric series to 0-100."""
    scaler = MinMaxScaler(feature_range=(0, 100))
    arr = scaler.fit_transform(series.to_frame())
    return pd.Series(arr.flatten(), index=series.index, name=series.name)


def normalize_by_position_outcome(
    df: pd.DataFrame,
    raw_col: str = "raw_game_impact",
    position_col: str = "position",
    result_col: str = "game_result",
    random_state: int = 42,
    max_quantiles: int = 1000,
) -> pd.Series:
    """Normalize Game Impact within each position and win/loss group."""
    out = pd.Series(np.nan, index=df.index, name="game_impact_winloss_norm")

    for pos in df[position_col].dropna().unique():
        for result in df[result_col].dropna().unique():
            condition = (df[position_col] == pos) & (df[result_col] == result)
            idx = df.loc[condition].index

            if idx.empty:
                continue

            values = df.loc[idx, raw_col].values
            mask = ~np.isnan(values) & ~np.isinf(values)
            valid_values = values[mask]
            valid_idx = idx[mask]

            if len(valid_values) < 2:
                continue

            n_quantiles_val = min(len(valid_values), max_quantiles)
            qt = QuantileTransformer(
                output_distribution="normal",
                random_state=random_state,
                n_quantiles=n_quantiles_val,
            )
            transformed = qt.fit_transform(valid_values.reshape(-1, 1))

            mm = MinMaxScaler(feature_range=(0, 100))
            scaled = mm.fit_transform(transformed)
            out.loc[valid_idx] = scaled.flatten()

    return out


def compute_n_person_contribution(
    df: pd.DataFrame,
    norm_col: str = "game_impact_winloss_norm",
    game_id_col: str = "replay_code",
    players_per_game: int = 10,
) -> pd.Series:
    """Calculate each player's share of a 10-person match contribution total."""
    game_wide_sum = df.groupby(game_id_col)[norm_col].transform("sum")
    return (df[norm_col] / game_wide_sum * players_per_game).fillna(0)


def compute_vs_opponent(
    df: pd.DataFrame,
    norm_col: str = "game_impact_winloss_norm",
    game_id_col: str = "replay_code",
    position_col: str = "position",
    result_col: str = "game_result",
    puuid_col: str = "puuid",
) -> pd.Series:
    """Compare a player against the same-position opponent in the same game."""
    df_comp = df[[game_id_col, position_col, result_col, norm_col, puuid_col]].copy()

    merged = pd.merge(
        df_comp[df_comp[result_col] == 1],
        df_comp[df_comp[result_col] == 0],
        on=[game_id_col, position_col],
        suffixes=("_winner", "_loser"),
        how="inner",
    )

    merged["total_impact"] = (
        merged[f"{norm_col}_winner"] + merged[f"{norm_col}_loser"]
    )
    merged["winner_score"] = (
        merged[f"{norm_col}_winner"] / merged["total_impact"] * 100
    ).fillna(0)
    merged["loser_score"] = (
        merged[f"{norm_col}_loser"] / merged["total_impact"] * 100
    ).fillna(0)

    rows = []
    for _, r in merged.iterrows():
        rows.append({
            game_id_col: r[game_id_col],
            position_col: r[position_col],
            puuid_col: r[f"{puuid_col}_winner"],
            "game_impact_vs_opponent": r["winner_score"],
        })
        rows.append({
            game_id_col: r[game_id_col],
            position_col: r[position_col],
            puuid_col: r[f"{puuid_col}_loser"],
            "game_impact_vs_opponent": r["loser_score"],
        })

    if not rows:
        return pd.Series(np.nan, index=df.index, name="game_impact_vs_opponent")

    vs_df = pd.DataFrame(rows)
    merged_back = df[[game_id_col, position_col, puuid_col]].merge(
        vs_df,
        on=[game_id_col, position_col, puuid_col],
        how="left",
    )
    return merged_back["game_impact_vs_opponent"].rename("game_impact_vs_opponent")


# =============================================================================
# 4. ELO MMR
# =============================================================================

def expected_performance(mmr_a: float, mmr_b: float) -> float:
    """Calculate ELO expected performance between two MMR values."""
    return 1 / (1 + 10 ** ((mmr_b - mmr_a) / 400))


def calculate_personal_factor(row: pd.Series, f1_mean: float, f2_mean: float) -> float:
    """Calculate personal performance multiplier."""
    f1 = row["game_n_person_contribution"] / f1_mean if f1_mean != 0 else 1

    if pd.isna(row["game_impact_vs_opponent"]) or f2_mean == 0:
        f2 = 1
    else:
        f2 = row["game_impact_vs_opponent"] / f2_mean

    f1 = np.clip(f1, 0.5, 2)
    f2 = np.clip(f2, 0.5, 2)
    return (f1 ** ALPHA) * (f2 ** BETA)


def calculate_k_factor(mmr: float) -> float:
    """Reduce update volatility as MMR rises, with a fixed minimum."""
    k = 1.0
    if mmr > MMR_K_DECAY_START:
        k = 1.0 - ((mmr - MMR_K_DECAY_START) * MMR_K_DECAY_RATE)
    return max(k, MMR_K_MIN)


def update_mmr_elo(df: pd.DataFrame) -> tuple[pd.DataFrame, pd.DataFrame]:
    """Update position MMR and total MMR by game order."""
    df = df.sort_values(by=["played_at", "replay_code", "puuid"]).copy()

    player_pos_mmr: dict[str, dict[str, int]] = {}
    player_pos_record: dict[str, dict[str, dict[str, int]]] = {}
    updated_rows: list[pd.Series] = []

    f1_mean = df["game_n_person_contribution"].mean()
    f2_mean = df["game_impact_vs_opponent"].mean()

    for _, game_df in df.groupby("replay_code", sort=False):
        pre_mmr: dict[tuple[str, str], int] = {}
        game_updates = []

        for _, row in game_df.iterrows():
            pid = row["puuid"]
            pos = row["position"]

            player_pos_mmr.setdefault(pid, {})
            player_pos_record.setdefault(pid, {})
            player_pos_mmr[pid].setdefault(pos, INITIAL_MMR)
            player_pos_record[pid].setdefault(pos, {"win": 0, "total": 0})

            pre_mmr[(pid, pos)] = int(player_pos_mmr[pid][pos])

        for _, row in game_df.iterrows():
            pid = row["puuid"]
            pos = row["position"]
            current_mmr = pre_mmr[(pid, pos)]

            opponent_df = game_df[
                (game_df["position"] == pos) & (game_df["puuid"] != pid)
            ]

            opponent_mmr = INITIAL_MMR
            if not opponent_df.empty:
                opp_id = opponent_df.iloc[0]["puuid"]
                opponent_mmr = pre_mmr.get((opp_id, pos), INITIAL_MMR)

            expected = expected_performance(current_mmr, opponent_mmr)
            actual = (
                row["game_impact_vs_opponent"] / 100
                if not pd.isna(row["game_impact_vs_opponent"])
                else expected
            )

            relative_factor = actual / expected if expected > 0 else 1
            personal_factor = calculate_personal_factor(row, f1_mean, f2_mean)
            final_factor = personal_factor * (relative_factor ** GAMMA)
            k = calculate_k_factor(current_mmr)

            if row["game_result"] == 1:
                delta = BASE_WIN * final_factor * k
                delta = np.clip(max(delta, 12), 12, MMR_MAX_CHANGE)
            else:
                delta = BASE_LOSS * final_factor * k
                delta = np.clip(min(delta, -12), MMR_MIN_CHANGE, -12)

            delta = int(round(delta))
            new_mmr = int(current_mmr + delta)

            row_copy = row.copy()
            row_copy["pre_game_pos_mmr"] = int(current_mmr)
            row_copy["expected_score"] = round(expected, 4)
            row_copy["actual_score"] = round(actual, 4)
            row_copy["relative_factor"] = round(relative_factor, 4)
            row_copy["personal_factor"] = round(personal_factor, 4)
            row_copy["final_factor"] = round(final_factor, 4)
            row_copy["mmr_change"] = int(delta)
            row_copy["pos_cumulative_mmr"] = int(new_mmr)

            game_updates.append((pid, pos, row["game_result"], new_mmr, row_copy))

        for pid, pos, result, new_mmr, row_copy in game_updates:
            player_pos_mmr[pid][pos] = new_mmr
            player_pos_record[pid][pos]["total"] += 1

            if result == 1:
                player_pos_record[pid][pos]["win"] += 1

            weighted_sum = 0
            total_games = 0
            for p in player_pos_mmr[pid]:
                games = player_pos_record[pid][p]["total"]
                weighted_sum += player_pos_mmr[pid][p] * games
                total_games += games

            row_copy["total_mmr"] = (
                int(round(weighted_sum / total_games))
                if total_games > 0
                else INITIAL_MMR
            )
            updated_rows.append(row_copy)

    mmr_df_updated = pd.DataFrame(updated_rows)
    summary_df = make_summary_df_wide(mmr_df_updated)
    return mmr_df_updated, summary_df


def make_summary_df_wide(
    mmr_df_updated: pd.DataFrame,
    positions: tuple[str, ...] = DEFAULT_POSITIONS,
) -> pd.DataFrame:
    """Build per-user total and position summary from row-level MMR output."""
    pos_last = (
        mmr_df_updated
        .sort_values(by=["played_at", "replay_code"])
        .groupby(["puuid", "position"], as_index=False)
        .tail(1)
        [["puuid", "position", "pos_cumulative_mmr"]]
        .rename(columns={"pos_cumulative_mmr": "pos_mmr"})
    )

    pos_stats = (
        mmr_df_updated
        .groupby(["puuid", "position"], as_index=False)
        .agg(
            pos_games=("game_result", "count"),
            pos_wins=("game_result", "sum"),
        )
    )
    pos_stats["pos_winrate"] = (
        pos_stats["pos_wins"] / pos_stats["pos_games"] * 100
    ).round(2)

    pos_summary = pos_last.merge(pos_stats, on=["puuid", "position"], how="outer")

    mmr_wide = pos_summary.pivot(index="puuid", columns="position", values="pos_mmr")
    winrate_wide = pos_summary.pivot(index="puuid", columns="position", values="pos_winrate")
    games_wide = pos_summary.pivot(index="puuid", columns="position", values="pos_games")

    mmr_wide.columns = [f"{c}_mmr" for c in mmr_wide.columns]
    winrate_wide.columns = [f"{c}_winrate" for c in winrate_wide.columns]
    games_wide.columns = [f"{c}_games" for c in games_wide.columns]

    overall_summary = (
        mmr_df_updated
        .groupby("puuid", as_index=False)
        .agg(
            total_games=("game_result", "count"),
            total_wins=("game_result", "sum"),
        )
    )
    overall_summary["overall_winrate"] = (
        overall_summary["total_wins"] / overall_summary["total_games"] * 100
    ).round(2)

    total_mmr_df = (
        mmr_df_updated
        .sort_values(by=["played_at", "replay_code"])
        .groupby("puuid", as_index=False)
        .tail(1)
        [["puuid", "total_mmr"]]
    )

    overall_summary = (
        overall_summary
        .merge(total_mmr_df, on="puuid", how="left")
        .drop(columns="total_wins")
    )

    summary_df = (
        overall_summary
        .merge(mmr_wide, on="puuid", how="left")
        .merge(winrate_wide, on="puuid", how="left")
        .merge(games_wide, on="puuid", how="left")
    )

    for pos in positions:
        if f"{pos}_mmr" not in summary_df.columns:
            summary_df[f"{pos}_mmr"] = np.nan
        if f"{pos}_winrate" not in summary_df.columns:
            summary_df[f"{pos}_winrate"] = np.nan
        if f"{pos}_games" not in summary_df.columns:
            summary_df[f"{pos}_games"] = 0

    ordered_cols = ["puuid", "total_mmr", "total_games", "overall_winrate"]
    for pos in positions:
        ordered_cols += [f"{pos}_mmr", f"{pos}_winrate", f"{pos}_games"]

    return (
        summary_df[ordered_cols]
        .sort_values(by="total_mmr", ascending=False)
        .reset_index(drop=True)
    )


# =============================================================================
# 5. One-file orchestration
# =============================================================================

def calculate_mmr_outputs(raw_df: pd.DataFrame) -> tuple[pd.DataFrame, pd.DataFrame]:
    """Run the full MMR calculation from raw rows to row-level and summary output.

    Args:
        raw_df: Raw match rows already loaded from DB/API.

    Returns:
        ``(mmr_df_updated, summary_df)``.
    """
    clean_df = clean_match_data(raw_df, convert_duration_to_minutes=True)
    feature_df = add_basic_features(clean_df)

    metrics = [c for c in BASE_METRICS if c in feature_df.columns]
    if not metrics:
        raise RuntimeError("No usable metric columns were found.")

    position_weights = derive_position_weights(feature_df, metrics=metrics)
    feature_df["raw_game_impact"] = compute_raw_game_impact(
        feature_df,
        position_weights,
    )
    feature_df["game_impact"] = normalize_minmax_0_100(
        feature_df["raw_game_impact"],
    )
    feature_df["game_impact_winloss_norm"] = normalize_by_position_outcome(feature_df)
    feature_df["game_n_person_contribution"] = compute_n_person_contribution(feature_df)
    feature_df["game_impact_vs_opponent"] = compute_vs_opponent(feature_df)

    return update_mmr_elo(feature_df)
