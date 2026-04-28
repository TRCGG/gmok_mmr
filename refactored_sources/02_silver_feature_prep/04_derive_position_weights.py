"""포지션별 feature_importance(가중치) 도출.

핵심 계산은 `mmr_refactor.game_impact.derive_position_weights` 로 위임.
이 파일은 입력 컬럼 정의 + 시각화만 담당.
"""

import numpy as np
import pandas as pd
import seaborn as sns
import matplotlib.pyplot as plt

from mmr_refactor.game_impact import derive_position_weights

# --- 사용할 지표 선택 ---
metrics = [
    'kills',
    'deaths',
    'assists',
    'gold_per_min',
    'exp_per_min',
    'dpm',
    'damage_to_turrets_per_min',
    'vision_score',
    'damage_taken_per_min',
    'cs_per_min',
    'kda',
    'damage_taken_per_death',
    'damage_dealt_per_death',
    'wards_placed_per_min',
    'wards_killed_per_min',
    'cc_time_per_min',
    'heal_on_teammates',
    'shield_on_teammates',
    'lane_gold_diff'
]

# --- 포지션별 가중치 산출 (모듈 호출) ---
position_importances_df = derive_position_weights(
    mmr_df_cleaned_default,
    metrics=metrics,
    target='game_result',
)

# --- 시각화 ---
position_importances = {
    pos: position_importances_df[pos].to_dict()
    for pos in position_importances_df.columns
}

if not position_importances:
    print("분석 가능한 포지션 데이터가 없어 그래프를 그릴 수 없습니다. 원본 데이터를 확인하세요.")
else:
    sns.set_style("whitegrid")
    plt.rcParams.update({
        'font.size': 12,
        'font.family': 'Malgun Gothic'
    })

    num_positions = len(position_importances)
    fig, axes = plt.subplots(1, num_positions, figsize=(5 * num_positions, 9), sharey=True)

    if num_positions == 1:
        axes = [axes]

    for i, (pos, imp_dict) in enumerate(position_importances.items()):
        imp_series = pd.Series(imp_dict).sort_values(ascending=False)

        sns.barplot(
            x=imp_series.values,
            y=imp_series.index,
            ax=axes[i],
            palette="rocket"
        )

        axes[i].set_title(f"[{pos}] 승패 기여 중요 지표", fontsize=16, pad=15)
        axes[i].set_xlabel("중요도", fontsize=14)
        axes[i].set_ylabel("")

        if i == 0:
            axes[i].set_ylabel("지표", fontsize=14)

        sns.despine(ax=axes[i], top=True, right=True)

    plt.suptitle("포지션별 승패 중요 지표 분석 (변경 변수명 반영)", fontsize=20, y=1.02)
    plt.tight_layout(rect=[0, 0.03, 1, 0.98])
    plt.show()

print(position_importances_df)
