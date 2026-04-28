user_name_path = r"C:/Users/PC/Desktop/김필준/data/2026 유저_0415.csv"

try:
    user_name = pd.read_csv(user_name_path, encoding='utf-8', on_bad_lines='skip')
except UnicodeDecodeError:
    user_name = pd.read_csv(user_name_path, encoding='cp949', on_bad_lines='skip')

user_name = user_name[['puuid', 'riot_name']].drop_duplicates()


mmr_df_updated_elo = mmr_df_updated_elo.merge(
    user_name[['puuid', 'riot_name']],
    on='puuid',
    how='left'
)


import numpy as np
import pandas as pd
import matplotlib.pyplot as plt

# ==============================================================
# 0. 유저 이름 파일 로드 + 데이터 연결
# ==============================================================

user_name_path = r"C:/Users/PC/Desktop/김필준/data/2026 유저_0415.csv"

try:
    user_name = pd.read_csv(user_name_path, encoding="utf-8", on_bad_lines="skip")
    print("UTF-8 인코딩으로 유저 이름 파일 로드 성공")
except UnicodeDecodeError:
    user_name = pd.read_csv(user_name_path, encoding="cp949", on_bad_lines="skip")
    print("CP949 인코딩으로 유저 이름 파일 로드 성공")

user_name = user_name[["puuid", "riot_name"]].drop_duplicates()

# summary_df_elo에 riot_name 붙이기
summary_df_elo = summary_df_elo.drop(
    columns=[c for c in ["riot_name", "riot_name_x", "riot_name_y"] if c in summary_df_elo.columns]
)

summary_df_elo = summary_df_elo.merge(
    user_name,
    on="puuid",
    how="left"
)

summary_df_elo = summary_df_elo[["riot_name"] + [c for c in summary_df_elo.columns if c != "riot_name"]]

# mmr_df_updated_elo에도 riot_name 붙이기
mmr_df_updated_elo = mmr_df_updated_elo.drop(
    columns=[c for c in ["riot_name", "riot_name_x", "riot_name_y"] if c in mmr_df_updated_elo.columns]
)

mmr_df_updated_elo = mmr_df_updated_elo.merge(
    user_name,
    on="puuid",
    how="left"
)

print("summary_df_elo 컬럼:", summary_df_elo.columns.tolist())
print("mmr_df_updated_elo 컬럼:", mmr_df_updated_elo.columns.tolist())


# ==============================================================
# 1. 기본 설정
# ==============================================================

POS_LIST = ["TOP", "JUNGLE", "MIDDLE", "BOTTOM", "UTILITY"]

metrics = [
    "kills",
    "deaths",
    "assists",
    "gold_per_min",
    "exp_per_min",
    "dpm",
    "damage_to_turrets_per_min",
    "vision_score",
    "damage_taken_per_min",
    "cs_per_min",
    "kda",
    "damage_taken_per_death",
    "damage_dealt_per_death",
    "wards_placed_per_min",
    "wards_killed_per_min",
    "cc_time_per_min",
    "heal_on_teammates",
    "shield_on_teammates",
    "lane_gold_diff",
    "game_impact_winloss_norm",
    "game_n_person_contribution",
    "game_impact_vs_opponent",
]

INDICATOR_DESC_KO = {
    "dpm": "분당 챔피언에게 가한 피해량. 교전 및 딜링 기여도를 보여준다.",
    "cs_per_min": "분당 CS 수급량. 라인/정글 운영과 성장 속도를 나타낸다.",
    "gold_per_min": "분당 획득 골드. 아이템 성장 속도와 자원 확보 능력을 나타낸다.",
    "exp_per_min": "분당 경험치. 레벨링 속도와 성장 안정성을 나타낸다.",
    "kda": "킬과 어시스트 대비 데스 비율. 교전 안정성과 생존 기여도를 함께 반영한다.",
    "damage_dealt_per_death": "데스당 가한 피해량. 죽기 전까지 얼마나 효율적으로 딜을 넣었는지 보여준다.",
    "game_n_person_contribution": "게임 내 몇 인분 지표. 한 경기에서 개인이 차지한 기여도 비중을 의미한다.",
    "game_impact_vs_opponent": "동일 포지션 상대 대비 영향력 지표. 라인전 또는 맞상대 우위를 반영한다.",
}

