"""생활 쾌적도 점수 산출 (가중치 공식 방식)

입력 : data/clean/{air_quality,noise,temperature}_clean.csv (보정 파일이 있으면 *_imputed.csv 우선)
출력 : reports/comfort_score/
"""
from pathlib import Path
import json
import numpy as np
import pandas as pd

BASE_DIR = Path(__file__).resolve().parent
CLEAN_DIR = BASE_DIR / "data" / "clean"
OUT_DIR = BASE_DIR / "reports" / "comfort_score"

KEY = ["sigungu_code", "year_month"]
NAME = "sigungu_name"
TRACE_COLS = ["original_date", "original_region", "original_sigungu_name", "source_excel_row"]

COLS = {"temperature": "temp_avg_c", "pm25": "pm25", "pm10": "pm10",
        "noise": "noise_avg_db", "ozone": "o3"}
IND = list(COLS)

# ------------------------------------------------------------------
# 설정 (지표설계안 xlsx 기준)
# ------------------------------------------------------------------
# 합이 100이 아니어도 됩니다. 값이 0인 지표는 점수에서 제외하고 나머지를 자동 정규화합니다.
WEIGHT_SETS = {
    # '지표 설계' 시트. 습도(11.5)는 데이터 없음, 오존은 설계안에 없어 제외
    "design_sheet1": {"temperature": 26.2, "pm25": 28.7, "pm10": 17, "noise": 28.0, "ozone": 0},
    # '가중치 검토' 시트 초기 제안. 습도(10)와 공원면적(15)은 제외
    "review_sheet3": {"temperature": 20, "pm25": 25, "pm10": 15, "noise": 15, "ozone": 0},
}
WEIGHT_SET = "design_sheet1"

# "relative": 월별 자치구 간 상대 순위(0~100)로 환산 → 가중치가 순위에 그대로 반영
# "absolute": 기준값 기반 절대 점수 → 월 간 비교 가능, 지표별 변별력 차이가 남음
SCORE_MODE = "relative"

# 직접 채워 넣은 기온 추정값 (지역코드, YYYY-MM)
ESTIMATED_TEMP = {
    ("11215", "2024-05"),   # 광진구
    ("11530", "2024-10"),   # 구로구
    ("11440", "2024-09"),   # 마포구
    ("11410", "2026-08"),   # 서대문구
    ("11410", "2026-09"),
    ("11170", "2025-02"),   # 용산구
    ("11170", "2025-03"),
    ("11170", "2025-10"),
}

# 기온: 계절별 목표 범위(°C). 설계안에서 확정되기 전 임시 가정값입니다.
SEASON_OF = {12: "winter", 1: "winter", 2: "winter", 3: "spring", 4: "spring", 5: "spring",
             6: "summer", 7: "summer", 8: "summer", 9: "fall", 10: "fall", 11: "fall"}
TEMP_TARGET = {"winter": (0, 8), "spring": (10, 18), "summer": (22, 27), "fall": (12, 20)}

# 절대 점수 기준 (값, 점수). 기온은 목표 범위에서 벗어난 정도(°C)
ABS_POINTS = {
    "temperature": [(0, 100), (3, 80), (8, 50), (15, 20), (25, 0)],
    "pm25": [(0, 100), (15, 75), (35, 40), (75, 10), (150, 0)],
    "pm10": [(0, 100), (30, 75), (80, 40), (150, 10), (250, 0)],
    "noise": [(40, 100), (45, 85), (55, 60), (65, 30), (75, 0)],
    "ozone": [(0, 100), (0.03, 75), (0.09, 40), (0.15, 10), (0.20, 0)],
}
GRADE_BINS = [0, 50, 65, 80, 100.01]
GRADE_LABELS = ["나쁨", "보통", "양호", "쾌적"]


