# ==============================================================
# [1] IMPORT
# ==============================================================
import pandas as pd
import numpy as np
import matplotlib.pyplot as plt
import seaborn as sns


# ==============================================================
# [2] PARAMETER
# ==============================================================
BASE_WIN = 20
BASE_LOSS = -15

ALPHA = 0.6   # 개인 기여도 반영
BETA = 0.4    # 상대 포지션 비교 지표 반영
GAMMA = 0.2   # ELO 기대성과 대비 실제성과 반영

INITIAL_MMR = 1300
MMR_MIN_CHANGE = -25
MMR_MAX_CHANGE = 30

MMR_K_DECAY_START = 1500
MMR_K_DECAY_RATE = 0.002
MMR_K_MIN = 0.35


# ==============================================================
# [3] FUNCTION
# ==============================================================

def expected_performance(mmr_a, mmr_b):
    """
    ELO 기대성과 계산
    """
    return 1 / (1 + 10 ** ((mmr_b - mmr_a) / 400))


def calculate_personal_factor(row, f1_mean, f2_mean):
    """
    개인 기여도 factor
    - game_n_person_contribution
    - game_impact_vs_opponent
    """
    f1 = row['game_n_person_contribution'] / f1_mean if f1_mean != 0 else 1

    if pd.isna(row['game_impact_vs_opponent']) or f2_mean == 0:
        f2 = 1
    else:
        f2 = row['game_impact_vs_opponent'] / f2_mean

    f1 = np.clip(f1, 0.5, 2)
    f2 = np.clip(f2, 0.5, 2)

    return (f1 ** ALPHA) * (f2 ** BETA)


def calculate_k_factor(mmr):
    """
    MMR이 높아질수록 점수 변동폭 축소
    """
    k = 1.0
    if mmr > MMR_K_DECAY_START:
        k = 1.0 - ((mmr - MMR_K_DECAY_START) * MMR_K_DECAY_RATE)
    return max(k, MMR_K_MIN)


def make_summary_df_wide(mmr_df_updated):
    """
    summary_df를 wide 형식으로 생성
    예:
    puuid / total_mmr / total_games / overall_winrate /
    TOP_mmr / TOP_winrate / TOP_games / ...
    """
    positions = ['TOP', 'BOTTOM', 'MIDDLE', 'JUNGLE', 'UTILITY']

    # 1. 플레이어-포지션별 마지막 MMR
    pos_last = (
        mmr_df_updated
        .sort_values(by=['played_at', 'replay_code'])
        .groupby(['puuid', 'position'], as_index=False)
        .tail(1)
        [['puuid', 'position', 'pos_cumulative_mmr']]
        .rename(columns={'pos_cumulative_mmr': 'pos_mmr'})
    )

    # 2. 플레이어-포지션별 게임수 / 승수
    pos_stats = (
        mmr_df_updated
        .groupby(['puuid', 'position'], as_index=False)
        .agg(
            pos_games=('game_result', 'count'),
            pos_wins=('game_result', 'sum')
        )
    )
    pos_stats['pos_winrate'] = (pos_stats['pos_wins'] / pos_stats['pos_games'] * 100).round(2)

    # 3. merge
    pos_summary = pos_last.merge(pos_stats, on=['puuid', 'position'], how='outer')

    # 4. pivot
    mmr_wide = pos_summary.pivot(index='puuid', columns='position', values='pos_mmr')
    winrate_wide = pos_summary.pivot(index='puuid', columns='position', values='pos_winrate')
    games_wide = pos_summary.pivot(index='puuid', columns='position', values='pos_games')

    mmr_wide.columns = [f'{col}_mmr' for col in mmr_wide.columns]
    winrate_wide.columns = [f'{col}_winrate' for col in winrate_wide.columns]
    games_wide.columns = [f'{col}_games' for col in games_wide.columns]

    # 5. 전체 게임 수 / 전체 승률
    overall_summary = (
        mmr_df_updated
        .groupby('puuid', as_index=False)
        .agg(
            total_games=('game_result', 'count'),
            total_wins=('game_result', 'sum')
        )
    )
    overall_summary['overall_winrate'] = (
        overall_summary['total_wins'] / overall_summary['total_games'] * 100
    ).round(2)

    # 6. total_mmr = 마지막 경기 기준 total_mmr
    total_mmr_df = (
        mmr_df_updated
        .sort_values(by=['played_at', 'replay_code'])
        .groupby('puuid', as_index=False)
        .tail(1)
        [['puuid', 'total_mmr']]
    )

    overall_summary = overall_summary.merge(total_mmr_df, on='puuid', how='left')
    overall_summary = overall_summary.drop(columns='total_wins')

    # 7. 전체 merge
    summary_df = (
        overall_summary
        .merge(mmr_wide, on='puuid', how='left')
        .merge(winrate_wide, on='puuid', how='left')
        .merge(games_wide, on='puuid', how='left')
    )

    # 8. 포지션 컬럼 보정
    for pos in positions:
        if f'{pos}_mmr' not in summary_df.columns:
            summary_df[f'{pos}_mmr'] = np.nan
        if f'{pos}_winrate' not in summary_df.columns:
            summary_df[f'{pos}_winrate'] = np.nan
        if f'{pos}_games' not in summary_df.columns:
            summary_df[f'{pos}_games'] = 0

    # 9. 컬럼 순서
    ordered_cols = [
        'puuid', 'total_mmr', 'total_games', 'overall_winrate',
        'TOP_mmr', 'TOP_winrate', 'TOP_games',
        'BOTTOM_mmr', 'BOTTOM_winrate', 'BOTTOM_games',
        'MIDDLE_mmr', 'MIDDLE_winrate', 'MIDDLE_games',
        'JUNGLE_mmr', 'JUNGLE_winrate', 'JUNGLE_games',
        'UTILITY_mmr', 'UTILITY_winrate', 'UTILITY_games'
    ]

    summary_df = summary_df[ordered_cols].sort_values(by='total_mmr', ascending=False).reset_index(drop=True)

    return summary_df


