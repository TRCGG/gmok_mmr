import pandas as pd
import numpy as np
import matplotlib.pyplot as plt
import seaborn as sns

# 폰트 설정 (시각화 시 한글 깨짐 방지)
plt.rcParams.update({'font.size': 12, 'font.family': 'Malgun Gothic'})
# macOS/Linux 사용자는 필요 시 아래로 변경
# plt.rcParams['font.family'] = 'AppleGothic'
# plt.rcParams['font.family'] = 'NanumGothic'

# ----------------------------------------------------
# 2. 포지션별 game_impact 균등성 확인
#    (Part 1에서 계산된 'game_impact_winloss_norm' 컬럼 사용)
# ----------------------------------------------------
print("\n✨ Part 2: 포지션별 game_impact 균등성 확인 중...")

# 필요한 데이터만 필터링 (NaN 값 제외)
plot_data_for_uniformity = mmr_df_cleaned_default[
    ['position', 'game_impact_winloss_norm']
].dropna()

if plot_data_for_uniformity.empty:
    print("😢 'game_impact_winloss_norm' 데이터가 없어 포지션별 균등성을 확인할 수 없습니다.")
else:
    # 1. 포지션별 평균/중앙값 등 주요 통계 확인
    print("\n--- Part 2: 포지션별 'game_impact_winloss_norm' 주요 통계 ---")
    position_stats = plot_data_for_uniformity.groupby('position')['game_impact_winloss_norm'].agg(
        ['count', 'mean', 'median', 'std', 'min', 'max']
    ).sort_values(by='mean', ascending=False)
    print(position_stats)

    # 2. Violin Plot으로 포지션별 분포 비교
    print("\n--- Part 2: 포지션별 game_impact_winloss_norm 분포 Violin Plot ---")
    plt.figure(figsize=(10, 7))
    sns.violinplot(
        x='position',
        y='game_impact_winloss_norm',
        data=plot_data_for_uniformity,
        palette='viridis'
    )
    plt.title('포지션별 게임 임팩트 점수 분포 비교 (0-100 정규화)', fontsize=16)
    plt.xlabel('포지션', fontsize=14)
    plt.ylabel('게임 임팩트 점수 (0-100)', fontsize=14)
    plt.grid(axis='y', linestyle='--', alpha=0.7)
    plt.tight_layout()
    plt.show()

    # 3. Box Plot으로 포지션별 분포 비교
    print("\n--- Part 2: 포지션별 game_impact_winloss_norm 분포 Box Plot (참고용) ---")
    plt.figure(figsize=(10, 7))
    sns.boxplot(
        x='position',
        y='game_impact_winloss_norm',
        data=plot_data_for_uniformity,
        palette='magma'
    )
    plt.title('포지션별 게임 임팩트 점수 분포 비교 (Box Plot)', fontsize=16)
    plt.xlabel('포지션', fontsize=14)
    plt.ylabel('게임 임팩트 점수 (0-100)', fontsize=14)
    plt.grid(axis='y', linestyle='--', alpha=0.7)
    plt.tight_layout()
    plt.show()
