"""ELO 포함 MMR 갱신 + 시각화.

핵심 계산은 `mmr_refactor.mmr.update_mmr_elo` 로 위임.
이 파일은 실행 진입점 + 분포 시각화만 담당.
"""

import numpy as np
import pandas as pd
import matplotlib.pyplot as plt
import seaborn as sns

from mmr_refactor.mmr import update_mmr_elo


# ==============================================================
# 실행
# ==============================================================
mmr_df_updated_elo, summary_df_elo = update_mmr_elo(mmr_df_cleaned_default.copy())

print("=== ELO 포함 summary_df ===")
print(summary_df_elo.head())


# ==============================================================
# 시각화
# ==============================================================
plt.figure(figsize=(10, 6))
sns.boxplot(data=mmr_df_updated_elo, x='position', y='mmr_change', hue='game_result')
plt.axhline(0, color='black', linestyle='--', linewidth=1)
plt.axhline(12, color='red', linestyle=':', alpha=0.6)
plt.axhline(-12, color='red', linestyle=':', alpha=0.6)
plt.title("MMR Change Distribution (ELO Version)")
plt.tight_layout()
plt.show()

plt.figure(figsize=(10, 6))
sns.histplot(summary_df_elo['total_mmr'], kde=True, bins=30, color='skyblue')
plt.title("Total MMR Distribution (ELO Version)")
plt.xlabel("MMR Score")
plt.ylabel("Player Count")
plt.tight_layout()
plt.show()
