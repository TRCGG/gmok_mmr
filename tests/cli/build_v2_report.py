"""실데이터로 MMR v2 파이프라인을 돌려 라인별 탭 HTML 리포트를 생성한다.

DB에서 가져온 CSV(data/mmr_participant_metric_*.csv)를 입력으로 가정한다.
운영 경로가 아니라 로컬 검증/리포트용. 출력은 output/ (gitignore).

실행:
    PYTHONPATH=src python tests/cli/build_v2_report.py [csv_path] [out_html]
"""

from __future__ import annotations

import sys
from pathlib import Path

import pandas as pd

ROOT = Path(__file__).resolve().parents[2]
for _p in (ROOT / "src", ROOT / "tests"):
    if str(_p) not in sys.path:
        sys.path.insert(0, str(_p))

from mmr.serving.service import build_base_feature_dataframe
from mmr.silver.performance import (
    _compute_raw_perf,
    apply_performance_features,
    derive_blowout_baseline,
    derive_performance_baseline,
)
from mmr.gold.mmr import DEFAULT_MMR_SETTINGS, update_mmr_elo

POS = ["TOP", "JUNGLE", "MIDDLE", "BOTTOM", "UTILITY"]
POS_KR = {"TOP": "탑", "JUNGLE": "정글", "MIDDLE": "미드", "BOTTOM": "원딜", "UTILITY": "서폿"}


def _build_main_resolver(gm_path: Path):
    """guild_member에서 account(player_code) → 메인 account 해석기를 만든다.

    is_main=False & main_account 존재 시 부계정으로 보고 메인으로 롤업(전이적).
    """
    if not gm_path.exists():
        return lambda pc: pc
    gm = pd.read_csv(gm_path)
    sub = gm[(~gm["is_main"].astype(bool)) & gm["main_account"].notna()]
    parent = dict(zip(sub["account"].astype(str), sub["main_account"].astype(str)))

    def resolve(pc: str) -> str:
        seen: set[str] = set()
        while pc in parent and pc not in seen:
            seen.add(pc)
            pc = parent[pc]
        return pc

    return resolve


def load_merged_raw(csv_path: str, gm_path: Path) -> tuple[pd.DataFrame, int, int]:
    """raw를 읽고 puuid를 '메인 player_code' 식별자로 치환(계정 통합)한다.

    반환: (raw, 부계정_병합_puuid수, 식별자중복으로_드롭된_경기수)
    """
    raw = pd.read_csv(csv_path)
    raw["played_date"] = raw["played_date"].astype(str)

    p2c = raw.drop_duplicates("puuid").set_index("puuid")["player_code"].astype(str).to_dict()
    resolve = _build_main_resolver(gm_path)
    identity = {u: resolve(p2c.get(u, u)) for u in p2c}
    # 병합된 계정 수 = (puuid 수) − (최종 메인 식별자 수). participant의 player_code가 이미
    # 부계정을 메인으로 해소해두므로 멀티계정 puuid가 한 메인으로 합쳐진다.
    n_merged = len(p2c) - len(set(identity.values()))

    raw["puuid"] = raw["puuid"].map(lambda u: identity.get(u, u))

    # 한 경기에 같은 식별자가 2번 들어오면(같은 사람이 본/부계정으로 동시 출전 등) 구조가
    # 깨지므로 해당 경기를 제외한다.
    dup = raw.groupby("custom_match_id")["puuid"].apply(lambda s: bool(s.duplicated().any()))
    bad = dup[dup].index.tolist()
    if bad:
        raw = raw[~raw["custom_match_id"].isin(bad)].copy()
    return raw, n_merged, len(bad)


