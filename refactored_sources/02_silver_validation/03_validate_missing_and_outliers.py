mmr_df['replay_code'].value_counts()

print(mmr_df.duplicated().sum())

mmr_df_cleaned_default = mmr_df.drop_duplicates()

mmr_df_cleaned_default['replay_code'].value_counts()


# 제외할 컬럼 정의
exclude_cols = [
    'jungle_cs_own', 'jungle_cs_enemy', 'dragon_kills', 'baron_kills',
    'herald_kills', 'horde_kills', 'damage_to_epic_monsters',
    'objectives_stolen', 'barracks_killed'
]

# 제외 컬럼 제거한 데이터프레임 생성
check_df = mmr_df_cleaned_default.drop(columns=exclude_cols)

# NA가 하나라도 있는 행 추출
rows_with_na = mmr_df_cleaned_default[check_df.isnull().any(axis=1)]

# 출력
print("--- Rows containing NA (missing values, excluding specific columns) ---")
print(rows_with_na)

# 개수 확인
print(f"\nNA (missing values) were found in a total of {len(rows_with_na)} rows.")


# 중복 제거 후 .copy()
mmr_df_cleaned_default = mmr_df.drop_duplicates().copy()

# win -> game_result 변환
mmr_df_cleaned_default['game_result'] = (
    mmr_df_cleaned_default['win']
    .astype(str)
    .str.upper()
    .map({'TRUE': 1, 'FALSE': 0})
)

mmr_df_cleaned_default.drop(columns=['win'], inplace=True)


# 서포트 전용 지표 NULL -> 0 처리
mmr_df_cleaned_default['heal_on_teammates'] = mmr_df_cleaned_default['heal_on_teammates'].fillna(0)
mmr_df_cleaned_default['shield_on_teammates'] = mmr_df_cleaned_default['shield_on_teammates'].fillna(0)

# game_duration 분 단위 변환
mmr_df_cleaned_default['game_duration'] = (
    mmr_df_cleaned_default['game_duration'] / 60
).round(2)

# 0으로 나누기 방지용 duration
duration_for_calc = mmr_df_cleaned_default['game_duration'].replace(0, np.nan)

# 승패 분리
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

print("\n추가 지표 포함 데이터프레임 미리보기:")
print(
    mmr_df_cleaned_default[
        [
            'deaths', 'damage_taken', 'damage_taken_per_death',
            'damage_to_champions', 'damage_dealt_per_death',
            'wards_placed', 'wards_killed', 'cc_time',
            'heal_on_teammates', 'shield_on_teammates', 'lane_gold_diff'
        ]
    ].head()
)
