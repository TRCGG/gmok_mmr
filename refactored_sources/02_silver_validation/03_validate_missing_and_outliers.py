"""중복/결측 검사 + 기본 클렌징.

핵심 로직은 `mmr_refactor.silver.clean_match_data` 로 위임.
이 파일은 진단 출력 + win/lose 분리만 담당.
"""

import numpy as np
import pandas as pd

from mmr_refactor.silver import clean_match_data, find_rows_with_na

# 진단: replay_code 분포, 중복 행 수
mmr_df['replay_code'].value_counts()
print(mmr_df.duplicated().sum())

# 결측 검사 (참고용)
rows_with_na = find_rows_with_na(mmr_df.drop_duplicates())
print("--- Rows containing NA (missing values, excluding specific columns) ---")
print(rows_with_na)
print(f"\nNA (missing values) were found in a total of {len(rows_with_na)} rows.")

# 클렌징
mmr_df_cleaned_default = clean_match_data(mmr_df)

# 승/패 분리
mmr_df_win_df = mmr_df_cleaned_default[
    mmr_df_cleaned_default['game_result'] == 1
].reset_index(drop=True)

mmr_df_lose_df = mmr_df_cleaned_default[
    mmr_df_cleaned_default['game_result'] == 0
].reset_index(drop=True)

print("승리한 게임 데이터:")
print(mmr_df_win_df.head())

print("\n패배한 게임 데이터:")
print(mmr_df_lose_df.head())

# 추가 지표 미리보기 (해당 컬럼이 존재할 때만)
preview_cols = [
    'deaths', 'damage_taken', 'damage_taken_per_death',
    'damage_to_champions', 'damage_dealt_per_death',
    'wards_placed', 'wards_killed', 'cc_time',
    'heal_on_teammates', 'shield_on_teammates', 'lane_gold_diff'
]
preview_cols = [c for c in preview_cols if c in mmr_df_cleaned_default.columns]
if preview_cols:
    print("\n추가 지표 포함 데이터프레임 미리보기:")
    print(mmr_df_cleaned_default[preview_cols].head())