RADAR_LABEL_MAP = {
    "dpm": "DPM",
    "cs_per_min": "CSM",
    "gold_per_min": "GPM",
    "exp_per_min": "XPM",
    "kda": "KDA",
    "damage_dealt_per_death": "DPD",
    "game_n_person_contribution": "personnel",
    "game_impact_vs_opponent": "vs opponent",
}

BASE_KPI_MAP = {
    "dpm": "dpm",
    "cs_per_min": "cs_per_min",
    "gold_per_min": "gold_per_min",
    "exp_per_min": "exp_per_min",
    "kda": "kda",
    "damage_dealt_per_death": "damage_dealt_per_death",
    "game_n_person_contribution": "game_n_person_contribution",
    "game_impact_vs_opponent": "game_impact_vs_opponent",
}

POS_KPI_MAP = {pos: BASE_KPI_MAP.copy() for pos in POS_LIST}

POS_RADAR_WEIGHTS = {
    "TOP": {
        "dpm": 0.90,
        "cs_per_min": 0.90,
        "gold_per_min": 0.75,
        "exp_per_min": 0.75,
        "kda": 0.80,
        "damage_dealt_per_death": 0.85,
        "game_n_person_contribution": 0.80,
        "game_impact_vs_opponent": 1.00,
    },
    "JUNGLE": {
        "dpm": 0.80,
        "cs_per_min": 0.75,
        "gold_per_min": 0.75,
        "exp_per_min": 0.75,
        "kda": 0.90,
        "damage_dealt_per_death": 0.75,
        "game_n_person_contribution": 0.90,
        "game_impact_vs_opponent": 1.00,
    },
    "MIDDLE": {
        "dpm": 0.95,
        "cs_per_min": 0.80,
        "gold_per_min": 0.75,
        "exp_per_min": 0.80,
        "kda": 0.85,
        "damage_dealt_per_death": 0.80,
        "game_n_person_contribution": 0.85,
        "game_impact_vs_opponent": 1.00,
    },
    "BOTTOM": {
        "dpm": 1.00,
        "cs_per_min": 0.90,
        "gold_per_min": 0.85,
        "exp_per_min": 0.75,
        "kda": 0.80,
        "damage_dealt_per_death": 0.85,
        "game_n_person_contribution": 0.75,
        "game_impact_vs_opponent": 0.85,
    },
    "UTILITY": {
        "dpm": 0.65,
        "cs_per_min": 0.55,
        "gold_per_min": 0.55,
        "exp_per_min": 0.55,
        "kda": 1.00,
        "damage_dealt_per_death": 0.60,
        "game_n_person_contribution": 1.00,
        "game_impact_vs_opponent": 0.90,
    },
}


# ==============================================================
# 2. 스타일 / 성향 규칙
# ==============================================================

STYLE_RULES = [
    ("불도저", lambda p: p.get("dpm", 0) >= 75 and p.get("damage_dealt_per_death", 100) <= 35),
    ("생존형 딜러", lambda p: p.get("dpm", 0) >= 75 and p.get("damage_dealt_per_death", 0) >= 75),
    ("성장형(파밍 중심)", lambda p: p.get("cs_per_min", 0) >= 75 and (p.get("gold_per_min", 0) >= 75 or p.get("exp_per_min", 0) >= 75)),
    ("팀파이트 캐리형", lambda p: p.get("kda", 0) >= 75 and p.get("game_impact_vs_opponent", 0) >= 75),
    ("밸런스형(올라운더)", lambda p: p.get("game_n_person_contribution", 0) >= 70 and p.get("game_impact_vs_opponent", 0) >= 60),
    ("운영형", lambda p: (p.get("cs_per_min", 0) >= 70 or p.get("gold_per_min", 0) >= 70) and p.get("kda", 100) <= 40),
]

