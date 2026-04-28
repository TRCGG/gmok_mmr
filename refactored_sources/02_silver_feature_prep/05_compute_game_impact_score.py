"""row 단위 raw_game_impact + 전체 MinMax(0~100) game_impact 산출.

핵심 계산은 `mmr_refactor.game_impact` 로 위임.
"""

import numpy as np
import pandas as pd

from mmr_refactor.game_impact import compute_raw_game_impact, normalize_minmax_0_100

# raw_game_impact: 포지션별 importance 가중합
mmr_df_cleaned_default['raw_game_impact'] = compute_raw_game_impact(
    mmr_df_cleaned_default,
    position_importances_df,
)

# game_impact: 전체 MinMax 0~100
mmr_df_cleaned_default['game_impact'] = normalize_minmax_0_100(
    mmr_df_cleaned_default['raw_game_impact']
)

print(
    mmr_df_cleaned_default[['puuid', 'position', 'raw_game_impact', 'game_impact']].head(20)
)

mmr_df_cleaned_default.info()
