"""Explicit slider API contract; all five preferences are required."""
from typing import Annotated
from pydantic import Field, model_validator
from .schemas import Contract, ExplicitWeights, CategoryScores

SliderNumber=Annotated[float,Field(strict=True,ge=0,le=100,allow_inf_nan=False)]
RegionCode=Annotated[str,Field(strict=True,pattern=r"^[0-9]{6}$")]
DistrictCode=Annotated[str,Field(strict=True,pattern=r"^[0-9]{5}$")]
ReleaseId=Annotated[str,Field(strict=True,pattern=r"^snapshot-[a-f0-9]{16}$")]


class SliderWeights(ExplicitWeights):
    economy: SliderNumber
    energy: SliderNumber
    comfort: SliderNumber
    health: SliderNumber
    safety: SliderNumber


class WeightedSelection(Contract):
    weights: SliderWeights
    release_id: ReleaseId | None=None


class SliderRequest(WeightedSelection):
    top_k: Annotated[int,Field(strict=True,ge=1,le=5)]=5
    sigungu_code: DistrictCode | None=None
    min_scores: CategoryScores=Field(default_factory=CategoryScores)


class CompareRequest(WeightedSelection):
    region_codes: Annotated[list[RegionCode],Field(min_length=2,max_length=5)]

    @model_validator(mode="after")
    def unique_regions(self):
        if len(set(self.region_codes))!=len(self.region_codes):
            raise ValueError("Region codes must be unique")
        return self


class ExplainRequest(SliderRequest):
    region_codes: Annotated[list[RegionCode],Field(min_length=1,max_length=5)] | None=None

    @model_validator(mode="after")
    def unique_regions(self):
        if self.region_codes is not None and len(set(self.region_codes))!=len(self.region_codes):
            raise ValueError("Region codes must be unique")
        return self