STYLE_DESC_KO = {
    "불도저": "딜 지표는 높지만 데스 대비 효율이 낮아, 과감한 교전 빈도가 높고 리스크도 큰 유형.",
    "생존형 딜러": "딜 지표와 데스 대비 효율이 모두 높아, 살아남으며 지속 딜을 확보하는 안정형 딜러 유형.",
    "성장형(파밍 중심)": "CS/골드/경험치 등 성장 지표가 높아, 성장 우위를 바탕으로 영향력을 만드는 유형.",
    "팀파이트 캐리형": "KDA와 맞상대 우위가 강해, 교전/한타에서 게임 흐름을 주도하는 유형.",
    "밸런스형(올라운더)": "특정 지표에 치우치지 않고 전반적으로 고르게 좋은 성과를 내는 유형.",
    "운영형": "성장 지표는 높지만 교전 효율은 낮을 수 있어, 운영 중심으로 게임을 풀어가는 유형.",
    "밸런스형(기본)": "특정 성향으로 강하게 분류되지 않는 균형형 패턴.",
}

def _fmt_combo(items):
    return " + ".join(items) if isinstance(items, list) else str(items)

POSITION_TENDENCY_RULES = {
    "TOP": [
        {
            "tendency": "사이드 운영형 탑",
            "combo": _fmt_combo(["cs_per_min↑", "gold_per_min↑", "vs opponent↑"]),
            "rule": lambda p: p.get("cs_per_min", 0) >= 70 and p.get("gold_per_min", 0) >= 65 and p.get("game_impact_vs_opponent", 0) >= 60,
            "interpretation": "사이드 운영과 성장 기반으로 상대 탑보다 높은 영향력을 만드는 성향.",
        },
        {
            "tendency": "한타 개입형 탑",
            "combo": _fmt_combo(["dpm↑", "kda↑", "personnel↑"]),
            "rule": lambda p: p.get("dpm", 0) >= 65 and p.get("kda", 0) >= 65 and p.get("game_n_person_contribution", 0) >= 65,
            "interpretation": "교전과 한타에서 팀 기여도가 높은 탑 라이너 성향.",
        },
    ],
    "JUNGLE": [
        {
            "tendency": "갱킹형 정글러",
            "combo": _fmt_combo(["kda↑", "personnel↑", "vs opponent↑"]),
            "rule": lambda p: p.get("kda", 0) >= 70 and p.get("game_n_person_contribution", 0) >= 70 and p.get("game_impact_vs_opponent", 0) >= 60,
            "interpretation": "교전 개입과 팀 기여가 높고, 맞정글 우위도 확보하는 주도형 갱킹 성향.",
        },
        {
            "tendency": "오브젝트/주도권형 정글러",
            "combo": _fmt_combo(["vs opponent↑", "personnel↑", "cs_per_min 중상"]),
            "rule": lambda p: p.get("game_impact_vs_opponent", 0) >= 75 and p.get("game_n_person_contribution", 0) >= 65 and p.get("cs_per_min", 0) >= 55,
            "interpretation": "상대 정글 대비 우위를 바탕으로 오브젝트와 전장 주도권을 만드는 성향.",
        },
        {
            "tendency": "파밍형 정글러",
            "combo": _fmt_combo(["cs_per_min↑", "gold_per_min↑", "exp_per_min↑"]),
            "rule": lambda p: p.get("cs_per_min", 0) >= 75 and p.get("gold_per_min", 0) >= 70 and p.get("exp_per_min", 0) >= 70,
            "interpretation": "개입보다 성장 속도와 자원 확보를 통해 영향력을 만드는 파밍 중심 성향.",
        },
    ],
    "MIDDLE": [
        {
            "tendency": "로밍형 미드",
            "combo": _fmt_combo(["kda↑", "personnel↑", "cs_per_min↓"]),
            "rule": lambda p: p.get("kda", 0) >= 70 and p.get("game_n_person_contribution", 0) >= 70 and p.get("cs_per_min", 100) <= 50,
            "interpretation": "라인 고정 성장보다 합류와 교전 개입으로 팀 기여를 만드는 로밍 성향.",
        },
        {
            "tendency": "라인 캐리형 미드",
            "combo": _fmt_combo(["vs opponent↑", "dpm↑", "cs_per_min 중상"]),
            "rule": lambda p: p.get("game_impact_vs_opponent", 0) >= 70 and p.get("dpm", 0) >= 70 and p.get("cs_per_min", 0) >= 55,
            "interpretation": "라인전 우위를 딜과 교전 성과로 전환해 게임을 주도하는 성향.",
        },
    ],
    "BOTTOM": [
        {
            "tendency": "하드 캐리형 원딜",
            "combo": _fmt_combo(["dpm↑", "gold_per_min↑", "damage_dealt_per_death↑"]),
            "rule": lambda p: p.get("dpm", 0) >= 75 and p.get("gold_per_min", 0) >= 70 and p.get("damage_dealt_per_death", 0) >= 70,
            "interpretation": "높은 성장과 안정적인 딜링을 바탕으로 후반 캐리력을 보이는 원딜 성향.",
        },
        {
            "tendency": "라인전 우위형 원딜",
            "combo": _fmt_combo(["vs opponent↑", "cs_per_min↑", "dpm↑"]),
            "rule": lambda p: p.get("game_impact_vs_opponent", 0) >= 70 and p.get("cs_per_min", 0) >= 65 and p.get("dpm", 0) >= 65,
            "interpretation": "상대 바텀 대비 성장과 딜링 우위를 확보하는 라인전 중심 성향.",
        },
    ],
    "UTILITY": [
        {
            "tendency": "팀 기여형 서포터",
            "combo": _fmt_combo(["personnel↑", "kda↑", "vs opponent↑"]),
            "rule": lambda p: p.get("game_n_person_contribution", 0) >= 70 and p.get("kda", 0) >= 65 and p.get("game_impact_vs_opponent", 0) >= 60,
            "interpretation": "시야·교전 보조·생존 기여를 통해 팀 전체 성과에 기여하는 서포터 성향.",
        },
        {
            "tendency": "교전 개시형 서포터",
            "combo": _fmt_combo(["personnel↑", "dpm 중상", "kda 중상"]),
            "rule": lambda p: p.get("game_n_person_contribution", 0) >= 70 and p.get("dpm", 0) >= 55 and p.get("kda", 0) >= 55,
            "interpretation": "교전 개시와 합류를 통해 팀파이트 영향력을 만드는 서포터 성향.",
        },
    ],
}