# ------------------------------------------------------------------
# 입력
# ------------------------------------------------------------------
def pick(stem):
    """보정 파일(*_imputed)이 있으면 사용. 정제 파일보다 오래됐으면 정제 파일을 사용."""
    clean = CLEAN_DIR / f"{stem}_clean.csv"
    imputed = CLEAN_DIR / f"{stem}_imputed.csv"
    if imputed.exists():
        if clean.exists() and imputed.stat().st_mtime < clean.stat().st_mtime:
            print(f"⚠ {imputed.name}이 {clean.name}보다 오래되어 {clean.name}을 사용합니다. "
                  f"(보정 스크립트를 다시 실행하세요)")
            return clean
        return imputed
    if clean.exists():
        return clean
    raise FileNotFoundError(f"{clean} 파일이 없습니다. fix_data_quality.py를 먼저 실행하세요.")


def read(path):
    df = pd.read_csv(path, encoding="utf-8-sig", dtype={"sigungu_code": "string"})
    df = df.drop(columns=TRACE_COLS, errors="ignore")
    return df.rename(columns=lambda c: c.replace("_dB", "_db"))


def load():
    paths = {s: pick(s) for s in ("air_quality", "noise", "temperature")}
    air, noise, temp = (read(paths[s]) for s in ("air_quality", "noise", "temperature"))
    print("사용 파일:", ", ".join(p.name for p in paths.values()))
    if NAME not in air.columns:
        raise KeyError(f"air_quality 파일에 '{NAME}' 컬럼이 없습니다. 현재 컬럼: {list(air.columns)}")

    df = air.merge(noise.drop(columns=NAME, errors="ignore"), on=KEY, how="inner", validate="one_to_one")
    df = df.merge(temp.drop(columns=NAME, errors="ignore"), on=KEY, how="inner", validate="one_to_one")
    print(f"병합: 대기 {len(air)} / 소음 {len(noise)} / 기온 {len(temp)} → 결과 {len(df)}행")
    if len(df) < min(len(air), len(noise), len(temp)):
        print("⚠ 병합 후 행이 줄었습니다. check_coverage.py로 지역·월 누락을 확인하세요.")

    absent = [c for c in COLS.values() if c not in df.columns]
    if absent:
        raise KeyError(f"지표 컬럼이 없습니다: {absent}\n현재 컬럼: {list(df.columns)}")
    return df


# ------------------------------------------------------------------
# 점수 계산
# ------------------------------------------------------------------
def normalize(w):
    total = sum(w.get(k, 0) for k in IND)
    return {k: w.get(k, 0) / total for k in IND}


def temp_deviation(df):
    """계절별 목표 범위에서 벗어난 정도(°C). 범위 안이면 0."""
    month = pd.to_datetime(df["year_month"].astype(str).str[:7] + "-01").dt.month
    season = month.map(SEASON_OF)
    lo = season.map(lambda s: TEMP_TARGET[s][0])
    hi = season.map(lambda s: TEMP_TARGET[s][1])
    t = pd.to_numeric(df[COLS["temperature"]], errors="coerce")
    return pd.concat([lo - t, t - hi], axis=1).max(axis=1).clip(lower=0)


def interp(series, points):
    xs, ys = zip(*points)
    num = pd.to_numeric(series, errors="coerce")
    return pd.Series(np.interp(num, xs, ys), index=series.index).where(num.notna())


def abs_scores(df):
    s = pd.DataFrame({"temperature": interp(temp_deviation(df), ABS_POINTS["temperature"])})
    for k in IND[1:]:
        s[k] = interp(df[COLS[k]], ABS_POINTS[k])
    return s


def rel_scores(df):
    
    """월별로 자치구 간 순위를 0~100으로 환산 (높을수록 쾌적)."""
    better = pd.DataFrame({"temperature": -temp_deviation(df)})
    for k in IND[1:]:
        better[k] = -pd.to_numeric(df[COLS[k]], errors="coerce")
    g = better.groupby(df["year_month"])
    rank = g.rank(method="average")
    n = g.transform("count")
    return (rank - 1) / (n - 1).where(n > 1) * 100

