"""인분(game_n_person_contribution) + 상대비교(game_impact_vs_opponent) + 시각화.

핵심 계산은 `mmr_refactor.game_impact` 로 위임.
"""

import numpy as np
import pandas as pd
import matplotlib.pyplot as plt
import seaborn as sns

from mmr_refactor.game_impact import (
    compute_n_person_contribution,
    compute_vs_opponent,
)

# 폰트 설정 (시각화 시 한글 깨짐 방지)
plt.rcParams.update({'font.size': 12, 'font.family': 'Malgun Gothic'})

# ----------------------------------------------------
# 1. '몇 인분' 컬럼 (게임 전체 기여도, 총 합 10인분)
# ----------------------------------------------------
print("\n✨ 1. '몇 인분' 컬럼 (게임 전체 기여도, 총 합 10인분) 계산 중...")

mmr_df_cleaned_default['game_n_person_contribution'] = compute_n_person_contribution(
    mmr_df_cleaned_default,
    norm_col='game_impact_winloss_norm',
    game_id_col='replay_code',
)

print("\n--- '몇 인분' 컬럼 샘플 (game_n_person_contribution) ---")
print(
    mmr_df_cleaned_default[
        ['replay_code', 'puuid', 'position', 'game_impact_winloss_norm', 'game_n_person_contribution']
    ]
    .head(20)
    .sort_values(by='replay_code')
)

# ----------------------------------------------------
# 2. 상대 비교 점수 (game_impact_vs_opponent)
# ----------------------------------------------------
print("\n✨ 2. 상대와 비교 점수 컬럼 계산 중...")

mmr_df_cleaned_default['game_impact_vs_opponent'] = compute_vs_opponent(
    mmr_df_cleaned_default,
    norm_col='game_impact_winloss_norm',
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

# '몇 인분' 분포 (포지션별)
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

# '상대 비교 점수' 분포 (전체)
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
