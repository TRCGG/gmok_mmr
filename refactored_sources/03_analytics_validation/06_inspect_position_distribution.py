import pandas as pd
import numpy as np
from sklearn.preprocessing import MinMaxScaler, QuantileTransformer
import matplotlib.pyplot as plt
import seaborn as sns

# ------------------------------------
# 3. 각 포지션별로 정규 분포에 가깝게 변환 후 0 ~ 100 점수로 정규화
# ------------------------------------
mmr_df_cleaned_default['game_impact_normal_dist'] = np.nan

unique_positions = mmr_df_cleaned_default['position'].dropna().unique()

# 폰트 설정
plt.rcParams.update({'font.size': 10, 'font.family': 'Malgun Gothic'})
# macOS/Linux 사용자는 필요 시 아래로 변경
# plt.rcParams['font.family'] = 'AppleGothic'
# plt.rcParams['font.family'] = 'NanumGothic'

for pos in unique_positions:
    # 해당 포지션 데이터만 필터링
    pos_data_idx = mmr_df_cleaned_default['position'] == pos
    pos_impact_data = mmr_df_cleaned_default.loc[
        pos_data_idx, 'raw_game_impact'
    ].values.reshape(-1, 1)

    # NaN / Inf 제거
    pos_impact_data = pos_impact_data[
        ~np.isnan(pos_impact_data) & ~np.isinf(pos_impact_data)
    ]

    # 데이터가 너무 적으면 스킵
    if len(pos_impact_data) < 2:
        print(f"경고: '{pos}' 포지션의 데이터가 부족하여 정규 분포 변환을 스킵합니다.")
        continue

    # 1. 정규분포에 가깝게 변환
    n_quantiles_val = min(len(pos_impact_data), 1000)

    qt_scaler = QuantileTransformer(
        output_distribution='normal',
        random_state=42,
        n_quantiles=n_quantiles_val
    )
    transformed_data = qt_scaler.fit_transform(pos_impact_data.reshape(-1, 1))

    # 2. 0~100 점수로 스케일링
    mm_scaler = MinMaxScaler(feature_range=(0, 100))
    final_scaled_data = mm_scaler.fit_transform(transformed_data)

    # 원본 DataFrame에 저장
    mmr_df_cleaned_default.loc[
        pos_data_idx, 'game_impact_normal_dist'
    ] = final_scaled_data.flatten()

# ------------------------------------
# 4. 확인 및 분포 시각화
# ------------------------------------
print("--- 정규 분포에 가깝게 변환된 game_impact 점수 (상위 20개) ---")
print(
    mmr_df_cleaned_default[
        ['puuid', 'position', 'raw_game_impact', 'game_impact_normal_dist']
    ].head(20)
)

print("\n--- 각 포지션별 game_impact_normal_dist 분포 시각화 ---")

if len(unique_positions) == 0:
    print("분석할 포지션 데이터가 없어 분포 그래프를 그릴 수 없습니다.")
else:
    fig, axes = plt.subplots(
        1,
        len(unique_positions),
        figsize=(5 * len(unique_positions), 6),
        sharey=True
    )

    if len(unique_positions) == 1:
        axes = [axes]

    for i, pos in enumerate(unique_positions):
        plot_data = mmr_df_cleaned_default[
            mmr_df_cleaned_default['position'] == pos
        ]['game_impact_normal_dist'].dropna()

        if not plot_data.empty:
            sns.histplot(plot_data, kde=True, ax=axes[i], bins=10, color='skyblue')
            axes[i].set_title(f'{pos} Game Impact Distribution')
            axes[i].set_xlabel('Game Impact (0-100)')
            axes[i].set_ylabel('Frequency')
        else:
            axes[i].set_title(f'{pos} No Data')
            axes[i].set_xlabel('Game Impact (0-100)')
            axes[i].set_ylabel('Frequency')

    plt.tight_layout()
    plt.suptitle("포지션별 게임 임팩트 점수 분포 (정규 분포화)", fontsize=16, y=1.02)
    plt.show()

# ------------------------------------
# 5. 왜도 / 첨도 확인
# ------------------------------------
print("\n--- 각 포지션별 game_impact_normal_dist의 왜도(Skewness)와 첨도(Kurtosis) ---")
for pos in unique_positions:
    data_for_stats = mmr_df_cleaned_default[
        mmr_df_cleaned_default['position'] == pos
    ]['game_impact_normal_dist'].dropna()

    if len(data_for_stats) > 1:
        print(f"[{pos}] Skewness: {data_for_stats.skew():.4f}, Kurtosis: {data_for_stats.kurt():.4f}")
    else:
        print(f"[{pos}] 데이터 부족으로 왜도/첨도 계산 불가.")