# ==============================================================
# 3. 유틸 함수
# ==============================================================

def normalize_report_columns(df):
    df = df.copy()

    rename_map = {
        "DPM": "dpm",
        "CSM": "cs_per_min",
        "GPM": "gold_per_min",
        "XPM": "exp_per_min",
        "KDA": "kda",
        "total_damage_dealt_to_champions": "dpm",
        "gold_earned": "gold_per_min",
        "exp": "exp_per_min",
    }

    for old_col, new_col in rename_map.items():
        if old_col in df.columns and new_col not in df.columns:
            df = df.rename(columns={old_col: new_col})

    return df

def percentile_rank(value, population):
    pop = pd.to_numeric(population, errors="coerce").dropna()
    if pop.empty or pd.isna(value):
        return np.nan
    return float((pop <= value).mean() * 100)

def make_mmr_band(series, bin_size=100):
    s = pd.to_numeric(series, errors="coerce")
    lo = np.floor(s / bin_size) * bin_size
    hi = lo + bin_size
    return lo.astype("Int64").astype(str) + "~" + hi.astype("Int64").astype(str)

def pick_main_position_from_summary(summary_row, min_main_games=1):
    games = {}

    for pos in POS_LIST:
        game_col = f"{pos}_games"
        games[pos] = float(summary_row.get(game_col, 0)) if game_col in summary_row.index else 0

    main_pos = max(games, key=games.get)
    main_games = int(games[main_pos])

    if main_games < min_main_games:
        return "Unknown", main_games

    return main_pos, main_games

def get_winrate_from_game_df(player_games_df):
    if "game_result" not in player_games_df.columns or player_games_df.empty:
        return np.nan
    return float(player_games_df["game_result"].mean() * 100)

def classify_style_from_pct(pct_dict):
    for label, rule_fn in STYLE_RULES:
        try:
            if rule_fn(pct_dict):
                return label
        except Exception:
            continue
    return "밸런스형(기본)"

def classify_position_tendencies(main_pos, pct_dict, max_results=3):
    rules = POSITION_TENDENCY_RULES.get(main_pos, [])
    hits = []

    for rule in rules:
        try:
            if rule["rule"](pct_dict):
                hits.append({
                    "포지션": main_pos,
                    "지표 조합": rule["combo"],
                    "플레이 성향": rule["tendency"],
                    "해석": rule["interpretation"],
                })
        except Exception:
            continue

    if not hits:
        hits.append({
            "포지션": main_pos,
            "지표 조합": "-",
            "플레이 성향": "뚜렷한 패턴 없음",
            "해석": "현재 퍼센타일 조합이 특정 성향 규칙에 강하게 해당되지 않습니다.",
        })

    return pd.DataFrame(hits).head(max_results)

