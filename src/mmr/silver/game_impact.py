"""game_impact 산정 파이프라인 (순수 함수 모듈).

기존 노트북 셀(04 / 05 / 07 / 09)에 흩어져 있던 계산 로직을 그대로 옮겨와
재사용 가능한 함수 형태로 노출한다. **계산 결과(수치)는 변경하지 않는다**.

흐름
----
1. ``derive_position_weights``        → 포지션별 RandomForest feature_importance
2. ``compute_raw_game_impact``        → 포지션 가중합 (raw_game_impact)
3. ``normalize_minmax_0_100``         → 전체 MinMax 0~100 (game_impact)
4. ``normalize_by_position_outcome``  → (position × win/loss) Quantile→MinMax
                                       (game_impact_winloss_norm)
5. ``compute_n_person_contribution``  → 게임 내 인분 (총합 10인분 기준)
6. ``compute_vs_opponent``            → 동일 포지션 상대 대비 비교 점수
"""

from __future__ import annotations

from dataclasses import dataclass

import numpy as np
import pandas as pd
from sklearn.ensemble import RandomForestClassifier
from sklearn.preprocessing import MinMaxScaler, QuantileTransformer, StandardScaler


@dataclass(frozen=True)
class OutcomeNormalizationStats:
    """단일 경기 raw impact 정규화에 사용하는 그룹별 기준값."""

    lower: float
    upper: float


@dataclass(frozen=True)
class GameImpactBaseline:
    """단일 경기 Game Impact 계산에 필요한 고정 baseline."""

    position_weights: pd.DataFrame
    outcome_stats: dict[tuple[str, int], OutcomeNormalizationStats]

    @classmethod
    def from_history(
        cls,
        df: pd.DataFrame,
        metrics: list[str],
        position_weights: pd.DataFrame | None = None,
    ) -> "GameImpactBaseline":
        resolved_weights = resolve_position_weights(
            df,
            metrics=metrics,
            position_weights=position_weights,
        )
        history_df = df.copy()
        history_df["raw_game_impact"] = compute_raw_game_impact(history_df, resolved_weights)
        return cls(
            position_weights=resolved_weights,
            outcome_stats=derive_outcome_normalization_stats(history_df),
        )


# =====================================================
# 1) 포지션별 가중치(랜덤포레스트 중요도)
# =====================================================

def derive_position_weights(
    df: pd.DataFrame,
    metrics: list[str],
    target: str = "game_result",
    position_col: str = "position",
    n_estimators: int = 200,
    random_state: int = 42,
    min_samples: int = 5,
) -> pd.DataFrame:
    """포지션별 RandomForestClassifier 의 feature_importance 를 계산.

    반환:
        DataFrame (index=feature, columns=position, values=importance).
        importance 가 없는 (포지션, feature) 셀은 0 으로 채워진다.

    Notes:
        - df는 변경하지 않는다 (StandardScaler 는 내부 복사본에만 적용).
        - 표본 부족 / 단일 클래스 / 결측 행 0 인 포지션은 제외된다.
    """
    scaler = StandardScaler()
    df_scaled = df.copy()

    try:
        df_scaled[metrics] = scaler.fit_transform(df_scaled[metrics])
    except KeyError as e:
        raise KeyError(
            f"컬럼 {e} 이(가) 데이터프레임에 없습니다. metrics 리스트를 확인하세요."
        ) from e

    position_importances: dict[str, dict[str, float]] = {}

    for pos in df_scaled[position_col].dropna().unique():
        df_pos = df_scaled[df_scaled[position_col] == pos].copy()

        X = df_pos[metrics]
        y = df_pos[target]

        if len(y.unique()) < 2 or len(df_pos) < min_samples:
            print(
                f"안내: 포지션 '{pos}'은 승패 데이터가 부족하거나 표본 수가 부족하여 분석에서 제외됩니다."
            )
            continue

        X = X.replace([np.inf, -np.inf], np.nan).dropna()
        y = y.loc[X.index]

        if X.shape[0] == 0:
            print(f"안내: 포지션 '{pos}'은 유효한 데이터가 없어 분석에서 제외됩니다.")
            continue

        model = RandomForestClassifier(
            n_estimators=n_estimators,
            random_state=random_state,
        )
        model.fit(X, y)

        position_importances[pos] = dict(zip(metrics, model.feature_importances_))

    return pd.DataFrame(position_importances).fillna(0)


def resolve_position_weights(
    df: pd.DataFrame,
    metrics: list[str],
    position_weights: pd.DataFrame | None = None,
    target: str = "game_result",
    position_col: str = "position",
    n_estimators: int = 200,
    random_state: int = 42,
    min_samples: int = 5,
) -> pd.DataFrame:
    """전달된 포지션 가중치를 사용하거나, 없으면 현재 데이터에서 학습한다."""
    if position_weights is not None:
        return position_weights.copy()

    return derive_position_weights(
        df,
        metrics=metrics,
        target=target,
        position_col=position_col,
        n_estimators=n_estimators,
        random_state=random_state,
        min_samples=min_samples,
    )


# =====================================================
# 2) 원본 game impact(row 단위 가중합)
# =====================================================

def compute_raw_game_impact(
    df: pd.DataFrame,
    position_importances_df: pd.DataFrame,
    position_col: str = "position",
) -> pd.Series:
    """포지션별 importance 가중치를 사용해 row 단위 raw_game_impact 계산."""
    weights_dict = position_importances_df.to_dict()

    def _row_impact(row):
        pos = row[position_col]
        if pos not in weights_dict:
            return np.nan

        weights = weights_dict[pos]
        impact = 0.0
        for feature, weight in weights.items():
            if feature in row.index and pd.notnull(row[feature]):
                impact += row[feature] * weight
        return impact

    return df.apply(_row_impact, axis=1)


def normalize_minmax_0_100(series: pd.Series) -> pd.Series:
    """단일 컬럼을 [0, 100] 으로 MinMax 스케일링."""
    scaler = MinMaxScaler(feature_range=(0, 100))
    arr = scaler.fit_transform(series.to_frame())
    return pd.Series(arr.flatten(), index=series.index, name=series.name)


# =====================================================
# 3) 포지션 × 승패 정규화 (game_impact_winloss_norm)
# =====================================================

def normalize_by_position_outcome(
    df: pd.DataFrame,
    raw_col: str = "raw_game_impact",
    position_col: str = "position",
    result_col: str = "game_result",
    random_state: int = 42,
    max_quantiles: int = 1000,
) -> pd.Series:
    """(position × game_result) 그룹별 Quantile→MinMax(0~100) 변환 결과 반환.

    그룹별 표본이 2개 미만이면 NaN.
    원본 df는 변경하지 않는다.
    """
    out = pd.Series(np.nan, index=df.index, name="game_impact_winloss_norm")

    unique_positions = df[position_col].dropna().unique()
    game_results = df[result_col].dropna().unique()

    for pos in unique_positions:
        for result in game_results:
            condition = (df[position_col] == pos) & (df[result_col] == result)
            idx = df.loc[condition].index

            if idx.empty:
                continue

            values = df.loc[idx, raw_col].values
            mask = ~np.isnan(values) & ~np.isinf(values)
            valid_values = values[mask]
            valid_idx = idx[mask]

            if len(valid_values) < 2:
                print(
                    f"✨ 경고: '{pos}' 포지션, "
                    f"{'승리' if result == 1 else '패배'} 데이터가 부족하여 정규 분포 변환을 스킵합니다."
                )
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


def derive_outcome_normalization_stats(
    df: pd.DataFrame,
    raw_col: str = "raw_game_impact",
    position_col: str = "position",
    result_col: str = "game_result",
    lower_quantile: float = 0.05,
    upper_quantile: float = 0.95,
) -> dict[tuple[str, int], OutcomeNormalizationStats]:
    """이력 데이터에서 단일 경기 정규화에 사용할 position/result별 기준값을 만든다."""
    stats: dict[tuple[str, int], OutcomeNormalizationStats] = {}

    for (pos, result), group in df.groupby([position_col, result_col]):
        values = group[raw_col].replace([np.inf, -np.inf], np.nan).dropna()
        if values.empty:
            continue

        lower = float(values.quantile(lower_quantile))
        upper = float(values.quantile(upper_quantile))
        if np.isclose(lower, upper):
            lower = float(values.min())
            upper = float(values.max())
        if np.isclose(lower, upper):
            lower -= 0.5
            upper += 0.5

        stats[(pos, int(result))] = OutcomeNormalizationStats(lower=lower, upper=upper)

    return stats


def apply_outcome_normalization_stats(
    df: pd.DataFrame,
    outcome_stats: dict[tuple[str, int], OutcomeNormalizationStats],
    raw_col: str = "raw_game_impact",
    position_col: str = "position",
    result_col: str = "game_result",
) -> pd.Series:
    """저장된 기준값으로 단일 경기 raw impact를 0~100 점수로 변환한다."""
    values = []
    for _, row in df.iterrows():
        stats = outcome_stats.get((row[position_col], int(row[result_col])))
        raw_value = row[raw_col]
        if stats is None or pd.isna(raw_value):
            values.append(np.nan)
            continue

        scaled = (raw_value - stats.lower) / (stats.upper - stats.lower) * 100
        values.append(float(np.clip(scaled, 0, 100)))

    return pd.Series(values, index=df.index, name="game_impact_winloss_norm")


