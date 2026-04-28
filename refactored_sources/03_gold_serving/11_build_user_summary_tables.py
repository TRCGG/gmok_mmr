import pandas as pd
import numpy as np

# ==================================================
# 1. 유저 이름 파일 로드
# ==================================================
user_name_path = r"C:/Users/PC/Desktop/김필준/data/2026 유저_0415.csv"

try:
    user_name = pd.read_csv(user_name_path, encoding='utf-8', on_bad_lines='skip')
    print("UTF-8 인코딩으로 데이터 로드에 성공했습니다.")
except UnicodeDecodeError:
    user_name = pd.read_csv(user_name_path, encoding='cp949', on_bad_lines='skip')
    print("CP949 인코딩으로 데이터 로드에 성공했습니다.")

user_name = user_name[['puuid', 'riot_name']].drop_duplicates()

# ==================================================
# 2. summary_df_elo에 riot_name 붙이기
# ==================================================
cols_to_drop = ['riot_name', 'riot_name_x', 'riot_name_y']
summary_df_elo = summary_df_elo.drop(
    columns=[c for c in cols_to_drop if c in summary_df_elo.columns]
)

summary_df_elo = summary_df_elo.merge(
    user_name,
    on='puuid',
    how='left'
)

cols = ['riot_name'] + [c for c in summary_df_elo.columns if c != 'riot_name']
summary_df_elo = summary_df_elo[cols]

# ==================================================
# 3. total_mmr 보정
# ==================================================
position_mmr_cols = ['TOP_mmr', 'JUNGLE_mmr', 'MIDDLE_mmr', 'BOTTOM_mmr', 'UTILITY_mmr']
existing_position_mmr_cols = [c for c in position_mmr_cols if c in summary_df_elo.columns]

if 'total_mmr' not in summary_df_elo.columns:
    if len(existing_position_mmr_cols) > 0:
        summary_df_elo['total_mmr'] = summary_df_elo[existing_position_mmr_cols].mean(axis=1)
        print("total_mmr 컬럼이 없어 포지션별 mmr 평균으로 생성했습니다.")
    else:
        summary_df_elo['total_mmr'] = np.nan
        print("포지션별 mmr 컬럼이 없어 total_mmr를 NaN으로 생성했습니다.")

# ==================================================
# 4. 경기 데이터 복사
#    (이미 per-minute 처리 끝난 상태라고 가정)
# ==================================================
df = mmr_df_updated_elo.copy()

# ==================================================
# 5. 사용할 지표 컬럼 정의
#    game impact 3개를 우선 배치할 수 있게 분리
# ==================================================
priority_metric_cols = [
    'game_impact_winloss_norm',
    'game_n_person_contribution',
    'game_impact_vs_opponent'
]

other_metric_candidates =  [
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

priority_metric_cols = [col for col in priority_metric_cols if col in df.columns]
other_metric_cols = [col for col in other_metric_candidates if col in df.columns]

existing_metric_cols = priority_metric_cols + other_metric_cols

print("사용 지표 컬럼:")
print(existing_metric_cols)

# ==================================================
# 6. 유저 + 포지션 기준 평균 지표 계산
# ==================================================
player_pos_metrics = (
    df.groupby(['puuid', 'position'], as_index=False)[existing_metric_cols]
      .mean()
)

# ==================================================
# 7. 유저 전체 기준 평균 지표 계산 (TOTAL용)
# ==================================================
player_total_metrics = (
    df.groupby('puuid', as_index=False)[existing_metric_cols]
      .mean()
)

# ==================================================
# 8. summary_df_elo를 long 형태로 변환
# ==================================================
positions = ['TOP', 'JUNGLE', 'MIDDLE', 'BOTTOM', 'UTILITY']
summary_long_list = []

for pos in positions:
    mmr_col = f'{pos}_mmr'
    win_col = f'{pos}_winrate'
    game_col = f'{pos}_games'

    required_cols = ['riot_name', 'puuid', mmr_col, win_col, game_col]

    if all(col in summary_df_elo.columns for col in required_cols):
        temp = summary_df_elo[required_cols].copy()
        temp.columns = ['riot_name', 'puuid', 'MMR', 'win_rate', 'games']
        temp['position'] = pos
        summary_long_list.append(temp)
    else:
        print(f"{pos} 관련 컬럼이 summary_df_elo에 없어 제외됩니다.")

summary_long = pd.concat(summary_long_list, ignore_index=True)
summary_long = summary_long[summary_long['games'] > 0].copy()

# ==================================================
# 9. 포지션별 merge
# ==================================================
player_pos_final = summary_long.merge(
    player_pos_metrics,
    on=['puuid', 'position'],
    how='left'
)

# ==================================================
# 10. TOTAL용 summary 생성
# ==================================================
game_cols = [f'{pos}_games' for pos in positions if f'{pos}_games' in summary_df_elo.columns]

summary_total = summary_df_elo[['riot_name', 'puuid', 'total_mmr']].copy()

# 전체 판수
summary_total['games'] = summary_df_elo[game_cols].sum(axis=1)

# 전체 승률 계산 (판수 가중 평균)
weighted_wins = 0
for pos in positions:
    win_col = f'{pos}_winrate'
    game_col = f'{pos}_games'
    if win_col in summary_df_elo.columns and game_col in summary_df_elo.columns:
        weighted_wins += (summary_df_elo[win_col] / 100.0) * summary_df_elo[game_col]

summary_total['win_rate'] = np.where(
    summary_total['games'] > 0,
    (weighted_wins / summary_total['games']) * 100,
    np.nan
)

summary_total['MMR'] = summary_total['total_mmr']
summary_total = summary_total[summary_total['games'] > 0].copy()

# ==================================================
# 11. TOTAL용 merge
# ==================================================
player_total_final = summary_total.merge(
    player_total_metrics,
    on='puuid',
    how='left'
)

# ==================================================
# 12. 포지션별 DataFrame 생성
#     - total_mmr 제외
#     - MMR 내림차순
#     - 평균 행 맨 위 추가
# ==================================================
position_dfs = {}

for pos in positions:
    df_pos = player_pos_final[player_pos_final['position'] == pos].copy()
    df_pos = df_pos.drop(columns=['position'])

    # 유저 데이터 MMR 내림차순
    df_pos = df_pos.sort_values(by='MMR', ascending=False).reset_index(drop=True)

    # 평균 행 생성
    avg_row = df_pos.mean(numeric_only=True)
    avg_row['riot_name'] = f'{pos}_AVERAGE'
    avg_row['puuid'] = ''

    avg_df = pd.DataFrame([avg_row])

    # 평균 행 맨 위 추가
    df_pos = pd.concat([avg_df, df_pos], ignore_index=True)

    # total_mmr는 포지션 시트에서 제거
    if 'total_mmr' in df_pos.columns:
        df_pos = df_pos.drop(columns=['total_mmr'])

    # 컬럼 순서 정리
    front_cols = ['riot_name', 'puuid', 'MMR', 'win_rate', 'games']
    ordered_metric_cols = priority_metric_cols + [c for c in other_metric_cols if c in df_pos.columns]
    remaining_cols = [col for col in df_pos.columns if col not in front_cols + ordered_metric_cols]

    df_pos = df_pos[front_cols + ordered_metric_cols + remaining_cols]

    # 숫자형 반올림
    numeric_cols = df_pos.select_dtypes(include='number').columns
    df_pos[numeric_cols] = df_pos[numeric_cols].round(3)

    position_dfs[pos] = df_pos

# ==================================================
# 13. TOTAL DataFrame 생성
#     - total_mmr 포함
#     - total_mmr 내림차순
#     - 평균 행 맨 위 추가
# ==================================================
total_df = player_total_final.copy()

# total_mmr 기준 내림차순
total_df = total_df.sort_values(by='total_mmr', ascending=False).reset_index(drop=True)

# 평균 행 생성
total_avg_row = total_df.mean(numeric_only=True)
total_avg_row['riot_name'] = 'TOTAL_AVERAGE'
total_avg_row['puuid'] = ''

total_avg_df = pd.DataFrame([total_avg_row])

# 평균 행 맨 위 추가
total_df = pd.concat([total_avg_df, total_df], ignore_index=True)

# TOTAL 컬럼 순서 정리
front_cols_total = ['riot_name', 'puuid', 'total_mmr', 'MMR', 'win_rate', 'games']
ordered_metric_cols_total = priority_metric_cols + [c for c in other_metric_cols if c in total_df.columns]
remaining_cols_total = [col for col in total_df.columns if col not in front_cols_total + ordered_metric_cols_total]

total_df = total_df[front_cols_total + ordered_metric_cols_total + remaining_cols_total]

# 숫자형 반올림
numeric_cols = total_df.select_dtypes(include='number').columns
total_df[numeric_cols] = total_df[numeric_cols].round(3)

position_dfs['TOTAL'] = total_df

# ==================================================
# 14. 확인
# ==================================================
print("TOTAL 데이터 예시")
print(position_dfs['TOTAL'].head())

print("\nTOP 데이터 예시")
print(position_dfs['TOP'].head())

# ==================================================
# 15. 엑셀 저장
# ==================================================
sheet_order = ['TOTAL', 'TOP', 'JUNGLE', 'MIDDLE', 'BOTTOM', 'UTILITY']

with pd.ExcelWriter('position_user_summary_final.xlsx') as writer:
    for sheet_name in sheet_order:
        if sheet_name in position_dfs:
            position_dfs[sheet_name].to_excel(writer, sheet_name=sheet_name, index=False)

print("\n엑셀 저장 완료: position_user_summary_final.xlsx")