def build_pos_kpi_df(mmr_df):
    mmr_df = normalize_report_columns(mmr_df)

    required = ["puuid", "position"]
    for col in required:
        if col not in mmr_df.columns:
            raise KeyError(f"{col} 컬럼이 필요합니다.")

    available_metrics = [m for m in BASE_KPI_MAP.values() if m in mmr_df.columns]

    return (
        mmr_df.groupby(["puuid", "position"], as_index=False)[available_metrics]
        .mean()
        .rename(columns={"puuid": "player_id", "position": "team_position"})
    )

def plot_weighted_radar(radar_table, title="플레이 스타일 레이더", subtitle=None):
    if radar_table is None or radar_table.empty:
        print("레이더를 그릴 데이터가 비었습니다.")
        return

    labels_raw = radar_table["indicator"].tolist()
    labels = [RADAR_LABEL_MAP.get(label, label) for label in labels_raw]

    user_vals = radar_table["user_w_pct"].astype(float).tolist()
    ref_vals = radar_table["ref_w_pct"].astype(float).tolist()

    if len(labels) < 3:
        print("레이더 축이 3개 미만입니다.")
        return

    N = len(labels)
    angles = np.linspace(0, 2 * np.pi, N, endpoint=False).tolist()
    angles += angles[:1]
    user_vals += user_vals[:1]
    ref_vals += ref_vals[:1]

    fig = plt.figure(figsize=(7.2, 7.2))
    ax = plt.subplot(111, polar=True)

    ax.set_theta_offset(np.pi / 2)
    ax.set_theta_direction(-1)
    ax.set_thetagrids(np.degrees(angles[:-1]), labels, fontsize=11)
    ax.set_ylim(0, 100)
    ax.set_yticks([20, 40, 60, 80, 100])
    ax.set_yticklabels(["20", "40", "60", "80", "100"], fontsize=9)

    ax.plot(angles, user_vals, linewidth=2, label="Player")
    ax.fill(angles, user_vals, alpha=0.22)

    ax.plot(
        angles,
        ref_vals,
        linestyle="--",
        linewidth=1.8,
        color="gray",
        label="Reference Avg"
    )

    # ✅ 제목 겹침 방지
    ax.set_title(title, fontsize=15, pad=35)

    if subtitle:
        fig.text(
            0.5,
            0.94,
            subtitle,
            ha="center",
            va="center",
            fontsize=10
        )

    ax.legend(
        loc="lower center",
        bbox_to_anchor=(0.5, -0.18),
        ncol=2,
        frameon=False
    )

    plt.tight_layout(rect=[0, 0.05, 1, 0.90])
    plt.show()


# ==============================================================
# 4. 리포트 생성 함수
# ==============================================================