def period_rel_scores(df, mask=None):
    """평가기간 평균을 자치구별로 먼저 구한 뒤 자치구 간 순위(0~100)로 환산합니다.
    반환: (상대 점수 [index=sigungu_code], 자치구별 원단위 평균)"""
    better = pd.DataFrame({"temperature": -temp_deviation(df)})
    for k in IND[1:]:
        better[k] = -pd.to_numeric(df[COLS[k]], errors="coerce")
    if mask is not None:
        better = better.mask(mask)
    region_mean = better.groupby(df["sigungu_code"]).mean()
    n = region_mean.count()
    score = (region_mean.rank(method="average") - 1) / (n - 1) * 100
    return score, -region_mean

def weighted(sub, weights):
    """가중 평균. 비어 있는 지표는 제외하고 나머지 가중치를 재조정."""
    w = pd.Series(weights, dtype=float).reindex(sub.columns).fillna(0)
    num = (sub.fillna(0) * w).sum(axis=1)
    den = (sub.notna() * w).sum(axis=1)
    return num / den.where(den > 0)


def influence(region_sub, weights):
    """지표별 실효 영향(%): 가중치 × 공분산(지표 점수, 총점) / 총점 분산. 합계 100%."""
    cols = [k for k in IND if weights.get(k, 0) > 0]
    w = pd.Series(normalize(weights))[cols]
    total = (region_sub[cols] * w).sum(axis=1)
    return pd.Series({k: w[k] * region_sub[k].cov(total) / total.var() for k in cols}) * 100


def save_contract_json(df, out_path):
    """공통 계약 형식으로 최신 평가월의 자치구별 점수를 JSON으로 저장합니다."""
    months = pd.to_datetime(df["year_month"], errors="coerce")
    latest = months.max()
    if pd.isna(latest):
        raise ValueError("평가기준월을 정할 수 없습니다: year_month 값이 없습니다.")

    start_month = months.min().strftime("%Y-%m")
    latest_month = latest.strftime("%Y-%m")
    source_period = f"{start_month}~{latest_month}"
    latest_rows = df.loc[months.dt.strftime("%Y-%m") == latest_month].copy()

    records = []
    for _, row in latest_rows.iterrows():
        score = pd.to_numeric(row["comfort_score"], errors="coerce")
        complete = pd.notna(score)
        reasons = [] if complete else ["점수 계산에 필요한 지표가 없습니다."]
        records.append({
            "행정구코드": str(row["sigungu_code"]),
            "행정구명": str(row[NAME]) if pd.notna(row[NAME]) else "",
            "평가분야": "생활쾌적도",
            "평가기준월": latest_month,
            "사용자료_기준기간": source_period,
            "점수": round(float(score), 1) if complete else None,
            "계산상태": "완료" if complete else "불가",
            "계산불가사유": reasons,
        })

    out_path.parent.mkdir(parents=True, exist_ok=True)
    with out_path.open("w", encoding="utf-8") as f:
        json.dump(records, f, ensure_ascii=False, indent=2, allow_nan=False)


