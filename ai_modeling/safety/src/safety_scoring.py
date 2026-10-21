"""치안 평가 점수 계산. 범죄 예측/ETL/API와 분리된 순수 계산 모듈."""
from __future__ import annotations
from fractions import Fraction
import argparse,json,math,re
from datetime import date
from pathlib import Path
from evaluation_contract import validate_regions
DEFAULT_WEIGHTS={"crime":0.8,"cctv":0.1,"police":0.1}
CATEGORIES=("murder","robbery","sexual_assault","theft","violence")
SOURCE_PERIODS={"crime":"2025","population":"2025-01/2025-12 month-end mean",
 "cctv":"2026-06-30","police":"2025-12-31","jurisdiction_mapping":"2025-12-31"}

def number(v,positive=False,integer=False):
    if isinstance(v,bool) or not isinstance(v,(int,float,Fraction)) or not math.isfinite(v):
        raise ValueError("유한한 숫자가 필요합니다. 결측과 0은 다릅니다.")
    if v<0 or (positive and v<=0) or (integer and int(v)!=v):raise ValueError("수량/분모 범위 오류")
    return v

def relative_scores(values,higher_is_better=True):
    """원값 오름차순 평균순위 백분위. 동점 동일, 모두 같으면 50점."""
    if len(values)<2:raise ValueError("비교지역은 2개 이상이어야 합니다.")
    for v in values.values():number(v)
    ordered=sorted(values.values());n=len(ordered)
    positions={}
    for i,v in enumerate(ordered,1):positions.setdefault(v,[]).append(i)
    ranks={v:Fraction(sum(p),len(p)) for v,p in positions.items()}
    return {k:float(100*((ranks[v]-1) if higher_is_better else (n-ranks[v]))/(n-1)) for k,v in values.items()}

def combine(scores,weights=None):
    weights=DEFAULT_WEIGHTS if weights is None else weights
    if set(weights)!=set(DEFAULT_WEIGHTS) or set(scores)!=set(DEFAULT_WEIGHTS):raise ValueError("성분 키 불일치")
    for v in weights.values():number(v)
    if not math.isclose(sum(weights.values()),1,abs_tol=1e-10):raise ValueError("가중치 합은 1")
    if any(v is None for v in scores.values()):return None
    for v in scores.values():
        number(v)
        if v>100:raise ValueError("점수는 0~100")
    return sum(scores[k]*weights[k] for k in weights)

def unique(rows,key):
    d={r[key]:r for r in rows}
    if len(d)!=len(rows):raise ValueError("중복 키: "+key)
    return d

def score_safety(data,weights=None):
    periods=data["source_periods"]
    if periods != SOURCE_PERIODS:
        raise ValueError("현재 배포 입력의 고정 자료기간과 다릅니다. 기간과 기준을 함께 검토해야 합니다.")
    for field in ("cctv","police"):date.fromisoformat(periods[field])
    weights=dict(DEFAULT_WEIGHTS if weights is None else weights)
    combine(dict.fromkeys(DEFAULT_WEIGHTS,50),weights)
    regions=unique(data["regions"],"region_id")
    districts=unique(data["districts"],"sigungu_code")
    dongs=unique(data["dongs"],"region_code")
    validate_regions(data["dongs"], require_all=True)
    if len(regions)!=25 or len(districts)!=25 or len(dongs)!=427:raise ValueError("고정 비교집단 25권역·25구·427동을 유지해야 합니다.")
    def mean(r):
        ms=r["population_monthly_2025"]
        if len(ms)!=12:raise ValueError("2025년 월말인구 12개가 필요합니다.")
        for n in ms:number(n,positive=True,integer=True)
        return Fraction(sum(ms),12)
    rp={k:mean(r) for k,r in regions.items()}
    gp={k:mean(r) for k,r in districts.items()}
    if sum(rp.values())!=sum(gp.values()):raise ValueError("권역과 구 인구 합계 불일치")
    for month_index in range(12):
        if sum(r["population_monthly_2025"][month_index] for r in regions.values()) != sum(r["population_monthly_2025"][month_index] for r in districts.values()):
            raise ValueError("월별 권역과 구 인구 합계 불일치")
    counts={};police={}
    for k,r in regions.items():
        if set(r["crime_counts"])!=set(CATEGORIES):raise ValueError("5개 범죄 항목 필요")
        for n in r["crime_counts"].values():number(n,integer=True)
        for field in ("jigudae_count","pachulso_count"):number(r[field],integer=True)
        counts[k]=sum(r["crime_counts"].values())
        police[k]=r["jigudae_count"]+r["pachulso_count"]
    for r in districts.values():number(r["cctv_security"],integer=True)
    rates={"crime":{k:Fraction(v)*10000/rp[k] for k,v in counts.items()},
           "police":{k:Fraction(v)*10000/rp[k] for k,v in police.items()},
           "cctv":{k:Fraction(r["cctv_security"])*10000/gp[k] for k,r in districts.items()}}
    scores={k:relative_scores(v,k!="crime") for k,v in rates.items()}
    records=[];profiles={}
    def component(kind,key,count,pop,period,scope):
        return {"count":count,"population_mean_2025":float(pop),"rate_per_10000_residents":float(rates[kind][key]),
                "score":scores[kind][key],"weight":weights[kind],"weighted_points":scores[kind][key]*weights[kind],
                "source_period":period,"measurement_scope":scope,"measurement_area_id":key,"comparison_count":25}
    for code,d in sorted(dongs.items()):
        if not re.fullmatch(r"\d{6}",code) or not d["region_name"]:raise ValueError("행정동 코드/이름 오류")
        rid=d["jurisdiction_id"];gu=d["sigungu_code"]
        if rid not in regions or gu not in districts:raise ValueError("행정동 연결 오류")
        reg=regions[rid]
        cc=component("crime",rid,counts[rid],rp[rid],"2025","pooled_police_jurisdiction")
        pc=component("police",rid,police[rid],rp[rid],data["source_periods"]["police"],"pooled_police_jurisdiction")
        cv=component("cctv",gu,districts[gu]["cctv_security"],gp[gu],data["source_periods"]["cctv"],"sigungu")
        s=combine({"crime":cc["score"],"police":pc["score"],"cctv":cv["score"]},weights)
        key=rid+"__"+gu
        profiles.setdefault(key,{"profile_id":key,"jurisdiction_id":rid,"jurisdiction_name":reg["region_name"],
            "sigungu_code":gu,"sigungu_name":districts[gu]["sigungu_name"],"crime_score":cc["score"],
            "cctv_score":cv["score"],"police_score":pc["score"],"score":s,"dong_count":0})
        profiles[key]["dong_count"]+=1
        records.append({"region_code":code,"region_name":d["region_name"],"sigungu_code":gu,
          "jurisdiction_id":rid,"profile_id":key,"score":s,"status":"calculated_draft",
          "components":{"crime":cc,"cctv":cv,"police":pc},"observed_dong_crime_count":None,
          "observed_dong_cctv_count":None,"observed_dong_police_count":None,
          "mapping_status":d["mapping_status"],"jurisdiction_review":d["jurisdiction_review"],
          "quality_flags":d["quality_flags"]+data["quality_flags"]})
    # 427개 연결 행을 독립 관측으로 재순위화하지 않는다.
    for p in profiles.values():
        p["profile_rank"]=1+sum(round(q["score"],10)>round(p["score"],10) for q in profiles.values())
    for d in records:d["profile_rank"]=profiles[d["profile_id"]]["profile_rank"]
    return {"domain":"safety","snapshot_id":data["snapshot_id"],
      "weights":weights,"source_periods":data["source_periods"],"comparison":{"crime_regions":25,"cctv_districts":25,"police_regions":25,"profiles":len(profiles),"linked_dongs":427},
      "interpretation":"관할권역·자치구 상대점수를 행정동에 연결. 동 자체 실측점수나 피해확률이 아님.",
      "profiles":sorted(profiles.values(),key=lambda p:(p["profile_rank"],p["profile_id"])),"results":records}

if __name__=="__main__":
    p=argparse.ArgumentParser();p.add_argument("--input",required=True,type=Path);p.add_argument("--output",required=True,type=Path)
    a=p.parse_args();obj=score_safety(json.loads(a.input.read_text(encoding="utf-8")))
    a.output.parent.mkdir(parents=True,exist_ok=True)
    a.output.write_text(json.dumps(obj,ensure_ascii=False,indent=2,allow_nan=False),encoding="utf-8")