def apply_game_impact_baseline(
    df: pd.DataFrame,
    baseline: GameImpactBaseline,
) -> pd.DataFrame:
    out = df.copy()

    # 저장된 position_weights로 raw_game_impact 재계산
    out["raw_game_impact"] = compute_raw_game_impact(
        out,
        baseline.position_weights,
    )

    # raw_game_impact를 0~100 범위로 정규화
    out["game_impact"] = normalize_minmax_0_100(
        out["raw_game_impact"]
    )

    # 현재 데이터로 재정규화하지 않고
    # baseline에 저장된 outcome_stats를 사용해 원본 결과 재현
    out["game_impact_winloss_norm"] = apply_outcome_normalization_stats(
        out,
        baseline.outcome_stats,
        raw_col="raw_game_impact",
        position_col="position",
        result_col="game_result",
    )

    # 팀 내 기여도 계산
    out["game_n_person_contribution"] = compute_n_person_contribution(out)

    # 같은 포지션 상대와 비교한 영향력 계산
    out["game_impact_vs_opponent"] = compute_vs_opponent(out)

    return out

# =====================================================
# 4) 인분 / 상대 비교
# =====================================================

def compute_n_person_contribution(
    df: pd.DataFrame,
    norm_col: str = "game_impact_winloss_norm",
    game_id_col: str = "replay_code",
    position_col: str = "position",
    players_per_game: int = 10,
) -> pd.Series:
    """포지션 내 norm 합을 기준으로 본인 비중을 인분으로 환산한다.

    포지션마다 기여도 합계가 동일해지도록 균형화하여, 특정 position의 비중이
    과도하게 커지거나 작아지지 않도록 한다. position 정보가 없으면 게임 전체
    합을 기준으로 기존 방식(본인 비중 × 10)을 사용한다.
    5개 포지션이면 포지션당 목표 비중은 2, 한 게임 전체 합은 10이 된다.
    """
    if position_col not in df.columns:
        game_wide_sum = df.groupby(game_id_col)[norm_col].transform("sum")
        return (df[norm_col] / game_wide_sum * players_per_game).fillna(0)

    group_cols = [game_id_col, position_col]
    position_sum = df.groupby(group_cols)[norm_col].transform("sum")
    positions_per_game = df.groupby(game_id_col)[position_col].transform("nunique")
    position_target = players_per_game / positions_per_game.replace(0, np.nan)

    contribution = df[norm_col] / position_sum * position_target

    zero_or_missing_sum = position_sum.isna() | np.isclose(position_sum, 0)
    if zero_or_missing_sum.any():
        players_per_position = df.groupby(group_cols)[norm_col].transform("size")
        fallback = position_target / players_per_position.replace(0, np.nan)
        contribution = contribution.mask(zero_or_missing_sum, fallback)

    return contribution.fillna(0)


def compute_vs_opponent(
    df: pd.DataFrame,
    norm_col: str = "game_impact_winloss_norm",
    game_id_col: str = "replay_code",
    position_col: str = "position",
    result_col: str = "game_result",
    puuid_col: str = "puuid",
) -> pd.Series:
    """동일 (game, position) 내 승/패 1:1 비교에서 본인 비중(0~100) 반환.

    같은 (game, position) 그룹에 winner/loser 가 모두 존재해야 매칭된다.
    매칭되지 않은 row 는 NaN.
    """
    df_comp = df[[game_id_col, position_col, result_col, norm_col, puuid_col]].copy()
    df_comp["_row_id"] = df.index

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
            "_row_id": r["_row_id_winner"],
            game_id_col: r[game_id_col],
            position_col: r[position_col],
            puuid_col: r[f"{puuid_col}_winner"],
            "game_impact_vs_opponent": r["winner_score"],
        })
        rows.append({
            "_row_id": r["_row_id_loser"],
            game_id_col: r[game_id_col],
            position_col: r[position_col],
            puuid_col: r[f"{puuid_col}_loser"],
            "game_impact_vs_opponent": r["loser_score"],
        })

    if not rows:
        return pd.Series(np.nan, index=df.index, name="game_impact_vs_opponent")

    vs_df = pd.DataFrame(rows)
    return (
        vs_df
        .drop_duplicates(subset=["_row_id"])
        .set_index("_row_id")
        .reindex(df.index)["game_impact_vs_opponent"]
        .rename("game_impact_vs_opponent")
    )