# ==============================================================
# [4] ELO 포함 MMR 업데이트
# ==============================================================

def update_mmr_elo(df):
    df = df.sort_values(by=['played_at', 'replay_code', 'puuid']).copy()

    player_pos_mmr = {}
    player_pos_record = {}
    updated_rows = []

    f1_mean = df['game_n_person_contribution'].mean()
    f2_mean = df['game_impact_vs_opponent'].mean()

    for replay_code, game_df in df.groupby('replay_code', sort=False):
        pre_mmr = {}
        game_updates = []

        # 경기 시작 전 MMR snapshot
        for _, row in game_df.iterrows():
            pid = row['puuid']
            pos = row['position']

            player_pos_mmr.setdefault(pid, {})
            player_pos_record.setdefault(pid, {})

            player_pos_mmr[pid].setdefault(pos, INITIAL_MMR)
            player_pos_record[pid].setdefault(pos, {'win': 0, 'total': 0})

            pre_mmr[(pid, pos)] = int(player_pos_mmr[pid][pos])

        # 각 플레이어 변화량 계산
        for _, row in game_df.iterrows():
            pid = row['puuid']
            pos = row['position']
            current_mmr = pre_mmr[(pid, pos)]

            # 같은 포지션 상대 찾기
            opponent_df = game_df[
                (game_df['position'] == pos) &
                (game_df['puuid'] != pid)
            ]

            opponent_mmr = INITIAL_MMR
            if not opponent_df.empty:
                opp_id = opponent_df.iloc[0]['puuid']
                opponent_mmr = pre_mmr.get((opp_id, pos), INITIAL_MMR)

            expected = expected_performance(current_mmr, opponent_mmr)

            actual = (
                row['game_impact_vs_opponent'] / 100
                if not pd.isna(row['game_impact_vs_opponent'])
                else expected
            )

            relative_factor = actual / expected if expected > 0 else 1
            personal_factor = calculate_personal_factor(row, f1_mean, f2_mean)
            final_factor = personal_factor * (relative_factor ** GAMMA)

            k = calculate_k_factor(current_mmr)

            if row['game_result'] == 1:
                delta = BASE_WIN * final_factor
                delta = delta * k
                delta = np.clip(max(delta, 12), 12, MMR_MAX_CHANGE)
            else:
                delta = BASE_LOSS * final_factor
                delta = delta * k
                delta = np.clip(min(delta, -12), MMR_MIN_CHANGE, -12)

            delta = int(round(delta))
            new_mmr = int(current_mmr + delta)

            row_copy = row.copy()
            row_copy['pre_game_pos_mmr'] = int(current_mmr)
            row_copy['expected_score'] = round(expected, 4)
            row_copy['actual_score'] = round(actual, 4)
            row_copy['relative_factor'] = round(relative_factor, 4)
            row_copy['personal_factor'] = round(personal_factor, 4)
            row_copy['final_factor'] = round(final_factor, 4)
            row_copy['mmr_change'] = int(delta)
            row_copy['pos_cumulative_mmr'] = int(new_mmr)

            game_updates.append((pid, pos, row['game_result'], new_mmr, row_copy))

        # 경기 결과 반영
        for pid, pos, result, new_mmr, row_copy in game_updates:
            player_pos_mmr[pid][pos] = new_mmr
            player_pos_record[pid][pos]['total'] += 1

            if result == 1:
                player_pos_record[pid][pos]['win'] += 1

            # total_mmr = 포지션별 경기수 가중 평균
            pos_mmr = player_pos_mmr[pid]
            pos_record = player_pos_record[pid]

            weighted_sum = 0
            total_games = 0

            for p in pos_mmr:
                g = pos_record[p]['total']
                weighted_sum += pos_mmr[p] * g
                total_games += g

            total_mmr = int(round(weighted_sum / total_games)) if total_games > 0 else INITIAL_MMR

            row_copy['total_mmr'] = total_mmr
            updated_rows.append(row_copy)

    mmr_df_updated = pd.DataFrame(updated_rows)
    summary_df = make_summary_df_wide(mmr_df_updated)

    return mmr_df_updated, summary_df


# ==============================================================
# [5] 실행
# ==============================================================

mmr_df_updated_elo, summary_df_elo = update_mmr_elo(mmr_df_cleaned_default.copy())

print("=== ELO 포함 summary_df ===")
print(summary_df_elo.head())


# ==============================================================
# [6] 시각화
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