def run(csv_path: str, out_html: str, gm_path: str | None = None) -> None:
    gmp = Path(gm_path) if gm_path else (ROOT / "data" / "guild_member_202606191023.csv")
    raw, n_merged, n_dup_drop = load_merged_raw(csv_path, gmp)
    n_raw_matches = raw["custom_match_id"].nunique()

    feat = build_base_feature_dataframe(raw)
    pb = derive_performance_baseline(feat)
    bb = derive_blowout_baseline(feat)
    feat = apply_performance_features(feat, pb, bb)
    raw_perf = _compute_raw_perf(feat, pb.robust_params)

    updated, summary = update_mmr_elo(feat)

    # --- P1(포지션별 재표준화) 시뮬레이션 ---
    p1 = raw_perf.copy()
    for pos, idx in feat.groupby("position").groups.items():
        s = raw_perf.loc[idx]
        sd = s.std(ddof=0) or 1.0
        p1.loc[idx] = ((s - s.mean()) / sd).clip(-2.5, 2.5)
    feat_p1 = feat.copy()
    feat_p1["perf_z"] = p1
    _, summary_p1 = update_mmr_elo(feat_p1)

    cut = DEFAULT_MMR_SETTINGS.cut
    ranked = summary[summary["is_ranked"]]

    # ---------- 표 빌드 ----------
    # 전체 랭킹
    overall = ranked.sort_values("total_mmr", ascending=False).reset_index(drop=True)
    overall.insert(0, "순위", overall.index + 1)
    overall["main_position"] = overall["main_position"].map(lambda p: POS_KR.get(p, p))
    overall_tbl = overall[[
        "순위", "puuid", "total_mmr", "total_games", "overall_winrate", "main_position",
    ]].rename(columns={
        "puuid": "player_code", "total_mmr": "종합MMR", "total_games": "경기수",
        "overall_winrate": "승률%", "main_position": "주포지션",
    })

    # 포지션 균형 표
    bal_rows = []
    for p in POS:
        v = ranked[f"{p}_mmr"].dropna()
        pz = feat[feat["position"] == p]["perf_z"]
        vp1 = summary_p1[summary_p1["is_ranked"]][f"{p}_mmr"].dropna()
        bal_rows.append({
            "포지션": POS_KR[p], "정식인원": len(v),
            "평균MMR(전역)": round(v.mean(), 1),
            "perf_z평균": round(pz.mean(), 3),
            "평균MMR(P1)": round(vp1.mean(), 1),
        })
    bal_tbl = pd.DataFrame(bal_rows)

    # 라인별 랭킹(해당 포지션 경기 보유자, pos_mmr 내림차순)
    pos_last = (
        updated.sort_values(["played_date", "custom_match_id"])
        .groupby(["puuid", "position"], as_index=False).tail(1)
        [["puuid", "position", "pos_cumulative_mmr"]]
    )
    pos_stats = updated.groupby(["puuid", "position"], as_index=False).agg(
        경기수=("game_result", "count"), 승=("game_result", "sum"))
    pos_stats["승률%"] = (pos_stats["승"] / pos_stats["경기수"] * 100).round(2)
    pos_merged = pos_last.merge(pos_stats, on=["puuid", "position"])

    lane_tables = {}
    for p in POS:
        d = pos_merged[pos_merged["position"] == p].sort_values(
            "pos_cumulative_mmr", ascending=False).reset_index(drop=True)
        d.insert(0, "순위", d.index + 1)
        d["정식"] = d["경기수"] >= cut
        lane_tables[p] = d[["순위", "puuid", "pos_cumulative_mmr", "경기수", "승률%", "정식"]].rename(
            columns={"puuid": "player_code", "pos_cumulative_mmr": "포지션MMR"})

    # 검증 지표
    def lane_corr(summ):
        lane = feat.groupby("puuid")["lane_gold_diff"].mean()
        m = summ.set_index("puuid")["total_mmr"]
        j = pd.concat([lane, m], axis=1).dropna()
        j = j[summ.set_index("puuid")["is_ranked"].reindex(j.index).fillna(False)]
        return j["lane_gold_diff"].corr(j["total_mmr"])

    meta = {
        "행": len(feat), "경기": feat["custom_match_id"].nunique(),
        "부계정병합": n_merged, "중복드롭": n_dup_drop,
        "무효드롭": n_raw_matches - feat["custom_match_id"].nunique(),
        "유저(메인)": summary["puuid"].nunique(), "정식": int(summary["is_ranked"].sum()),
        "배치중": int((~summary["is_ranked"]).sum()),
        "MMR최소": int(summary["total_mmr"].min()), "MMR최대": int(summary["total_mmr"].max()),
        "MMR평균": round(summary["total_mmr"].mean(), 1),
        "상관_전역": round(lane_corr(summary), 3), "상관_P1": round(lane_corr(summary_p1), 3),
    }
    gap_g = bal_tbl["평균MMR(전역)"].max() - bal_tbl["평균MMR(전역)"].min()
    gap_p1 = bal_tbl["평균MMR(P1)"].max() - bal_tbl["평균MMR(P1)"].min()

    html = _render(meta, overall_tbl, bal_tbl, lane_tables, gap_g, gap_p1, cut)
    Path(out_html).parent.mkdir(parents=True, exist_ok=True)
    Path(out_html).write_text(html, encoding="utf-8")
    print(f"리포트 생성: {out_html}  (메인유저 {meta['유저(메인)']}명, 정식 {meta['정식']} / "
          f"배치중 {meta['배치중']}, 부계정병합 {n_merged}, 중복드롭 {n_dup_drop})")


def _tbl(df: pd.DataFrame) -> str:
    return df.to_html(index=False, border=0, classes="t", justify="center")


def _render(meta, overall, bal, lanes, gap_g, gap_p1, cut) -> str:
    cards = "".join(
        f'<div class="card"><div class="k">{k}</div><div class="v">{v}</div></div>'
        for k, v in meta.items()
    )
    tabs = [("OVERALL", "📊 전체")] + [(p, f"{POS_KR[p]} {p}") for p in POS]
    btns = "".join(
        f'<button id="btn-{tid}" class="tabbtn{" active" if i==0 else ""}" '
        f'onclick="showTab(\'{tid}\')">{label}</button>'
        for i, (tid, label) in enumerate(tabs)
    )

    overall_div = f"""
      <div class="cards">{cards}</div>
      <h3>라인전 검증 — 라인 골드차 vs 종합 MMR 상관 (산식문서 ≈0.78)</h3>
      <p class="big">전역 재표준화 <b>{meta['상관_전역']}</b> &nbsp;|&nbsp; P1(포지션별) <b>{meta['상관_P1']}</b></p>
      <h3>포지션 균형 + P1(포지션별 정규화) 비교</h3>
      {_tbl(bal)}
      <p class="note">포지션 평균 MMR 격차(max−min): 전역 <b>{gap_g:.1f}</b> → P1 <b>{gap_p1:.1f}</b>.
      전역 재표준화는 서폿 지표의 우편향 때문에 서폿 perf_z 평균이 +로 떠 평균 MMR이 약간 높다.
      P1은 포지션별로 0 센터링해 격차를 줄이되 라인전 상관은 거의 유지.</p>
      <h3>종합 랭킹 (정식 ≥{cut}판)</h3>
      {_tbl(overall)}
    """

    lane_divs = ""
    for i, p in enumerate(POS):
        lane_divs += f"""
        <div id="{p}" class="tab" style="display:none">
          <h3>{POS_KR[p]} ({p}) 라인 랭킹 — 포지션 MMR 내림차순</h3>
          <p class="note">해당 포지션 경기 보유자 전원. '정식'=해당 포지션 {cut}판 이상.</p>
          {_tbl(lanes[p])}
        </div>"""

    return f"""<!doctype html><html lang="ko"><head><meta charset="utf-8">
<title>MMR v2 리포트</title>
<style>
 body{{font-family:'Segoe UI',Malgun Gothic,sans-serif;margin:0;background:#0f1420;color:#e6e9ef}}
 header{{padding:18px 24px;background:#161c2c;border-bottom:1px solid #2a3550}}
 h1{{margin:0;font-size:20px}} .sub{{color:#8b97b3;font-size:13px;margin-top:4px}}
 .tabs{{display:flex;gap:4px;padding:10px 24px 0;background:#161c2c;flex-wrap:wrap}}
 .tabbtn{{background:#222b42;color:#c3cce0;border:0;padding:9px 16px;border-radius:8px 8px 0 0;cursor:pointer;font-size:14px}}
 .tabbtn.active{{background:#3b5bd6;color:#fff;font-weight:600}}
 .wrap{{padding:20px 24px}}
 .cards{{display:flex;flex-wrap:wrap;gap:10px;margin-bottom:8px}}
 .card{{background:#1b2236;border:1px solid #2a3550;border-radius:10px;padding:10px 14px;min-width:84px}}
 .card .k{{color:#8b97b3;font-size:11px}} .card .v{{font-size:18px;font-weight:700;margin-top:2px}}
 h3{{margin:22px 0 8px;font-size:15px;color:#aeb9d6}}
 .big{{font-size:15px}} .note{{color:#8b97b3;font-size:12.5px;line-height:1.5}}
 table.t{{border-collapse:collapse;width:100%;font-size:13px;background:#141a29;border-radius:8px;overflow:hidden}}
 table.t th{{background:#243049;padding:8px 10px;text-align:center;position:sticky;top:0}}
 table.t td{{padding:6px 10px;text-align:center;border-top:1px solid #222b42}}
 table.t tr:nth-child(even) td{{background:#171e2e}}
 table.t tr:hover td{{background:#202b44}}
</style></head><body>
<header><h1>🎯 MMR 산식 v2 — 실데이터 리포트</h1>
<div class="sub">팀 평균 Elo + robust-z 퍼포먼스 + 승부격차 · 입력 mmr_participant_metric</div></header>
<div class="tabs">{btns}</div>
<div class="wrap">
  <div id="OVERALL" class="tab">{overall_div}</div>
  {lane_divs}
</div>
<script>
 function showTab(id){{
   document.querySelectorAll('.tab').forEach(t=>t.style.display='none');
   document.querySelectorAll('.tabbtn').forEach(b=>b.classList.remove('active'));
   document.getElementById(id).style.display='block';
   document.getElementById('btn-'+id).classList.add('active');
 }}
</script></body></html>"""


if __name__ == "__main__":
    csv = sys.argv[1] if len(sys.argv) > 1 else "data/mmr_participant_metric_202606191426.csv"
    out = sys.argv[2] if len(sys.argv) > 2 else "output/mmr_v2_report.html"
    run(csv, out)
