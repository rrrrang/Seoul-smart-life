"""Database-backed use cases. Existing deterministic scoring remains the authority."""
import json
import asyncio
from pathlib import Path
from .api_schemas import SliderRequest,CompareRequest,ExplainRequest,SliderWeights
from .schemas import DOMAINS
from .recommendation import calculate_total_score,normalize_weights
from .snapshot_service import recommend_snapshots,_public_metadata
from .snapshot_llm import generate_snapshot_explanation


class RegionNotFound(LookupError):
    pass


class RecommendationApplication:
    def __init__(self,repository):
        self.repository=repository
        identity=json.loads((Path(__file__).resolve().parents[2]/"data/region_identity.json").read_text(encoding="utf-8"))
        self.district_names=identity["district_names"]
        self.identities={r["region_code"]:r for r in identity["regions"]}

    def _load(self,release_id=None,sigungu_code=None):
        data=self.repository.load_dataset(release_id)
        if sigungu_code is not None:
            selected=[r for r in data.regions if r.sigungu_code==sigungu_code]
            if not selected:raise RegionNotFound("Requested district has no regions in this release")
            data=data.model_copy(deep=True,update={"regions":selected})
        return data

    @staticmethod
    def _weighted(row,weights):
        scores=row.category_scores.model_dump() if hasattr(row,"category_scores") else row
        if any(scores[d] is None and getattr(weights,d)>0 for d in DOMAINS):return None
        return round(calculate_total_score(scores,weights),6)

    def _summary(self,row):
        identity=self.identities.get(row.region_code)
        if identity and (identity["region_name"]!=row.region_name or identity["sigungu_code"]!=row.sigungu_code):
            # A new administrative release requires a reviewed identity mapping.
            identity=None
        return {"region_code":row.region_code,"region_name":row.region_name,"sigungu_code":row.sigungu_code,
            "sigungu_name":self.district_names.get(row.sigungu_code,row.sigungu_code),
            "geometry_key":identity["geometry_key"] if identity else None,
            "category_scores":row.category_scores.model_dump(),
            "safety_grade":row.domain_metadata["safety"].details.get("grade") if "safety" in row.domain_metadata else None,
            "domain_metadata":{d:{**e.model_dump(mode="json",exclude={"details"}),
                "is_dong_observation":e.details.get("is_dong_observation")}
                for d,e in row.domain_metadata.items()}}

    def scores(self,release_id=None,sigungu_code=None,weights=None):
        data=self._load(release_id,sigungu_code)
        items=[self._summary(row) for row in data.regions]
        if weights is not None:
            for item,row in zip(items,data.regions):item["personalized_score_100"]=self._weighted(row,weights)
        return {"snapshot_version":data.snapshot_version,"target_month":data.target_month,
                "available_domains":data.available_domains,"warnings":data.warnings,
                "count":len(items),"items":items,"is_mock":data.is_mock}

    def districts(self,weights=None,release_id=None):
        data=self._load(release_id)
        weights=weights or SliderWeights.model_validate(dict.fromkeys(DOMAINS,20))
        output=[]
        for code in sorted({r.sigungu_code for r in data.regions}):
            rows=[r for r in data.regions if r.sigungu_code==code]
            values={d:[getattr(r.category_scores,d) for r in rows if getattr(r.category_scores,d) is not None] for d in DOMAINS}
            means={d:sum(v)/len(v) if v else None for d,v in values.items()}
            output.append({"sigungu_code":code,"sigungu_name":self.district_names.get(code,code),
                "category_scores":means,"personalized_score_100":self._weighted(means,weights),
                "region_count":len(rows),"valid_region_counts":{d:len(v) for d,v in values.items()}})
        return {"snapshot_version":data.snapshot_version,"target_month":data.target_month,
            "aggregation":"mean_of_dong_scores","normalized_weights":normalize_weights(weights).model_dump(),
            "warnings":data.warnings,"items":output,"is_mock":data.is_mock}

    def region(self,region_code,release_id=None):
        data=self._load(release_id)
        row=next((r for r in data.regions if r.region_code==region_code),None)
        if row is None:raise RegionNotFound("Requested region does not exist in this release")
        return {"snapshot_version":data.snapshot_version,"target_month":data.target_month,
                "item":_public_metadata(row.model_dump(mode="json")),"summary":self._summary(row),
                "warnings":data.warnings,"is_mock":data.is_mock}

    def recommend(self,request:SliderRequest):
        request=SliderRequest.model_validate(request)
        data=self._load(request.release_id,request.sigungu_code)
        ranked=recommend_snapshots(data,weights=request.weights.model_dump(),top_k=request.top_k,
                                  min_scores=request.min_scores.model_dump(exclude_none=True))
        return {"snapshot_version":data.snapshot_version,"rank_scope":"sigungu" if request.sigungu_code else "seoul",
            "sigungu_code":request.sigungu_code,"recommendation":ranked.model_dump(mode="json"),
            "map_scores":[{"region_code":r.region_code,"personalized_score_100":self._weighted(r,request.weights)} for r in data.regions]}

    def _select(self,data,codes):
        lookup={r.region_code:r for r in data.regions}
        if any(code not in lookup for code in codes):raise RegionNotFound("One or more requested regions do not exist in this release")
        return data.model_copy(deep=True,update={"regions":[lookup[code] for code in codes]})

    def compare(self,request:CompareRequest):
        request=CompareRequest.model_validate(request)
        data=self._select(self._load(request.release_id),request.region_codes)
        ranked=recommend_snapshots(data,weights=request.weights.model_dump(),top_k=len(data.regions))
        first=data.regions[0].category_scores.model_dump()
        items=[]
        for row in data.regions:
            scores=row.category_scores.model_dump()
            items.append({**self._summary(row),"personalized_score_100":self._weighted(row,request.weights),
                "differences_from_first":{d:None if first[d] is None or scores[d] is None else round(scores[d]-first[d],6) for d in DOMAINS}})
        return {"snapshot_version":data.snapshot_version,"target_month":data.target_month,
            "rank_scope":"selected_regions","items":items,"recommendation":ranked.model_dump(mode="json"),
            "warnings":data.warnings,"is_mock":data.is_mock}

    def _explanation_input(self,request:ExplainRequest):
        request=ExplainRequest.model_validate(request)
        data=self._load(request.release_id,request.sigungu_code)
        scope="sigungu" if request.sigungu_code else "seoul"
        if request.region_codes is not None:
            data=self._select(data,request.region_codes);scope="selected_regions"
        ranked=recommend_snapshots(data,weights=request.weights.model_dump(),
            top_k=len(data.regions) if request.region_codes is not None else request.top_k,
            min_scores=request.min_scores.model_dump(exclude_none=True))
        return ranked,scope,data.snapshot_version

    async def explain(self,request:ExplainRequest,client=None):
        ranked,scope,version=await asyncio.to_thread(self._explanation_input,request)
        result=await generate_snapshot_explanation(ranked,client)
        return {"snapshot_version":version,"rank_scope":scope,
                "explanation":result.model_dump(mode="json")}
