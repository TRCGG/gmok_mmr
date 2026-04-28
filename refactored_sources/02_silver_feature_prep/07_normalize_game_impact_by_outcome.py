"""(position × win/loss) 별 Quantile→MinMax(0~100) 정규화 + 시각화.

핵심 계산은 `mmr_refactor.game_impact.normalize_by_position_outcome` 로 위임.
"""

import numpy as np
import pandas as pd
import matplotlib.pyplot as plt
import seaborn as sns

from mmr_refactor.game_impact import normalize_by_position_outcome

# ----------------------------------------------------
# 1. 정규화 결과 컬럼 생성
# ----------------------------------------------------
print("✨ Part 1: 승/패 별 game_impact 정규 분포화 진행 중...")
mmr_df_cleaned_default['game_impact_winloss_norm'] = normalize_by_position_outcome(
    mmr_df_cleaned_default,
    raw_col='raw_game_impact',
)

print("\n--- Part 1: 승/패 별 game_impact_winloss_norm 결과 (상위 20개) ---")
print(
    mmr_df_cleaned_default[
        ['puuid', 'position', 'game_result', 'raw_game_impact', 'game_impact_winloss_norm']
    ].head(20)
)

unique_positions = mmr_df_cleaned_default['position'].dropna().unique()
game_results = mmr_df_cleaned_default['game_result'].dropna().unique()

# ----------------------------------------------------
# 2. 분포 시각화
# ----------------------------------------------------
print("\n--- Part 1: 각 포지션별 승/패 game_impact_winloss_norm 분포 시각화 ---")

if len(unique_positions) == 0 or len(game_results) == 0:
    print("분석할 포지션 또는 승패 데이터가 없어 그래프를 그릴 수 없습니다.")
else:
    fig, axes = plt.subplots(
        len(unique_positions),
        len(game_results),
        figsize=(6 * len(game_results), 5 * len(unique_positions)),
        sharex=True,
        sharey=True
    )

    if len(unique_positions) == 1 and len(game_results) == 1:
        axes = np.array([[axes]])
    elif len(unique_positions) == 1:
        axes = np.expand_dims(axes, axis=0)
    elif len(game_results) == 1:
        axes = np.expand_dims(axes, axis=1)

    for i, pos in enumerate(unique_positions):
        for j, result in enumerate(game_results):
            ax = axes[i, j]

            plot_data = mmr_df_cleaned_default[
                (mmr_df_cleaned_default['position'] == pos) &
                (mmr_df_cleaned_default['game_result'] == result)
            ]['game_impact_winloss_norm'].dropna()

            title_result = '승리' if result == 1 else '패배'

            if not plot_data.empty:
                sns.histplot(
                    plot_data,
                    kde=True,
                    bins=10,
                    ax=ax,
                    color='lightcoral' if result == 0 else 'skyblue'
                )
                ax.set_title(f'{pos} - {title_result} 분포')
                ax.set_xlabel('Game Impact (0-100)')
                ax.set_ylabel('빈도')
            else:
                ax.set_title(f'{pos} - {title_result} (데이터 없음)')
                ax.set_xlabel('')
                ax.set_ylabel('')

    plt.tight_layout(rect=[0, 0.03, 1, 0.97])
    plt.suptitle("포지션별 승/패 결과에 따른 게임 임팩트 분포 (정규화)", fontsize=18, y=0.99)
    plt.show()

# ----------------------------------------------------
# 3. 왜도 / 첨도 확인
# ----------------------------------------------------
print("\n--- Part 1: 각 포지션별 승/패 game_impact_winloss_norm의 왜도(Skewness)와 첨도(Kurtosis) ---")
for pos in unique_positions:
    for result in game_results:
        data_for_stats = mmr_df_cleaned_default[
            (mmr_df_cleaned_default['position'] == pos) &
            (mmr_df_cleaned_default['game_result'] == result)
        ]['game_impact_winloss_norm'].dropna()

        title_result = '승리' if result == 1 else '패배'

        if len(data_for_stats) > 1:
            print(f"[{pos} - {title_result}] Skewness: {data_for_stats.skew():.4f}, Kurtosis: {data_for_stats.kurt():.4f}")
        else:
            print(f"[{pos} - {title_result}] 데이터 부족으로 왜도/첨도 계산 불가.")
