{
 "cells": [
  {
   "cell_type": "markdown",
   "id": "f1d9bf6e",
   "metadata": {},
   "source": [
    "# 챔피언 스코어 — 클랜별 (데이터 상위 2개 클랜)\n",
    "\n",
    "v2 하이브리드 방식을 **클랜(`guild_id`) 단위로 분리** 적용한다. 각 클랜의 데이터로\n",
    "**데이터 기반 가중치·팀 실력 보정·표본 신뢰도를 클랜 내부에서 학습**하므로,\n",
    "클랜별 플레이 성향이 점수에 반영된다. 데이터가 많은 **상위 N개 클랜**만 자동 선택한다.\n",
    "\n",
    "> 방법론 상세(V1 팀 보정 / V2 퍼포먼스 / 블렌드 가중치)는 `champion_score_hybrid_v2.ipynb` 및 보고서 참조.\n",
    "> 이 노트북은 그 파이프라인을 클랜별로 감싼 것이다.\n"
   ]
  },
  {
   "cell_type": "markdown",
   "id": "afb457f8",
   "metadata": {},
   "source": [
    "# 0. 환경설정"
   ]
  },
  {
   "cell_type": "code",
   "execution_count": 1,
   "id": "f72cb1a4",
   "metadata": {
    "execution": {
     "iopub.execute_input": "2026-07-29T06:59:52.725567Z",
     "iopub.status.busy": "2026-07-29T06:59:52.725360Z",
     "iopub.status.idle": "2026-07-29T06:59:55.644831Z",
     "shell.execute_reply": "2026-07-29T06:59:55.643254Z"
    }
   },
   "outputs": [],
   "source": [
    "import pandas as pd\n",
    "import numpy as np\n",
    "from sklearn.linear_model import LogisticRegression\n",
    "pd.set_option(\"display.max_columns\", None); pd.set_option(\"display.width\", 180)"
   ]
  },
  {
   "cell_type": "markdown",
   "id": "7d88e29b",
   "metadata": {},
   "source": [
    "# 1. 파라미터 (스케줄러/재실행 시 여기만 수정)"
   ]
  },
  {
   "cell_type": "code",
   "execution_count": 2,
   "id": "dd7c0e43",
   "metadata": {
    "execution": {
     "iopub.execute_input": "2026-07-29T06:59:55.647351Z",
     "iopub.status.busy": "2026-07-29T06:59:55.646953Z",
     "iopub.status.idle": "2026-07-29T06:59:55.658412Z",
     "shell.execute_reply": "2026-07-29T06:59:55.657404Z"
    }
   },
   "outputs": [],
   "source": [
    "PATH        = \"all_participant_metric_data.csv\"\n",
    "TOP_N_CLANS = 2          # 데이터 많은 상위 N개 클랜만\n",
    "CLAN_COL    = \"guild_id\" # 클랜 식별 컬럼\n",
    "MIN_GAMES   = 10\n",
    "W_V1, W_V2  = 0.35, 0.65\n",
    "ALPHA       = 0.5\n",
    "RZ_CLIP     = 4\n",
    "POSITION_ORDER = [\"TOP\",\"JUG\",\"MID\",\"ADC\",\"SUP\"]\n",
    "\n",
    "METRIC_DIR = {\"dpm\":1,\"kda\":1,\"damage_dealt_per_death\":1,\"gold_per_min\":1,\"cs_per_min\":1,\n",
    " \"exp_per_min\":1,\"lane_gold_diff\":1,\"damage_to_objectives\":1,\"takedowns_before_15min\":1,\n",
    " \"dead_time_pct\":-1,\"vision_score\":1}\n",
    "METRICS = list(METRIC_DIR)\n",
    "\n",
    "EXPERT = {\n",
    " \"TOP\":{\"dpm\":.55,\"kda\":.55,\"damage_dealt_per_death\":.75,\"gold_per_min\":.70,\"cs_per_min\":.55,\"exp_per_min\":.85,\"lane_gold_diff\":.95,\"damage_to_objectives\":.60,\"takedowns_before_15min\":.55,\"dead_time_pct\":.70,\"vision_score\":.25},\n",
    " \"JUG\":{\"dpm\":.45,\"kda\":.60,\"damage_dealt_per_death\":.60,\"gold_per_min\":.65,\"cs_per_min\":.45,\"exp_per_min\":.85,\"lane_gold_diff\":.80,\"damage_to_objectives\":.95,\"takedowns_before_15min\":.85,\"dead_time_pct\":.70,\"vision_score\":.40},\n",
    " \"MID\":{\"dpm\":.70,\"kda\":.55,\"damage_dealt_per_death\":.70,\"gold_per_min\":.70,\"cs_per_min\":.45,\"exp_per_min\":.85,\"lane_gold_diff\":.90,\"damage_to_objectives\":.60,\"takedowns_before_15min\":.65,\"dead_time_pct\":.70,\"vision_score\":.30},\n",
    " \"ADC\":{\"dpm\":.75,\"kda\":.55,\"damage_dealt_per_death\":.75,\"gold_per_min\":.85,\"cs_per_min\":.65,\"exp_per_min\":.85,\"lane_gold_diff\":.90,\"damage_to_objectives\":.80,\"takedowns_before_15min\":.50,\"dead_time_pct\":.70,\"vision_score\":.25},\n",
    " \"SUP\":{\"dpm\":.30,\"kda\":.60,\"damage_dealt_per_death\":.50,\"gold_per_min\":.45,\"cs_per_min\":.15,\"exp_per_min\":.80,\"lane_gold_diff\":.90,\"damage_to_objectives\":.55,\"takedowns_before_15min\":.55,\"dead_time_pct\":.70,\"vision_score\":.45},\n",
    "}"
   ]
  },
  {
   "cell_type": "markdown",
   "id": "38c352e6",
   "metadata": {},
   "source": [
    "# 2. 데이터 로드 & 상위 클랜 선택"
   ]
  },
  {
   "cell_type": "code",
   "execution_count": 3,
   "id": "eb7b9ba3",
   "metadata": {
    "execution": {
     "iopub.execute_input": "2026-07-29T06:59:55.660464Z",
     "iopub.status.busy": "2026-07-29T06:59:55.660273Z",
     "iopub.status.idle": "2026-07-29T06:59:56.804925Z",
     "shell.execute_reply": "2026-07-29T06:59:56.803821Z"
    }
   },
   "outputs": [
    {
     "name": "stdout",
     "output_type": "stream",
     "text": [
      "전체 클랜 수: 7\n",
      "데이터 상위 클랜 규모:\n",
      "guild_id\n",
      "1281251734454276106    24700\n",
      "936184382228693052      4070\n",
      "\n",
      "선택된 클랜: [1281251734454276106, 936184382228693052]\n"
     ]
    }
   ],
   "source": [
    "df_all = pd.read_csv(PATH)\n",
    "df_all = df_all[df_all[\"is_deleted\"] == False].copy()\n",
    "\n",
    "clan_sizes = df_all[CLAN_COL].value_counts()\n",
    "TOP_CLANS = clan_sizes.head(TOP_N_CLANS).index.tolist()\n",
    "print(\"전체 클랜 수:\", df_all[CLAN_COL].nunique())\n",
    "print(\"데이터 상위 클랜 규모:\")\n",
    "print(clan_sizes.head(TOP_N_CLANS).to_string())\n",
    "print(\"\\n선택된 클랜:\", TOP_CLANS)"
   ]
  },
  {
   "cell_type": "markdown",
   "id": "8d806088",
   "metadata": {},
   "source": [
    "# 3. 클랜별 스코어 함수\n",
    "\n",
    "한 클랜의 데이터를 받아 라인별 챔피언 스코어를 반환한다.\n",
    "모든 학습(스케일·가중치·팀보정·신뢰도)이 **그 클랜 내부**에서 이뤄진다."
   ]
  },
  {
   "cell_type": "code",
   "execution_count": 4,
   "id": "1c3a2815",
   "metadata": {
    "execution": {
     "iopub.execute_input": "2026-07-29T06:59:56.807420Z",
     "iopub.status.busy": "2026-07-29T06:59:56.806720Z",
     "iopub.status.idle": "2026-07-29T06:59:56.819207Z",
     "shell.execute_reply": "2026-07-29T06:59:56.818139Z"
    }
   },
   "outputs": [],
   "source": [
    "def robust(s):\n",
    "    iqr = s.quantile(0.75) - s.quantile(0.25)\n",
    "    return (s - s.median()) / iqr if iqr > 0 else s * 0.0\n",
    "\n",
    "def z_pos(s):\n",
    "    sd = s.std(ddof=0)\n",
    "    return (s - s.mean()) / sd if sd > 0 else s * 0.0\n",
    "\n",
    "def run_for_clan(d):\n",
    "    d = d.copy()\n",
    "    # 방향 정렬 + 포지션 내 로버스트 스케일\n",
    "    for m, sign in METRIC_DIR.items():\n",
    "        if sign == -1: d[m] = -d[m]\n",
    "    for m in METRICS:\n",
    "        d[f\"{m}_rz\"] = d.groupby(\"position\")[m].transform(robust).clip(-RZ_CLIP, RZ_CLIP)\n",
    "\n",
    "    # 클랜 내부 데이터 가중치 → 전문가값과 블렌드\n",
    "    ROLE_W = {}\n",
    "    for pos in POSITION_ORDER:\n",
    "        dd = d[d.position == pos]\n",
    "        X = dd[[f\"{m}_rz\" for m in METRICS]].fillna(0).values\n",
    "        y = dd.game_result.values\n",
    "        if len(np.unique(y)) < 2 or len(dd) < 20:\n",
    "            dw = {m: 0.0 for m in METRICS}          # 표본 부족 시 전문가값만\n",
    "        else:\n",
    "            lr = LogisticRegression(C=0.5, max_iter=1000).fit(X, y)\n",
    "            coef = np.clip(lr.coef_[0], 0, None)\n",
    "            dw = dict(zip(METRICS, coef/coef.max() if coef.max() > 0 else coef))\n",
    "        ew = EXPERT[pos]; mx = max(ew.values())\n",
    "        ROLE_W[pos] = {m: ALPHA*dw[m] + (1-ALPHA)*(ew[m]/mx) for m in METRICS}\n",
    "\n",
    "    # V2 퍼포먼스\n",
    "    w_arr = {pos: np.array([ROLE_W[pos][m] for m in METRICS]) for pos in POSITION_ORDER}\n",
    "    rz = d[[f\"{m}_rz\" for m in METRICS]].values\n",
    "    d[\"perf\"] = [float(v @ w_arr[p]) for v, p in zip(rz, d.position)]\n",
    "\n",
    "    # V1 팀 실력 보정 (클랜 내부)\n",
    "    pw = d.groupby(\"puuid\").game_result.mean(); d[\"p\"] = d.puuid.map(pw)\n",
    "    tsum = d.groupby([\"custom_match_id\",\"game_team\"])[\"p\"].transform(\"sum\")\n",
    "    tot  = d.groupby(\"custom_match_id\")[\"p\"].transform(\"sum\")\n",
    "    d[\"expected\"] = (0.5 + (tsum/5 - (tot-tsum)/5)).clip(0.02, 0.98)\n",
    "    d[\"surprise\"] = d.game_result - d[\"expected\"]\n",
    "\n",
    "    # 집계 + 점수\n",
    "    champ = d.groupby([\"champion_id\",\"position\"], as_index=False).agg(\n",
    "        champ_name=(\"champ_name\",\"first\"), games=(\"game_result\",\"count\"),\n",
    "        unique_users=(\"puuid\",\"nunique\"), champion_winrate=(\"game_result\",\"mean\"),\n",
    "        v1_core=(\"surprise\",\"mean\"), v2_core=(\"perf\",\"mean\"))\n",
    "    champ = champ[champ.games >= MIN_GAMES].copy()\n",
    "    if champ.empty:\n",
    "        return champ, ROLE_W, None\n",
    "    STABLE = int(champ.games.median())\n",
    "    champ[\"z1\"] = champ.groupby(\"position\")[\"v1_core\"].transform(z_pos)\n",
    "    champ[\"z2\"] = champ.groupby(\"position\")[\"v2_core\"].transform(z_pos)\n",
    "    champ[\"reliability\"] = np.minimum(champ.games / STABLE, 1.0)\n",
    "    champ[\"final\"] = (W_V1*champ.z1 + W_V2*champ.z2) * champ.reliability\n",
    "    champ[\"champion_score\"] = champ.groupby(\"position\")[\"final\"].transform(\n",
    "        lambda s: 70 + z_pos(s)*15).clip(0,100).round(1)\n",
    "    for c in [\"champion_winrate\",\"v1_core\",\"v2_core\"]:\n",
    "        champ[c] = champ[c].round(3)\n",
    "    champ = champ.sort_values([\"position\",\"champion_score\"], ascending=[True,False]).reset_index(drop=True)\n",
    "    return champ, ROLE_W, STABLE"
   ]
  },
  {
   "cell_type": "markdown",
   "id": "ab084f91",
   "metadata": {},
   "source": [
    "# 4. 클랜별 실행"
   ]
  },
  {
   "cell_type": "code",
   "execution_count": 5,
   "id": "7cf06787",
   "metadata": {
    "execution": {
     "iopub.execute_input": "2026-07-29T06:59:56.821458Z",
     "iopub.status.busy": "2026-07-29T06:59:56.820772Z",
     "iopub.status.idle": "2026-07-29T06:59:57.383050Z",
     "shell.execute_reply": "2026-07-29T06:59:57.381932Z"
    }
   },
   "outputs": [
    {
     "name": "stdout",
     "output_type": "stream",
     "text": [
      "클랜 1281251734454276106: 챔피언-라인 231개 | STABLE_GAMES=60\n",
      "클랜 936184382228693052: 챔피언-라인 118개 | STABLE_GAMES=23\n"
     ]
    }
   ],
   "source": [
    "DISPLAY = [\"champ_name\",\"champion_id\",\"position\",\"games\",\"unique_users\",\n",
    "           \"champion_winrate\",\"v1_core\",\"v2_core\",\"champion_score\"]\n",
    "results, weights = {}, {}\n",
    "for gid in TOP_CLANS:\n",
    "    champ, RW, STABLE = run_for_clan(df_all[df_all[CLAN_COL] == gid])\n",
    "    champ.insert(0, CLAN_COL, gid)\n",
    "    results[gid] = champ; weights[gid] = RW\n",
    "    print(f\"클랜 {gid}: 챔피언-라인 {len(champ)}개 | STABLE_GAMES={STABLE}\")"
   ]
  },
  {
   "cell_type": "markdown",
   "id": "05046795",
   "metadata": {},
   "source": [
    "## 4.1 첫 번째 클랜 — 라인별 순위"
   ]
  },
  {
   "cell_type": "code",
   "execution_count": 6,
   "id": "232cce06",
   "metadata": {
    "execution": {
     "iopub.execute_input": "2026-07-29T06:59:57.385172Z",
     "iopub.status.busy": "2026-07-29T06:59:57.384943Z",
     "iopub.status.idle": "2026-07-29T06:59:57.406565Z",
     "shell.execute_reply": "2026-07-29T06:59:57.405611Z"
    }
   },
   "outputs": [
    {
     "name": "stdout",
     "output_type": "stream",
     "text": [
      "CLAN 1281251734454276106\n"
     ]
    },
    {
     "data": {
      "text/html": [
       "<div>\n",
       "<style scoped>\n",
       "    .dataframe tbody tr th:only-of-type {\n",
       "        vertical-align: middle;\n",
       "    }\n",
       "\n",
       "    .dataframe tbody tr th {\n",
       "        vertical-align: top;\n",
       "    }\n",
       "\n",
       "    .dataframe thead th {\n",
       "        text-align: right;\n",
       "    }\n",
       "</style>\n",
       "<table border=\"1\" class=\"dataframe\">\n",
       "  <thead>\n",
       "    <tr style=\"text-align: right;\">\n",
       "      <th></th>\n",
       "      <th>champ_name</th>\n",
       "      <th>champion_id</th>\n",
       "      <th>position</th>\n",
       "      <th>games</th>\n",
       "      <th>unique_users</th>\n",
       "      <th>champion_winrate</th>\n",
       "      <th>v1_core</th>\n",
       "      <th>v2_core</th>\n",
       "      <th>champion_score</th>\n",
       "    </tr>\n",
       "  </thead>\n",
       "  <tbody>\n",
       "    <tr>\n",
       "      <th>0</th>\n",
       "      <td>제리</td>\n",
       "      <td>CHN_166</td>\n",
       "      <td>ADC</td>\n",
       "      <td>84</td>\n",
       "      <td>27</td>\n",
       "      <td>0.571</td>\n",
       "      <td>0.069</td>\n",
       "      <td>1.816</td>\n",
       "      <td>100.0</td>\n",
       "    </tr>\n",
       "    <tr>\n",
       "      <th>1</th>\n",
       "      <td>자야</td>\n",
       "      <td>CHN_157</td>\n",
       "      <td>ADC</td>\n",
       "      <td>110</td>\n",
       "      <td>40</td>\n",
       "      <td>0.536</td>\n",
       "      <td>0.036</td>\n",
       "      <td>1.345</td>\n",
       "      <td>92.4</td>\n",
       "    </tr>\n",
       "    <tr>\n",
       "      <th>2</th>\n",
       "      <td>코그모</td>\n",
       "      <td>CHN_68</td>\n",
       "      <td>ADC</td>\n",
       "      <td>48</td>\n",
       "      <td>8</td>\n",
       "      <td>0.562</td>\n",
       "      <td>0.055</td>\n",
       "      <td>1.316</td>\n",
       "      <td>88.6</td>\n",
       "    </tr>\n",
       "    <tr>\n",
       "      <th>3</th>\n",
       "      <td>코르키</td>\n",
       "      <td>CHN_25</td>\n",
       "      <td>ADC</td>\n",
       "      <td>94</td>\n",
       "      <td>26</td>\n",
       "      <td>0.532</td>\n",
       "      <td>0.025</td>\n",
       "      <td>1.187</td>\n",
       "      <td>85.7</td>\n",
       "    </tr>\n",
       "    <tr>\n",
       "      <th>4</th>\n",
       "      <td>스웨인</td>\n",
       "      <td>CHN_130</td>\n",
       "      <td>ADC</td>\n",
       "      <td>45</td>\n",
       "      <td>14</td>\n",
       "      <td>0.622</td>\n",
       "      <td>0.117</td>\n",
       "      <td>1.003</td>\n",
       "      <td>85.6</td>\n",
       "    </tr>\n",
       "    <tr>\n",
       "      <th>...</th>\n",
       "      <td>...</td>\n",
       "      <td>...</td>\n",
       "      <td>...</td>\n",
       "      <td>...</td>\n",
       "      <td>...</td>\n",
       "      <td>...</td>\n",
       "      <td>...</td>\n",
       "      <td>...</td>\n",
       "      <td>...</td>\n",
       "    </tr>\n",
       "    <tr>\n",
       "      <th>226</th>\n",
       "      <td>문도박사</td>\n",
       "      <td>CHN_29</td>\n",
       "      <td>TOP</td>\n",
       "      <td>48</td>\n",
       "      <td>24</td>\n",
       "      <td>0.354</td>\n",
       "      <td>-0.145</td>\n",
       "      <td>0.195</td>\n",
       "      <td>50.9</td>\n",
       "    </tr>\n",
       "    <tr>\n",
       "      <th>227</th>\n",
       "      <td>모데카이저</td>\n",
       "      <td>CHN_82</td>\n",
       "      <td>TOP</td>\n",
       "      <td>82</td>\n",
       "      <td>37</td>\n",
       "      <td>0.402</td>\n",
       "      <td>-0.094</td>\n",
       "      <td>-0.039</td>\n",
       "      <td>47.4</td>\n",
       "    </tr>\n",
       "    <tr>\n",
       "      <th>228</th>\n",
       "      <td>그라가스</td>\n",
       "      <td>CHN_40</td>\n",
       "      <td>TOP</td>\n",
       "      <td>49</td>\n",
       "      <td>26</td>\n",
       "      <td>0.367</td>\n",
       "      <td>-0.126</td>\n",
       "      <td>-0.629</td>\n",
       "      <td>40.4</td>\n",
       "    </tr>\n",
       "    <tr>\n",
       "      <th>229</th>\n",
       "      <td>세트</td>\n",
       "      <td>CHN_119</td>\n",
       "      <td>TOP</td>\n",
       "      <td>53</td>\n",
       "      <td>17</td>\n",
       "      <td>0.321</td>\n",
       "      <td>-0.164</td>\n",
       "      <td>-0.611</td>\n",
       "      <td>35.0</td>\n",
       "    </tr>\n",
       "    <tr>\n",
       "      <th>230</th>\n",
       "      <td>마오카이</td>\n",
       "      <td>CHN_79</td>\n",
       "      <td>TOP</td>\n",
       "      <td>68</td>\n",
       "      <td>16</td>\n",
       "      <td>0.412</td>\n",
       "      <td>-0.087</td>\n",
       "      <td>-1.308</td>\n",
       "      <td>26.1</td>\n",
       "    </tr>\n",
       "  </tbody>\n",
       "</table>\n",
       "<p>231 rows × 9 columns</p>\n",
       "</div>"
      ],
      "text/plain": [
       "    champ_name champion_id position  games  unique_users  champion_winrate  v1_core  v2_core  champion_score\n",
       "0           제리     CHN_166      ADC     84            27             0.571    0.069    1.816           100.0\n",
       "1           자야     CHN_157      ADC    110            40             0.536    0.036    1.345            92.4\n",
       "2          코그모      CHN_68      ADC     48             8             0.562    0.055    1.316            88.6\n",
       "3          코르키      CHN_25      ADC     94            26             0.532    0.025    1.187            85.7\n",
       "4          스웨인     CHN_130      ADC     45            14             0.622    0.117    1.003            85.6\n",
       "..         ...         ...      ...    ...           ...               ...      ...      ...             ...\n",
       "226       문도박사      CHN_29      TOP     48            24             0.354   -0.145    0.195            50.9\n",
       "227      모데카이저      CHN_82      TOP     82            37             0.402   -0.094   -0.039            47.4\n",
       "228       그라가스      CHN_40      TOP     49            26             0.367   -0.126   -0.629            40.4\n",
       "229         세트     CHN_119      TOP     53            17             0.321   -0.164   -0.611            35.0\n",
       "230       마오카이      CHN_79      TOP     68            16             0.412   -0.087   -1.308            26.1\n",
       "\n",
       "[231 rows x 9 columns]"
      ]
     },
     "execution_count": 6,
     "metadata": {},
     "output_type": "execute_result"
    }
   ],
   "source": [
    "gid = TOP_CLANS[0]\n",
    "print(\"CLAN\", gid)\n",
    "results[gid][DISPLAY]"
   ]
  },
  {
   "cell_type": "markdown",
   "id": "47004a12",
   "metadata": {},
   "source": [
    "## 4.2 두 번째 클랜 — 라인별 순위"
   ]
  },
  {
   "cell_type": "code",
   "execution_count": 7,
   "id": "e906b98c",
   "metadata": {
    "execution": {
     "iopub.execute_input": "2026-07-29T06:59:57.408502Z",
     "iopub.status.busy": "2026-07-29T06:59:57.408259Z",
     "iopub.status.idle": "2026-07-29T06:59:57.425623Z",
     "shell.execute_reply": "2026-07-29T06:59:57.424601Z"
    }
   },
   "outputs": [
    {
     "name": "stdout",
     "output_type": "stream",
     "text": [
      "CLAN 936184382228693052\n"
     ]
    },
    {
     "data": {
      "text/html": [
       "<div>\n",
       "<style scoped>\n",
       "    .dataframe tbody tr th:only-of-type {\n",
       "        vertical-align: middle;\n",
       "    }\n",
       "\n",
       "    .dataframe tbody tr th {\n",
       "        vertical-align: top;\n",
       "    }\n",
       "\n",
       "    .dataframe thead th {\n",
       "        text-align: right;\n",
       "    }\n",
       "</style>\n",
       "<table border=\"1\" class=\"dataframe\">\n",
       "  <thead>\n",
       "    <tr style=\"text-align: right;\">\n",
       "      <th></th>\n",
       "      <th>champ_name</th>\n",
       "      <th>champion_id</th>\n",
       "      <th>position</th>\n",
       "      <th>games</th>\n",
       "      <th>unique_users</th>\n",
       "      <th>champion_winrate</th>\n",
       "      <th>v1_core</th>\n",
       "      <th>v2_core</th>\n",
       "      <th>champion_score</th>\n",
       "    </tr>\n",
       "  </thead>\n",
       "  <tbody>\n",
       "    <tr>\n",
       "      <th>0</th>\n",
       "      <td>카이사</td>\n",
       "      <td>CHN_56</td>\n",
       "      <td>ADC</td>\n",
       "      <td>30</td>\n",
       "      <td>14</td>\n",
       "      <td>0.700</td>\n",
       "      <td>0.182</td>\n",
       "      <td>2.830</td>\n",
       "      <td>100.0</td>\n",
       "    </tr>\n",
       "    <tr>\n",
       "      <th>1</th>\n",
       "      <td>징크스</td>\n",
       "      <td>CHN_55</td>\n",
       "      <td>ADC</td>\n",
       "      <td>24</td>\n",
       "      <td>14</td>\n",
       "      <td>0.583</td>\n",
       "      <td>0.098</td>\n",
       "      <td>2.176</td>\n",
       "      <td>93.3</td>\n",
       "    </tr>\n",
       "    <tr>\n",
       "      <th>2</th>\n",
       "      <td>유나라</td>\n",
       "      <td>CHN_171</td>\n",
       "      <td>ADC</td>\n",
       "      <td>55</td>\n",
       "      <td>19</td>\n",
       "      <td>0.527</td>\n",
       "      <td>0.038</td>\n",
       "      <td>1.867</td>\n",
       "      <td>85.7</td>\n",
       "    </tr>\n",
       "    <tr>\n",
       "      <th>3</th>\n",
       "      <td>트리스타나</td>\n",
       "      <td>CHN_139</td>\n",
       "      <td>ADC</td>\n",
       "      <td>18</td>\n",
       "      <td>6</td>\n",
       "      <td>0.556</td>\n",
       "      <td>0.049</td>\n",
       "      <td>1.559</td>\n",
       "      <td>80.0</td>\n",
       "    </tr>\n",
       "    <tr>\n",
       "      <th>4</th>\n",
       "      <td>제리</td>\n",
       "      <td>CHN_166</td>\n",
       "      <td>ADC</td>\n",
       "      <td>24</td>\n",
       "      <td>10</td>\n",
       "      <td>0.500</td>\n",
       "      <td>-0.006</td>\n",
       "      <td>1.622</td>\n",
       "      <td>79.9</td>\n",
       "    </tr>\n",
       "    <tr>\n",
       "      <th>...</th>\n",
       "      <td>...</td>\n",
       "      <td>...</td>\n",
       "      <td>...</td>\n",
       "      <td>...</td>\n",
       "      <td>...</td>\n",
       "      <td>...</td>\n",
       "      <td>...</td>\n",
       "      <td>...</td>\n",
       "      <td>...</td>\n",
       "    </tr>\n",
       "    <tr>\n",
       "      <th>113</th>\n",
       "      <td>제이스</td>\n",
       "      <td>CHN_53</td>\n",
       "      <td>TOP</td>\n",
       "      <td>11</td>\n",
       "      <td>10</td>\n",
       "      <td>0.273</td>\n",
       "      <td>-0.228</td>\n",
       "      <td>-0.156</td>\n",
       "      <td>56.8</td>\n",
       "    </tr>\n",
       "    <tr>\n",
       "      <th>114</th>\n",
       "      <td>쉔</td>\n",
       "      <td>CHN_121</td>\n",
       "      <td>TOP</td>\n",
       "      <td>29</td>\n",
       "      <td>13</td>\n",
       "      <td>0.448</td>\n",
       "      <td>-0.033</td>\n",
       "      <td>-0.457</td>\n",
       "      <td>50.0</td>\n",
       "    </tr>\n",
       "    <tr>\n",
       "      <th>115</th>\n",
       "      <td>럼블</td>\n",
       "      <td>CHN_111</td>\n",
       "      <td>TOP</td>\n",
       "      <td>27</td>\n",
       "      <td>17</td>\n",
       "      <td>0.370</td>\n",
       "      <td>-0.120</td>\n",
       "      <td>-0.164</td>\n",
       "      <td>49.2</td>\n",
       "    </tr>\n",
       "    <tr>\n",
       "      <th>116</th>\n",
       "      <td>암베사</td>\n",
       "      <td>CHN_13</td>\n",
       "      <td>TOP</td>\n",
       "      <td>16</td>\n",
       "      <td>11</td>\n",
       "      <td>0.188</td>\n",
       "      <td>-0.269</td>\n",
       "      <td>-0.317</td>\n",
       "      <td>47.4</td>\n",
       "    </tr>\n",
       "    <tr>\n",
       "      <th>117</th>\n",
       "      <td>레넥톤</td>\n",
       "      <td>CHN_109</td>\n",
       "      <td>TOP</td>\n",
       "      <td>35</td>\n",
       "      <td>15</td>\n",
       "      <td>0.343</td>\n",
       "      <td>-0.157</td>\n",
       "      <td>-0.384</td>\n",
       "      <td>43.5</td>\n",
       "    </tr>\n",
       "  </tbody>\n",
       "</table>\n",
       "<p>118 rows × 9 columns</p>\n",
       "</div>"
      ],
      "text/plain": [
       "    champ_name champion_id position  games  unique_users  champion_winrate  v1_core  v2_core  champion_score\n",
       "0          카이사      CHN_56      ADC     30            14             0.700    0.182    2.830           100.0\n",
       "1          징크스      CHN_55      ADC     24            14             0.583    0.098    2.176            93.3\n",
       "2          유나라     CHN_171      ADC     55            19             0.527    0.038    1.867            85.7\n",
       "3        트리스타나     CHN_139      ADC     18             6             0.556    0.049    1.559            80.0\n",
       "4           제리     CHN_166      ADC     24            10             0.500   -0.006    1.622            79.9\n",
       "..         ...         ...      ...    ...           ...               ...      ...      ...             ...\n",
       "113        제이스      CHN_53      TOP     11            10             0.273   -0.228   -0.156            56.8\n",
       "114          쉔     CHN_121      TOP     29            13             0.448   -0.033   -0.457            50.0\n",
       "115         럼블     CHN_111      TOP     27            17             0.370   -0.120   -0.164            49.2\n",
       "116        암베사      CHN_13      TOP     16            11             0.188   -0.269   -0.317            47.4\n",
       "117        레넥톤     CHN_109      TOP     35            15             0.343   -0.157   -0.384            43.5\n",
       "\n",
       "[118 rows x 9 columns]"
      ]
     },
     "execution_count": 7,
     "metadata": {},
     "output_type": "execute_result"
    }
   ],
   "source": [
    "gid = TOP_CLANS[1]\n",
    "print(\"CLAN\", gid)\n",
    "results[gid][DISPLAY]"
   ]
  },
  {
   "cell_type": "markdown",
   "id": "63dabbbf",
   "metadata": {},
   "source": [
    "## 4.3 클랜 성향 비교 (라인별 상위 3)\n",
    "\n",
    "같은 라인이라도 클랜마다 강한 챔피언이 다르다."
   ]
  },
  {
   "cell_type": "code",
   "execution_count": 8,
   "id": "1c42142a",
   "metadata": {
    "execution": {
     "iopub.execute_input": "2026-07-29T06:59:57.427256Z",
     "iopub.status.busy": "2026-07-29T06:59:57.427072Z",
     "iopub.status.idle": "2026-07-29T06:59:57.448983Z",
     "shell.execute_reply": "2026-07-29T06:59:57.447881Z"
    }
   },
   "outputs": [
    {
     "name": "stdout",
     "output_type": "stream",
     "text": [
      "[TOP ]\n",
      "    1281251734454276106: 가렌(100.0) / 갱플랭크(100.0) / 올라프(100.0)\n",
      "    936184382228693052: 요네(100.0) / 카밀(100.0) / 이렐리아(87.4)\n",
      "[JUG ]\n",
      "    1281251734454276106: 제드(100.0) / 자헨(100.0) / 그레이브즈(97.3)\n",
      "    936184382228693052: 제드(100.0) / 그레이브즈(100.0) / 제이스(97.2)\n",
      "[MID ]\n",
      "    1281251734454276106: 제라스(100.0) / 카사딘(100.0) / 트리스타나(92.7)\n",
      "    936184382228693052: 야스오(100.0) / 제라스(91.2) / 이렐리아(87.2)\n",
      "[ADC ]\n",
      "    1281251734454276106: 제리(100.0) / 자야(92.4) / 코그모(88.6)\n",
      "    936184382228693052: 카이사(100.0) / 징크스(93.3) / 유나라(85.7)\n",
      "[SUP ]\n",
      "    1281251734454276106: 이즈리얼(100.0) / 엘리스(91.9) / 멜(90.5)\n",
      "    936184382228693052: 세라핀(92.8) / 제라스(92.2) / 렐(89.9)\n"
     ]
    }
   ],
   "source": [
    "for pos in POSITION_ORDER:\n",
    "    line = [pos.ljust(4)]\n",
    "    for gid in TOP_CLANS:\n",
    "        t = results[gid][results[gid].position == pos].head(3)\n",
    "        line.append(\" / \".join(f\"{r.champ_name}({r.champion_score})\" for _, r in t.iterrows()))\n",
    "    print(f\"[{line[0]}]\")\n",
    "    for gid, txt in zip(TOP_CLANS, line[1:]):\n",
    "        print(f\"    {gid}: {txt}\")"
   ]
  },
  {
   "cell_type": "markdown",
   "id": "ea486fad",
   "metadata": {},
   "source": [
    "## 4.4 클랜 성향 — 가중치 차이 (예: MID)\n",
    "\n",
    "데이터 기반 가중치가 클랜 내부에서 학습되므로, 클랜의 성향이 다르면 가중치도 달라진다."
   ]
  },
  {
   "cell_type": "code",
   "execution_count": 9,
   "id": "8be49702",
   "metadata": {
    "execution": {
     "iopub.execute_input": "2026-07-29T06:59:57.450816Z",
     "iopub.status.busy": "2026-07-29T06:59:57.450609Z",
     "iopub.status.idle": "2026-07-29T06:59:57.461414Z",
     "shell.execute_reply": "2026-07-29T06:59:57.460446Z"
    }
   },
   "outputs": [
    {
     "data": {
      "text/html": [
       "<div>\n",
       "<style scoped>\n",
       "    .dataframe tbody tr th:only-of-type {\n",
       "        vertical-align: middle;\n",
       "    }\n",
       "\n",
       "    .dataframe tbody tr th {\n",
       "        vertical-align: top;\n",
       "    }\n",
       "\n",
       "    .dataframe thead th {\n",
       "        text-align: right;\n",
       "    }\n",
       "</style>\n",
       "<table border=\"1\" class=\"dataframe\">\n",
       "  <thead>\n",
       "    <tr style=\"text-align: right;\">\n",
       "      <th></th>\n",
       "      <th>clan_1281251734454276106</th>\n",
       "      <th>clan_936184382228693052</th>\n",
       "    </tr>\n",
       "  </thead>\n",
       "  <tbody>\n",
       "    <tr>\n",
       "      <th>dpm</th>\n",
       "      <td>0.39</td>\n",
       "      <td>0.39</td>\n",
       "    </tr>\n",
       "    <tr>\n",
       "      <th>kda</th>\n",
       "      <td>0.81</td>\n",
       "      <td>0.81</td>\n",
       "    </tr>\n",
       "    <tr>\n",
       "      <th>damage_dealt_per_death</th>\n",
       "      <td>0.39</td>\n",
       "      <td>0.39</td>\n",
       "    </tr>\n",
       "    <tr>\n",
       "      <th>gold_per_min</th>\n",
       "      <td>0.39</td>\n",
       "      <td>0.39</td>\n",
       "    </tr>\n",
       "    <tr>\n",
       "      <th>cs_per_min</th>\n",
       "      <td>0.25</td>\n",
       "      <td>0.25</td>\n",
       "    </tr>\n",
       "    <tr>\n",
       "      <th>exp_per_min</th>\n",
       "      <td>0.72</td>\n",
       "      <td>0.78</td>\n",
       "    </tr>\n",
       "    <tr>\n",
       "      <th>lane_gold_diff</th>\n",
       "      <td>0.63</td>\n",
       "      <td>0.72</td>\n",
       "    </tr>\n",
       "    <tr>\n",
       "      <th>damage_to_objectives</th>\n",
       "      <td>0.42</td>\n",
       "      <td>0.53</td>\n",
       "    </tr>\n",
       "    <tr>\n",
       "      <th>takedowns_before_15min</th>\n",
       "      <td>0.36</td>\n",
       "      <td>0.36</td>\n",
       "    </tr>\n",
       "    <tr>\n",
       "      <th>dead_time_pct</th>\n",
       "      <td>0.40</td>\n",
       "      <td>0.42</td>\n",
       "    </tr>\n",
       "    <tr>\n",
       "      <th>vision_score</th>\n",
       "      <td>0.17</td>\n",
       "      <td>0.17</td>\n",
       "    </tr>\n",
       "  </tbody>\n",
       "</table>\n",
       "</div>"
      ],
      "text/plain": [
       "                        clan_1281251734454276106  clan_936184382228693052\n",
       "dpm                                         0.39                     0.39\n",
       "kda                                         0.81                     0.81\n",
       "damage_dealt_per_death                      0.39                     0.39\n",
       "gold_per_min                                0.39                     0.39\n",
       "cs_per_min                                  0.25                     0.25\n",
       "exp_per_min                                 0.72                     0.78\n",
       "lane_gold_diff                              0.63                     0.72\n",
       "damage_to_objectives                        0.42                     0.53\n",
       "takedowns_before_15min                      0.36                     0.36\n",
       "dead_time_pct                               0.40                     0.42\n",
       "vision_score                                0.17                     0.17"
      ]
     },
     "execution_count": 9,
     "metadata": {},
     "output_type": "execute_result"
    }
   ],
   "source": [
    "mid_cmp = pd.DataFrame({gid: weights[gid][\"MID\"] for gid in TOP_CLANS}).round(2)\n",
    "mid_cmp.columns = [f\"clan_{g}\" for g in TOP_CLANS]\n",
    "mid_cmp"
   ]
  },
  {
   "cell_type": "markdown",
   "id": "b5d6db30",
   "metadata": {},
   "source": [
    "# 5. 저장"
   ]
  },
  {
   "cell_type": "code",
   "execution_count": 10,
   "id": "1b598356",
   "metadata": {
    "execution": {
     "iopub.execute_input": "2026-07-29T06:59:57.463238Z",
     "iopub.status.busy": "2026-07-29T06:59:57.462989Z",
     "iopub.status.idle": "2026-07-29T06:59:57.481384Z",
     "shell.execute_reply": "2026-07-29T06:59:57.480297Z"
    }
   },
   "outputs": [
    {
     "name": "stdout",
     "output_type": "stream",
     "text": [
      "저장 완료: ['champion_score_clan_1281251734454276106.csv', 'champion_score_clan_936184382228693052.csv'] + champion_score_by_clan.csv\n"
     ]
    }
   ],
   "source": [
    "# 저장 컬럼: champ_name 으로 시작\n",
    "SAVE_COLS = [\"champ_name\", CLAN_COL, \"champion_id\", \"position\", \"games\",\n",
    "             \"unique_users\", \"champion_winrate\", \"v1_core\", \"v2_core\", \"champion_score\"]\n",
    "\n",
    "# 클랜별 개별 저장\n",
    "for gid in TOP_CLANS:\n",
    "    results[gid][SAVE_COLS].to_csv(\n",
    "        f\"champion_score_clan_{gid}.csv\", index=False, encoding=\"utf-8-sig\")\n",
    "\n",
    "# 통합본 (웹 업로드용) — 클랜 컬럼 포함\n",
    "combined = pd.concat([results[gid][SAVE_COLS] for gid in TOP_CLANS], ignore_index=True)\n",
    "combined.to_csv(\"champion_score_by_clan.csv\", index=False, encoding=\"utf-8-sig\")\n",
    "print(\"저장 완료:\", [f\"champion_score_clan_{g}.csv\" for g in TOP_CLANS], \"+ champion_score_by_clan.csv\")"
   ]
  },
  {
   "cell_type": "markdown",
   "id": "3056e295",
   "metadata": {},
   "source": [
    "# 6. 참고\n",
    "\n",
    "- `TOP_N_CLANS` 를 늘리면 더 많은 클랜을 자동 포함(데이터 순).\n",
    "- 클랜별 표본이 작을수록 `MIN_GAMES` 를 낮추거나(예: 5) 결과 해석에 주의.\n",
    "- 표본이 20행 미만인 라인은 데이터 가중치 대신 전문가값만 사용(과적합 방지).\n",
    "- `champion_score` 는 **클랜 내부·라인 내부 상대 순위**다.\n"
   ]
  }
 ],
 "metadata": {
  "kernelspec": {
   "display_name": "Python 3",
   "language": "python",
   "name": "python3"
  },
  "language_info": {
   "codemirror_mode": {
    "name": "ipython",
    "version": 3
   },
   "file_extension": ".py",
   "mimetype": "text/x-python",
   "name": "python",
   "nbconvert_exporter": "python",
   "pygments_lexer": "ipython3",
   "version": "3.12.3"
  }
 },
 "nbformat": 4,
 "nbformat_minor": 5
}