def main():
    OUT_DIR.mkdir(parents=True, exist_ok=True)
    df = load()

    W_raw = WEIGHT_SETS[WEIGHT_SET]
    W = normalize(W_raw)
    active = [k for k in IND if W[k] > 0]
    print(f"\n가중치 세트: {WEIGHT_SET} | 점수 방식: {SCORE_MODE}")
    print("  정규화된 가중치(%):", {k: round(W[k] * 100, 1) for k in active})

    # 추정값 표시
    ym = df["year_month"].astype(str).str[:7]
    df["temp_imputed"] = [(c, m) in ESTIMATED_TEMP for c, m in zip(df["sigungu_code"], ym)]
    est = pd.DataFrame(False, index=df.index, columns=IND)
    est["temperature"] = df["temp_imputed"]
    for k in ("pm25", "pm10"):
        if f"{k}_imputed" in df.columns:
            est[k] = df[f"{k}_imputed"].fillna(False).astype(bool)
    df["has_imputed"] = est.any(axis=1)

    # 점수 (절대/상대를 모두 계산하고 SCORE_MODE에 맞는 것을 최종 점수로 사용)
    s_abs, s_rel = abs_scores(df), rel_scores(df)
    df["score_abs"] = weighted(s_abs, W).round(2)
    df["score_rel"] = weighted(s_rel, W).round(2)
    sub_sel = s_rel if SCORE_MODE == "relative" else s_abs
    df["comfort_score"] = df["score_rel" if SCORE_MODE == "relative" else "score_abs"]
    df["grade_abs"] = pd.cut(df["score_abs"], GRADE_BINS, labels=GRADE_LABELS, right=False)
    df["n_indicators"] = sub_sel[active].notna().sum(axis=1)

    front = ["sigungu_code", NAME, "year_month", "comfort_score", "score_abs", "score_rel",
             "grade_abs", "n_indicators", "has_imputed", "temp_imputed"]
    sub_out = pd.concat([s_abs.round(2).add_prefix("abs_"), s_rel.round(2).add_prefix("rel_")], axis=1)
    out = pd.concat([df, sub_out], axis=1)
    raw_cols = list(COLS.values())
    rest = [c for c in out.columns if c not in front + list(sub_out.columns) + raw_cols]
    out[front + list(sub_out.columns) + raw_cols + rest].sort_values(KEY).to_csv(
        OUT_DIR / "monthly_scores.csv", index=False, encoding="utf-8-sig")

    print(f"\n점수 계산: {int(df['comfort_score'].notna().sum())}행 | "
          f"일부 지표 누락 {int((df['n_indicators'] < len(active)).sum())}행 | "
          f"추정값 포함 {int(df['has_imputed'].sum())}행")

    # 지역별 종합 순위
    region = df.groupby(["sigungu_code", NAME], as_index=False).agg(
        comfort_score=("comfort_score", "mean"),
        score_abs=("score_abs", "mean"), score_rel=("score_rel", "mean")).round(2)
    region["rank_abs"] = region["score_abs"].rank(ascending=False, method="min").astype(int)
    region["rank_rel"] = region["score_rel"].rank(ascending=False, method="min").astype(int)
    sub_region = sub_sel.groupby(df["sigungu_code"]).mean().round(1).add_prefix("s_").reset_index()
    region = region.merge(sub_region, on="sigungu_code").sort_values("comfort_score", ascending=False)
    region.insert(0, "rank", range(1, len(region) + 1))
    region.to_csv(OUT_DIR / "region_ranking.csv", index=False, encoding="utf-8-sig")
    print("\n[지역별 평균 점수 상위/하위 5]")
    show = ["rank", NAME, "comfort_score", "score_abs", "score_rel", "rank_abs", "rank_rel"]
    print(pd.concat([region.head(5), region.tail(5)])[show].to_string(index=False))

    # 최신 월 순위
    last = df["year_month"].max()
    latest = (df[df["year_month"] == last][["sigungu_code", NAME, "comfort_score", "score_abs"]]
              .sort_values("comfort_score", ascending=False))
    latest.insert(0, "rank", range(1, len(latest) + 1))
    latest.to_csv(OUT_DIR / "latest_month_ranking.csv", index=False, encoding="utf-8-sig")
    save_contract_json(df, OUT_DIR / "comfort_scores.json")
    print(f"\n최신 월({str(last)[:7]}) 1위: {latest.iloc[0][NAME]}, 최하위: {latest.iloc[-1][NAME]}")

    # 명목 가중치 vs 실효 영향
    inf = pd.DataFrame({
        "명목_가중치(%)": pd.Series({k: W[k] * 100 for k in active}),
        "실효영향(%)_절대점수": influence(s_abs.groupby(df["sigungu_code"]).mean(), W_raw),
        "실효영향(%)_상대점수": influence(s_rel.groupby(df["sigungu_code"]).mean(), W_raw),
    }).round(1)

        # --- 기간 평균 후 자치구 간 상대화: 가중치가 지역 순위에 그대로 반영되는 방식 ---
    pr, raw_mean = period_rel_scores(df)
    pr_noest, _ = period_rel_scores(df, mask=est)
    names = df.drop_duplicates("sigungu_code").set_index("sigungu_code")[NAME]
    final = pd.DataFrame({
        NAME: names,
        "period_rel_score": weighted(pr, W_raw).round(2),
        "점수_추정값제외": weighted(pr_noest, W_raw).round(2),
    }).join(pr.round(1).add_prefix("s_"))
    final["rank"] = final["period_rel_score"].rank(ascending=False, method="min").astype(int)
    final["rank_추정값제외"] = final["점수_추정값제외"].rank(ascending=False, method="min").astype(int)
    final = final.sort_values("rank")
    final.to_csv(OUT_DIR / "region_ranking_period_relative.csv", encoding="utf-8-sig")

    spread = raw_mean[active].agg(["min", "max"]).T
    spread["차이"] = spread["max"] - spread["min"]
    print("\n[자치구 간 실제 차이: 기간 평균] (기온은 목표 범위 이탈 °C, 나머지는 원단위)")
    print(spread.round(2).to_string())
    print("\n[기간 평균 상대화: 실효 영향(%)]")
    print(influence(pr, W_raw).round(1).to_string())
    old = region.set_index("sigungu_code")["comfort_score"].rank()
    print(f"\n기존 순위와의 Spearman: {final['period_rel_score'].rank().corr(old):.3f}")
    print(f"추정값 제외 시 순위 최대 변동: {int((final['rank'] - final['rank_추정값제외']).abs().max())}위")
    print(final[[NAME, "period_rel_score", "rank"]].head(5).to_string())
    print(final[[NAME, "period_rel_score", "rank"]].tail(5).to_string())
    print("\n[명목 가중치 vs 순위에 실제로 미치는 영향]")
    print(inf.to_string())
    inf.to_csv(OUT_DIR / "indicator_influence.csv", encoding="utf-8-sig")

    # 가중치 민감도 (현재 점수 방식 기준 지역 순위의 상관)
    other = "review_sheet3" if WEIGHT_SET == "design_sheet1" else "design_sheet1"
    scenarios = {
        f"other_set({other})": WEIGHT_SETS[other],
        "equal": {k: 1 for k in active},
        "no_noise": {**W_raw, "noise": 0},
        "with_ozone(10%)": {**W_raw, "ozone": 0.1 * sum(W_raw.values())},
    }
    region_sub = sub_sel.groupby(df["sigungu_code"]).mean()
    base_rank = weighted(region_sub, W_raw).rank()
    sens = pd.DataFrame([{"scenario": n, "spearman_vs_base": round(base_rank.corr(weighted(region_sub, w).rank()), 3)}
                         for n, w in scenarios.items()])
    print("\n[가중치 민감도] (1에 가까울수록 순위가 안 바뀜)")
    print(sens.to_string(index=False))
    sens.to_csv(OUT_DIR / "weight_sensitivity.csv", index=False, encoding="utf-8-sig")

    # 추정값이 점수에 미친 영향
    no_est = weighted(sub_sel.mask(est), W_raw)
    chk = df.loc[df["has_imputed"], ["sigungu_code", NAME, "year_month", "comfort_score"]].copy()
    chk["추정값_제외_점수"] = no_est[chk.index].round(2)
    chk["차이"] = (chk["comfort_score"] - chk["추정값_제외_점수"]).round(2)
    chk.to_csv(OUT_DIR / "imputed_impact.csv", index=False, encoding="utf-8-sig")
    print(f"\n[추정값 포함 {len(chk)}행] 추정 지표를 빼고 계산했을 때와의 점수 차이")
    print(chk.to_string(index=False))

    print(f"\n결과 위치: {OUT_DIR}")


if __name__ == "__main__":
    main()
