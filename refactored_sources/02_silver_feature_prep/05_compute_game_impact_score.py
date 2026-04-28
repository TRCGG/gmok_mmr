import pandas as pd
import numpy as np
from sklearn.preprocessing import MinMaxScaler

# ------------------------------------
# 1. 포지션별 importance 결과 불러오기
# ------------------------------------
# index = feature명, columns = 포지션명 (TOP, JUNGLE, MIDDLE, BOTTOM, UTILITY)
position_importances_df = position_importances_df.copy()

# 가중치 딕셔너리로 변환
position_weights = position_importances_df.to_dict()

# ------------------------------------
# 2. 플레이어별 game_impact 계산 함수
# ------------------------------------
def calculate_game_impact(row, weights_dict):
    pos = row['position']

    if pos not in weights_dict:
        return np.nan  # 예외 처리

    weights = weights_dict[pos]  # 해당 포지션의 feature importance dict

    # feature별 값 × 가중치 → 가중합
    impact_score = 0
    for feature, weight in weights.items():
        if feature in row.index and pd.notnull(row[feature]):
            impact_score += row[feature] * weight

    return impact_score

# ------------------------------------
# 3. game_impact 계산 적용
# ------------------------------------
mmr_df_cleaned_default['raw_game_impact'] = mmr_df_cleaned_default.apply(
    lambda row: calculate_game_impact(row, position_weights),
    axis=1
)

# ------------------------------------
# 4. 정규화 (0 ~ 100 점수)
# ------------------------------------
scaler = MinMaxScaler(feature_range=(0, 100))
mmr_df_cleaned_default['game_impact'] = scaler.fit_transform(
    mmr_df_cleaned_default[['raw_game_impact']]
)

# ------------------------------------
# 5. 확인
# ------------------------------------
print(
    mmr_df_cleaned_default[['puuid', 'position', 'raw_game_impact', 'game_impact']].head(20)
)


mmr_df_cleaned_default.info()