def generate_player_report_ko(
    player_name,
    df_processed,
    summary_df_all,
    bin_size=100,
    min_games_in_pos_group=20,
    min_main_games=1,
    radar_topk=8,
    min_band_users=5,
    tendency_max_results=3,
):
    report = {
        "player_name": player_name,
        "narrative_lines": [],
        "compare_table": None,
        "radar_table": None,
        "indicator_desc": [],
        "style_label": None,
        "style_desc": None,
        "main_position": None,
        "mmr_band": None,
        "ref_count": None,
        "ref_mode": None,
        "tendency_table": None,
        "category_summary": None,
    }

    df_processed = normalize_report_columns(df_processed)
    summary_df_all = normalize_report_columns(summary_df_all)

    if "riot_name" not in summary_df_all.columns:
        report["narrative_lines"].append("summary_df_all에 riot_name 컬럼이 없습니다.")
        return report

    srow_df = summary_df_all[summary_df_all["riot_name"] == player_name]

    if srow_df.empty:
        report["narrative_lines"].append(f"{player_name} 유저를 summary_df_all에서 찾지 못했습니다.")
        return report

    srow = srow_df.iloc[0]

    if "puuid" not in summary_df_all.columns:
        report["narrative_lines"].append("summary_df_all에 puuid 컬럼이 없습니다.")
        return report

    pid = srow["puuid"]

    main_pos, main_games = pick_main_position_from_summary(srow, min_main_games=min_main_games)
    report["main_position"] = main_pos

    if main_pos == "Unknown":
        report["narrative_lines"].append(f"{player_name}의 메인 포지션을 판수 기준으로 결정할 수 없습니다.")
        return report

    player_games_df = df_processed[df_processed["puuid"] == pid]
    win_rate = get_winrate_from_game_df(player_games_df)

    pos_kpi_df = build_pos_kpi_df(df_processed)

    my_pos_kpi = pos_kpi_df[
        (pos_kpi_df["player_id"] == pid) &
        (pos_kpi_df["team_position"] == main_pos)
    ]

    if my_pos_kpi.empty:
        report["narrative_lines"].append(f"{player_name}의 {main_pos} 포지션 KPI가 없습니다.")
        return report

    my_pos_kpi = my_pos_kpi.iloc[0]

    base_mmr_col = None
    for col in [f"{main_pos}_mmr", "total_mmr", "MMR"]:
        if col in summary_df_all.columns:
            base_mmr_col = col
            break

    if base_mmr_col is None:
        report["narrative_lines"].append("summary_df_all에서 MMR 컬럼을 찾지 못했습니다.")
        return report

    my_mmr = srow.get(base_mmr_col, np.nan)
    my_band = make_mmr_band(pd.Series([my_mmr]), bin_size=bin_size).iloc[0]
    report["mmr_band"] = my_band

    temp = summary_df_all.copy()
    temp["mmr_band"] = make_mmr_band(temp[base_mmr_col], bin_size=bin_size)

    pos_games_col = f"{main_pos}_games"

    if pos_games_col in temp.columns:
        pos_users = temp[temp[pos_games_col] >= min_games_in_pos_group].copy()
    else:
        pos_users = temp.copy()

    band_users = pos_users[pos_users["mmr_band"] == my_band].copy()

    if len(band_users) < min_band_users:
        ref_users = pos_users.copy()
        report["ref_mode"] = f"{main_pos} 전체 기준"
    else:
        ref_users = band_users.copy()
        report["ref_mode"] = f"MMR 밴드({my_band}) 내 {main_pos}"

    report["ref_count"] = len(ref_users)

    ref_ids = ref_users[["puuid"]].rename(columns={"puuid": "player_id"})

    ref_pos_kpis = ref_ids.merge(
        pos_kpi_df[pos_kpi_df["team_position"] == main_pos],
        on="player_id",
        how="left"
    )

    kpi_map = {
        k: v for k, v in BASE_KPI_MAP.items()
        if v in ref_pos_kpis.columns and v in df_processed.columns
    }

    rows = []
    pct_dict_for_style = {}

    for kpi_name, col in kpi_map.items():
        my_val = float(my_pos_kpi.get(col, np.nan))
        ref_avg = float(ref_pos_kpis[col].mean())

        user_pct = percentile_rank(my_val, ref_pos_kpis[col])
        ref_avg_pct = percentile_rank(ref_avg, ref_pos_kpis[col])

        if pd.isna(my_val) or pd.isna(ref_avg) or pd.isna(user_pct):
            continue

        rows.append({
            "indicator": kpi_name,
            "user": my_val,
            "ref_avg": ref_avg,
            "user_pct": user_pct,
            "ref_avg_pct": ref_avg_pct,
        })

        pct_dict_for_style[kpi_name] = user_pct

    compare_table = pd.DataFrame(rows)

    if compare_table.empty:
        report["narrative_lines"].append("비교 가능한 KPI 데이터가 없습니다.")
        return report

    compare_table = compare_table.sort_values("user_pct", ascending=False).reset_index(drop=True)
    report["compare_table"] = compare_table

    style_label = classify_style_from_pct(pct_dict_for_style)
    style_desc = STYLE_DESC_KO.get(style_label, "")

    tendency_table = classify_position_tendencies(
        main_pos=main_pos,
        pct_dict=pct_dict_for_style,
        max_results=tendency_max_results
    )

    report["style_label"] = style_label
    report["style_desc"] = style_desc
    report["tendency_table"] = tendency_table

    category_summary = pd.DataFrame([{
        "유저명": player_name,
        "메인 포지션": main_pos,
        "MMR 밴드": my_band,
        "비교 기준": report["ref_mode"],
        "비교 유저 수": report["ref_count"],
        "기본 스타일": style_label,
        "스타일 설명": style_desc,
        "대표 성향": tendency_table.iloc[0]["플레이 성향"],
        "대표 성향 해석": tendency_table.iloc[0]["해석"],
    }])

    report["category_summary"] = category_summary

    desc_lines = []
    for indicator in compare_table["indicator"].tolist():
        label = RADAR_LABEL_MAP.get(indicator, indicator)
        desc = INDICATOR_DESC_KO.get(indicator, "(설명 미정)")
        desc_lines.append(f"- {label}: {desc}")

    report["indicator_desc"] = desc_lines

    report["narrative_lines"].append(
        f"{player_name}의 메인 포지션은 {main_pos}이며, 비교 기준은 {report['ref_mode']}입니다."
    )

    if not pd.isna(win_rate):
        report["narrative_lines"].append(f"전체 승률은 {win_rate:.1f}%입니다.")

    report["narrative_lines"].append(f"[기본 스타일] {style_label}")
    report["narrative_lines"].append(f"→ {style_desc}")
    report["narrative_lines"].append(f"[포지션 보정 플레이 성향] {tendency_table.iloc[0]['플레이 성향']}")
    report["narrative_lines"].append(f"→ {tendency_table.iloc[0]['해석']}")

    weights = POS_RADAR_WEIGHTS.get(main_pos, {})
    radar_df = compare_table.sort_values("user_pct", ascending=False).head(radar_topk).copy()

    radar_df["weight"] = radar_df["indicator"].map(lambda x: float(weights.get(x, 0.8)))
    radar_df["user_w_pct"] = (radar_df["user_pct"] * radar_df["weight"]).clip(0, 100)
    radar_df["ref_w_pct"] = (radar_df["ref_avg_pct"] * radar_df["weight"]).clip(0, 100)

    report["radar_table"] = radar_df[
        ["indicator", "user_pct", "ref_avg_pct", "weight", "user_w_pct", "ref_w_pct"]
    ].copy()

    subtitle = f"{player_name} | {main_pos} | {report['ref_mode']}"

    plot_weighted_radar(
        report["radar_table"][["indicator", "user_w_pct", "ref_w_pct"]],
        title="플레이 스타일 레이더",
        subtitle=subtitle
    )

    return report


