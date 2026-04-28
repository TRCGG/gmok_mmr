import pandas as pd
import numpy as np
from sklearn.preprocessing import MinMaxScaler, QuantileTransformer
import matplotlib.pyplot as plt
import seaborn as sns

# 폰트 설정 (시각화 시 한글 깨짐 방지)
plt.rcParams.update({'font.size': 12, 'font.family': 'Malgun Gothic'})
# For macOS/Linux users, uncomment one of these:
# plt.rcParams['font.family'] = 'AppleGothic'
# plt.rcParams['font.family'] = 'NanumGothic'

# ----------------------------------------------------
# 1. '몇 인분' 컬럼 추가 (게임 전체 기여도 - 총 합이 10인분)
# ----------------------------------------------------
print("\n✨ 1. '몇 인분' 컬럼 (게임 전체 기여도, 총 합 10인분) 계산 중...")

# 각 replay_code별 game_impact_winloss_norm 합계 계산
game_wide_impact_sum = mmr_df_cleaned_default.groupby('replay_code')['game_impact_winloss_norm'].transform('sum')

# 한 게임당 총 플레이어 수
players_per_game = 10

mmr_df_cleaned_default['game_n_person_contribution'] = (
    mmr_df_cleaned_default['game_impact_winloss_norm'] / game_wide_impact_sum * players_per_game
).fillna(0)

print("\n--- '몇 인분' 컬럼 샘플 (game_n_person_contribution) ---")
print(
    mmr_df_cleaned_default[
        ['replay_code', 'puuid', 'position', 'game_impact_winloss_norm', 'game_n_person_contribution']
    ]
    .head(20)
    .sort_values(by='replay_code')
)

# 검증용
# print("\n--- 검증: 게임별 '몇 인분'의 총합 ---")
# print(mmr_df_cleaned_default.groupby('replay_code')['game_n_person_contribution'].sum().head())

# ----------------------------------------------------
# 2. 상대와 비교 점수 컬럼 추가 (game_impact_vs_opponent)
# ----------------------------------------------------
print("\n✨ 2. 상대와 비교 점수 컬럼 계산 중...")

df_comp = mmr_df_cleaned_default[
    ['replay_code', 'position', 'game_result', 'game_impact_winloss_norm', 'puuid']
].copy()

merged_df = pd.merge(
    df_comp[df_comp['game_result'] == 1],  # 승리 팀 플레이어
    df_comp[df_comp['game_result'] == 0],  # 패배 팀 플레이어
    on=['replay_code', 'position'],
    suffixes=('_winner', '_loser'),
    how='inner'
)

merged_df['total_impact'] = (
    merged_df['game_impact_winloss_norm_winner'] +
    merged_df['game_impact_winloss_norm_loser']
)

merged_df['game_impact_vs_opponent_winner'] = (
    merged_df['game_impact_winloss_norm_winner'] / merged_df['total_impact'] * 100
).fillna(0)

merged_df['game_impact_vs_opponent_loser'] = (
    merged_df['game_impact_winloss_norm_loser'] / merged_df['total_impact'] * 100
).fillna(0)

result_list = []

for _, row in merged_df.iterrows():
    result_list.append({
        'replay_code': row['replay_code'],
        'position': row['position'],
        'puuid': row['puuid_winner'],
        'game_impact_vs_opponent': row['game_impact_vs_opponent_winner']
    })
    result_list.append({
        'replay_code': row['replay_code'],
        'position': row['position'],
        'puuid': row['puuid_loser'],
        'game_impact_vs_opponent': row['game_impact_vs_opponent_loser']
    })

game_impact_vs_opponent_df = pd.DataFrame(result_list)

mmr_df_cleaned_default = pd.merge(
    mmr_df_cleaned_default,
    game_impact_vs_opponent_df,
    on=['replay_code', 'puuid', 'position'],
    how='left'
)

mmr_df_cleaned_default['game_impact_vs_opponent'] = (
    mmr_df_cleaned_default['game_impact_vs_opponent'].fillna(np.nan)
)

print("\n--- 상대와 비교 점수 컬럼 샘플 (game_impact_vs_opponent) ---")
print(
    mmr_df_cleaned_default[
        ['replay_code', 'puuid', 'position', 'game_result',
         'game_impact_winloss_norm', 'game_impact_vs_opponent']
    ].head(10)
)

# ----------------------------------------------------
# 3. 시각화 및 최종 확인
# ----------------------------------------------------
print("\n--- 최종 확인 ---")
print(
    mmr_df_cleaned_default[
        ['replay_code', 'puuid', 'position', 'game_result',
         'game_impact_winloss_norm', 'game_n_person_contribution', 'game_impact_vs_opponent']
    ].head(20)
)

# '몇 인분' 컬럼 분포 시각화 (포지션별)
plt.figure(figsize=(10, 6))
sns.violinplot(
    x='position',
    y='game_n_person_contribution',
    data=mmr_df_cleaned_default,
    palette='magma'
)
plt.title('포지션별 게임 내 총 인분 기여도 (총 합 10인분)', fontsize=16)
plt.xlabel('포지션', fontsize=14)
plt.ylabel('인분 기여도', fontsize=14)
plt.grid(axis='y', linestyle='--', alpha=0.7)
plt.tight_layout()
plt.show()

# '상대 비교 점수' 컬럼 분포 시각화 (전체)
plt.figure(figsize=(10, 6))
sns.histplot(
    mmr_df_cleaned_default['game_impact_vs_opponent'].dropna(),
    kde=True,
    bins=20,
    color='teal'
)
plt.title('상대 비교 점수 분포 (전체)', fontsize=16)
plt.xlabel('상대 비교 점수 (0-100)', fontsize=14)
plt.ylabel('빈도', fontsize=14)
plt.grid(axis='y', linestyle='--', alpha=0.7)
plt.tight_layout()
plt.show()

# 포지션별 상대 비교 점수 분포 (boxplot)
plt.figure(figsize=(10, 6))
sns.boxplot(
    x='position',
    y='game_impact_vs_opponent',
    data=mmr_df_cleaned_default,
    palette='cubehelix'
)
plt.title('포지션별 상대 비교 점수 분포', fontsize=16)
plt.xlabel('포지션', fontsize=14)
plt.ylabel('상대 비교 점수 (0-100)', fontsize=14)
plt.ylim(0, 100)
plt.grid(axis='y', linestyle='--', alpha=0.7)
plt.tight_layout()
plt.show()


mmr_df_cleaned_default[[
    'replay_code',
    'puuid',
    'position',
    'game_result',
    'game_impact_winloss_norm',
    'game_n_person_contribution',
    'game_impact_vs_opponent'
]].head(20)
