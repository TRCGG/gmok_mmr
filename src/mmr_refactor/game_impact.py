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

import numpy as np
import pandas as pd
from sklearn.ensemble import RandomForestClassifier
from sklearn.preprocessing import MinMaxScaler, QuantileTransformer, StandardScaler


# =====================================================
# 1) Position weights (RandomForest feature importance)
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

    Returns:
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


# =====================================================
# 2) Raw game impact (weighted sum per row)
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
# 3) Position × win/loss 정규화 (game_impact_winloss_norm)
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


# =====================================================
# 4) 인분 / 상대 비교
# =====================================================

def compute_n_person_contribution(
    df: pd.DataFrame,
    norm_col: str = "game_impact_winloss_norm",
    game_id_col: str = "replay_code",
    players_per_game: int = 10,
) -> pd.Series:
    """게임별 norm 합을 기준으로 본인 비중 × 10 (인분 환산)."""
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
    """동일 (game, position) 내 승/패 1:1 비교에서 본인 비중(0~100) 반환.

    같은 (game, position) 그룹에 winner/loser 가 모두 존재해야 매칭된다.
    매칭되지 않은 row 는 NaN.
    """
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
