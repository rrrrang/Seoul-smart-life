import re
from datetime import date

import pandas as pd
from sqlalchemy import text

from .db import get_engine
from .region import RAW

NUM_COLS = ["jigudae_count", "pachulso_count", "safety_center_count"]


def find_file():
    files = sorted(RAW.glob("*지구대*.xlsx"))
    if not files:
        raise FileNotFoundError(f"{RAW} 안에서 지구대·파출소 엑셀 파일을 찾을 수 없음")
    return files[-1]


def parse_base_date(sheet):
    """'지구대파출소' 시트 첫 행의 '23.02.28 기준'에서 기준일을 읽는다."""
    for v in sheet.iloc[0]:
        m = re.search(r"(\d{2})\.(\d{1,2})\.(\d{1,2})\s*기준", str(v))
        if m:
            y, mo, d = map(int, m.groups())
            return date(2000 + y, mo, d)
    raise ValueError("'지구대파출소' 시트 첫 행에서 기준일을 찾을 수 없음")


def extract_gu(address, police_station, known_gu):
    """주소에서 구 이름을 읽고, 실패하면 경찰서 이름('서울동대문')으로 보정한다."""
    m = re.search(r"서울(?:특별시|시)?\s*([가-힣]+구)", str(address))
    if m and m.group(1) in known_gu:
        return m.group(1)
    name = re.sub(r"^서울", "", str(police_station).strip())
    name = name if name.endswith("구") else name + "구"
    return name if name in known_gu else None


def transform_police(sheets, dim):
    known_gu = set(dim["sigungu_name"])

    a = sheets["지구대파출소"].iloc[2:].copy()
    a = a[a[0].notna()]
    a = a.rename(columns={1: "station", 3: "kind", 4: "address"})
    a["kind"] = a["kind"].astype(str).str.strip()

    b = sheets["치안센터"].iloc[1:].copy()
    b = b[b[0].notna()]
    b = b.rename(columns={1: "station", 5: "address"})

    for df in (a, b):
        df["sigungu_name"] = [extract_gu(ad, st, known_gu) for ad, st in zip(df["address"], df["station"])]
        if df["sigungu_name"].isna().any():
            bad = df[df["sigungu_name"].isna()][["station", "address"]]
            raise ValueError(f"구를 찾지 못한 행:\n{bad}")

    unknown_kind = set(a["kind"]) - {"지구대", "파출소"}
    if unknown_kind:
        raise ValueError(f"알 수 없는 구분 값: {unknown_kind}")

    out = pd.DataFrame({
        "jigudae_count": a[a["kind"] == "지구대"].groupby("sigungu_name").size(),
        "pachulso_count": a[a["kind"] == "파출소"].groupby("sigungu_name").size(),
        "safety_center_count": b.groupby("sigungu_name").size(),
    }).reindex(sorted(known_gu)).fillna(0).astype(int)
    out.index.name = "sigungu_name"
    out = out.reset_index()

    # ---- 검증 ----
    if len(out) != 25:
        raise ValueError(f"구 개수가 25개가 아님: {len(out)}")
    if out["jigudae_count"].sum() + out["pachulso_count"].sum() != len(a):
        raise ValueError("지구대·파출소 집계 합이 원본 행 수와 다름")
    if out["safety_center_count"].sum() != len(b):
        raise ValueError("치안센터 집계 합이 원본 행 수와 다름")

    return out.merge(dim, on="sigungu_name", how="left")


def load_police(engine, df):
    cols = ["sigungu_code", "base_date"] + NUM_COLS
    updates = ", ".join(f"{c} = EXCLUDED.{c}" for c in NUM_COLS)
    sql = text(f"""
        INSERT INTO fact_police_facility ({", ".join(cols)})
        VALUES ({", ".join(":" + c for c in cols)})
        ON CONFLICT (sigungu_code, base_date) DO UPDATE SET {updates}
    """)
    with engine.begin() as conn:
        conn.execute(sql, df[cols].to_dict("records"))


def main(engine=None):
    engine = engine or get_engine()
    sheets = pd.read_excel(find_file(), sheet_name=None, header=None)
    dim = pd.read_sql(text("SELECT DISTINCT sigungu_code, sigungu_name FROM dim_region"), engine)
    if dim.empty:
        raise RuntimeError("dim_region이 비어 있음. 먼저 python -m etl.region 을 실행하세요")

    df = transform_police(sheets, dim)
    df["base_date"] = parse_base_date(sheets["지구대파출소"])
    load_police(engine, df)
    print("fact_police_facility", len(df), "행 | 지구대", df["jigudae_count"].sum(),
          "파출소", df["pachulso_count"].sum(), "치안센터", df["safety_center_count"].sum())


if __name__ == "__main__":
    main()