# ==============================================================
# 5. 실행
# ==============================================================

def run_player_report(player_name):
    print("\n==============================")
    print(f"🎮 유저 리포트: {player_name}")
    print("==============================")

    summary_for_report = summary_df_elo.copy()

    report = generate_player_report_ko(
        player_name=player_name,
        df_processed=mmr_df_updated_elo,
        summary_df_all=summary_for_report,
        min_games_in_pos_group=20,
        radar_topk=8,
        tendency_max_results=3
    )

    # ❗ 유저 없을 때 처리
    if report["compare_table"] is None:
        print("\n❌ 해당 유저를 찾을 수 없습니다.")
        for line in report["narrative_lines"]:
            print(line)
        return

    # ==============================
    # 1. 지표 설명 (먼저 출력)
    # ==============================
    print("\n📖 지표 설명")
    for desc in report["indicator_desc"]:
        print(desc)
    # ==============================
    # 2. 요약
    # ==============================
    print("\n📌 리포트 요약")
    for line in report["narrative_lines"]:
        print(line)
    # ==============================
    # 3. 카테고리
    # ==============================
    print("\n🎯 카테고리 요약")
    display(report["category_summary"])
    # ==============================
    # 4. 비교 테이블
    # ==============================
    print("\n📊 핵심 지표 비교")
    display(report["compare_table"])

    # ==============================
    # 5. 성향 분석
    # ==============================
    print("\n🔥 포지션 기반 성향 분석")
    display(report["tendency_table"])

    # ==============================
    # 6. 레이더 테이블
    # ==============================
    print("\n📡 레이더 지표")
    display(report["radar_table"])


run_player_report("이건끄미야")


# 1. 먼저 이것 확인
print('summary_df_elo' in globals())
print('mmr_df_updated_elo' in globals())
print('user_name' in globals())


print('position_dfs' in globals())
print(type(position_dfs))
print(position_dfs.keys())


print('position_dfs' in globals())
print(type(position_dfs))
print(position_dfs.keys())
