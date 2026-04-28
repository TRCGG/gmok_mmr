import pandas as pd
import numpy as np
from sklearn.preprocessing import MinMaxScaler, QuantileTransformer
import matplotlib.pyplot as plt
import seaborn as sns

# ----------------------------------------------------
# 1. 승리 / 패배로 나누어 game_impact 정규 분포화
#    'game_impact_winloss_norm'라는 새로운 컬럼에 저장
# ----------------------------------------------------
print("✨ Part 1: 승/패 별 game_impact 정규 분포화 진행 중...")
mmr_df_cleaned_default['game_impact_winloss_norm'] = np.nan

unique_positions = mmr_df_cleaned_default['position'].dropna().unique()
game_results = mmr_df_cleaned_default['game_result'].dropna().unique()  # 승(1), 패(0)

# 각 포지션별, 승/패 결과별로 반복
for pos in unique_positions:
    for result in game_results:
        # 해당 포지션 & 승/패 데이터만 필터링
        condition = (
            (mmr_df_cleaned_default['position'] == pos) &
            (mmr_df_cleaned_default['game_result'] == result)
        )

        pos_result_data_idx = mmr_df_cleaned_default.loc[condition].index

        # 필터링된 데이터가 없으면 건너뛰기
        if pos_result_data_idx.empty:
            continue

        pos_impact_data = mmr_df_cleaned_default.loc[
            pos_result_data_idx, 'raw_game_impact'
        ].values

        # NaN / Inf 제거
        pos_impact_data = pos_impact_data[
            ~np.isnan(pos_impact_data) & ~np.isinf(pos_impact_data)
        ]

        # 데이터가 너무 적으면 스킵
        if len(pos_impact_data) < 2:
            print(f"✨ 경고: '{pos}' 포지션, {'승리' if result == 1 else '패배'} 데이터가 부족하여 정규 분포 변환을 스킵합니다.")
            continue

        # 1. QuantileTransformer로 정규 분포에 가깝게 변환
        n_quantiles_val = min(len(pos_impact_data), 1000)
        qt_scaler = QuantileTransformer(
            output_distribution='normal',
            random_state=42,
            n_quantiles=n_quantiles_val
        )
        transformed_data = qt_scaler.fit_transform(pos_impact_data.reshape(-1, 1))

        # 2. MinMaxScaler로 0~100 점수화
        mm_scaler = MinMaxScaler(feature_range=(0, 100))
        final_scaled_data = mm_scaler.fit_transform(transformed_data)

        # 결과 저장
        mmr_df_cleaned_default.loc[
            pos_result_data_idx, 'game_impact_winloss_norm'
        ] = final_scaled_data.flatten()

print("\n--- Part 1: 승/패 별 game_impact_winloss_norm 결과 (상위 20개) ---")
print(
    mmr_df_cleaned_default[
        ['puuid', 'position', 'game_result', 'raw_game_impact', 'game_impact_winloss_norm']
    ].head(20)
)

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
