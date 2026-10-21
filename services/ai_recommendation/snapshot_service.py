"""Join delivered score snapshots; never load pickle models or invent missing domains.

The upstream teams own evaluation models. This module owns recommendation only.
Energy/health reference CSVs are explicitly labelled precomputed snapshots, not
fresh inference, and provisional/contextual scores require caller opt-in.
"""
import csv
import hashlib
import io
import json
import math
from pathlib import Path
import re
from typing import Literal

from .recommendation import recommend_regions
from .schemas import (
    DOMAINS, CategoryScores, Contract, Domain, DomainInsight, ExcludedRegion,
    RecommendationRequest, RegionScore, Score, Weights,
)


class SnapshotEvidence(Contract):
    source_file: str
    file_sha256: str
    artifact_kind: Literal["result_snapshot", "reference_snapshot"]
    status: str
    original_spatial_units: list[str]
    source_periods: dict[str, str]
    reference_years: list[int]
    production_approved: bool = False
    interpretation: str
    details: dict


class SnapshotRegion(Contract):
    region_code: str
    region_name: str
    sigungu_code: str
    category_scores: CategoryScores
    domain_metadata: dict[Domain, SnapshotEvidence]


class SnapshotDataset(Contract):
    regions: list[SnapshotRegion]
    available_domains: list[Domain]
    target_month: str
    snapshot_version: str
    file_hashes: dict[str, str]
    domain_metadata: dict[Domain, dict]
    warnings: list[str]
    is_mock: bool = False


class SnapshotRecommendationItem(SnapshotRegion):
    rank: int
    personalized_score_100: Score
    contributions: dict[Domain, float]
    domain_points_20: dict[Domain, float | None]
    selected_total_points: float
    five_domain_total_points: float | None
    strengths: list[DomainInsight]
    weaknesses: list[DomainInsight]


class SnapshotRecommendation(Contract):
    selected_domains: list[Domain]
    unavailable_domains: list[Domain]
    normalized_weights: Weights
    selected_max_points: int
    items: list[SnapshotRecommendationItem]
    excluded: list[ExcludedRegion]
    warnings: list[str]
    target_month: str
    snapshot_version: str
    file_hashes: dict[str, str]
    domain_metadata: dict[Domain, dict]
    is_mock: bool = False


class _Reader:
    def __init__(self, root):
        self.root = Path(root).resolve()
        self.hashes = {}
        self.manifests = {}

    def read(self, relative):
        path = (self.root / relative).resolve()
        if not path.is_relative_to(self.root):
            raise ValueError("source file must stay inside modeling directory")
        raw = path.read_bytes()
        self.hashes[relative] = hashlib.sha256(raw).hexdigest()
        return raw.decode("utf-8-sig")

    def json(self, relative):
        def pairs(entries):
            result = {}
            for key, value in entries:
                if key in result:
                    raise ValueError("duplicate JSON key")
                result[key] = value
            return result
        def nonfinite(value):
            raise ValueError("nonfinite JSON number")
        return json.loads(self.read(relative), object_pairs_hook=pairs, parse_constant=nonfinite)

    def csv(self, relative):
        reader = csv.DictReader(io.StringIO(self.read(relative), newline=""))
        if not reader.fieldnames or len(reader.fieldnames) != len(set(reader.fieldnames)):
            raise ValueError("missing or duplicate CSV columns")
        rows = list(reader)
        if any(None in row for row in rows):
            raise ValueError("CSV row has excess columns")
        return rows

    def verify(self, domain, relative):
        if domain not in self.manifests:
            self.manifests[domain] = self.json(f"{domain}/MANIFEST.json")
        expected = self.manifests[domain].get("files", {}).get(relative)
        if not expected or self.hashes.get(f"{domain}/{relative}") != expected:
            raise ValueError(f"{domain}: source snapshot integrity mismatch: {relative}")


def _index(rows, master=None):
    indexed = {}
    for row in rows:
        code = row.get("region_code")
        if not isinstance(code, str) or re.fullmatch(r"[0-9]{6}", code) is None:
            raise ValueError("region_code must be a six-digit project string, not truncated official codes")
        if code in indexed:
            raise ValueError("duplicate region_code")
        indexed[code] = row
    if master is not None and set(indexed) != set(master):
        raise ValueError("region set does not match delivered master")
    return indexed


def _score(value):
    if value is None:
        return None
    if isinstance(value, bool) or not isinstance(value, (int, float)) or not math.isfinite(value) or not 0 <= value <= 100:
        raise ValueError("domain score must be a finite number from 0 to 100 or null")
    return float(value)


def _evidence(reader, path, kind, status, units, periods, interpretation, details):
    periods = {key: str(value) for key, value in periods.items()}
    years = sorted({int(year) for value in periods.values() for year in re.findall(r"(?<!\d)(?:19|20)\d{2}(?!\d)", value)})
    return SnapshotEvidence(source_file=path, file_sha256=reader.hashes[path], artifact_kind=kind,
        status=status, original_spatial_units=units, source_periods=periods, reference_years=years,
        production_approved=False, interpretation=interpretation, details=details)


def load_snapshot_dataset(
    modeling_dir: str | Path, *, target_month: str, domains: list[Domain],
    allow_provisional: bool = False, allow_context_scores: bool = False,
) -> SnapshotDataset:
    """Load an explicit fixed release, not latest live data. Missing domains stay null."""
    if type(allow_provisional) is not bool or type(allow_context_scores) is not bool:
        raise ValueError("snapshot opt-in flags must be actual boolean values")
    if not isinstance(target_month, str) or re.fullmatch(r"[0-9]{4}-(0[1-9]|1[0-2])", target_month) is None:
        raise ValueError("target_month must be YYYY-MM")
    if not domains or len(domains) != len(set(domains)) or any(d not in DOMAINS for d in domains):
        raise ValueError("select unique supported domains")
    if "comfort" in domains:
        raise ValueError("comfort unavailable: no score artifact delivered; health cannot substitute for comfort")
    if any(d in domains for d in ("energy", "health")) and not allow_provisional:
        raise ValueError("allow_provisional=True required for unapproved pilot snapshots")
    if any(d in domains for d in ("health", "safety")) and not allow_context_scores:
        raise ValueError("allow_context_scores=True required for assigned district/jurisdiction context")
    reader = _Reader(modeling_dir)
    config = reader.json("economy/model_config.json")
    if config["target_month"] != target_month:
        raise ValueError("target month differs from this fixed modeling release")
    master = _index(reader.csv("economy/data/regions.csv"))
    if len(master) != config["expected_regions"]:
        raise ValueError("region count differs from delivered master contract")
    expected_hash = config["artifact_sha256"]["data/regions.csv"]
    if reader.hashes["economy/data/regions.csv"] != expected_hash:
        raise ValueError("region master integrity mismatch")
    for row in master.values():
        if re.fullmatch(r"[0-9]{5}", row.get("sigungu_code", "")) is None or not row.get("region_name"):
            raise ValueError("invalid region master identity")
    scores = {code: dict.fromkeys(DOMAINS) for code in master}
    evidence = {code: {} for code in master}
    global_metadata = {}
    warnings = {"FIXED_SNAPSHOT_NOT_LIVE_DATA"}
    selected = [d for d in DOMAINS if d in domains]
    for domain in selected:
        if domain in ("economy", "safety"):
            path = f"{domain}/results/{domain}_scores.json"
            payload = reader.json(path)
            if payload.get("is_mock") is not False or payload.get("domains") != list(DOMAINS):
                raise ValueError("invalid supplied score snapshot contract")
            items = payload.get("items")
            if not isinstance(items, list):
                raise ValueError("missing snapshot items")
            _index([item["region"] for item in items], master)
            global_metadata[domain] = payload["metadata"][domain]
            for item in items:
                region = item["region"]
                code = region["region_code"]
                expected = master[code]
                if (region.get("name_ko") != expected["region_name"] or region.get("sigungu_code") != expected["sigungu_code"]
                        or region.get("spatial_unit") != "dong"):
                    raise ValueError("region identity mismatch")
                values = item["scores"]
                if set(values) != set(DOMAINS) or any(values[d] is not None for d in DOMAINS if d != domain):
                    raise ValueError("invalid domain score keys or unrelated domain values")
                scores[code][domain] = _score(values[domain])
                detail = item["metadata"][domain]
                if domain == "economy":
                    if detail.get("target_month") != target_month or config["target_month"] != target_month:
                        raise ValueError("target month differs from delivered economy estimate")
                    if detail.get("status") != "estimated":
                        raise ValueError("economy must remain an estimate")
                    periods = detail["source_periods"]
                    units = ["administrative_dong"]
                    meaning = "경제활동 집중도 추정. 주민 소득·집값·실제 현재월 관측값이 아님."
                    warnings.add("ECONOMY_ESTIMATED")
                else:
                    periods = global_metadata[domain]["source_periods"]
                    units = sorted({c["measurement_scope"] for c in detail["components"].values()})
                    meaning = "관할권역·자치구 기반 치안 참고점수. 행정동 실제 범죄율·피해확률이 아님."
                    warnings.add("CONTEXT_ASSIGNED_SAFETY")
                evidence[code][domain] = _evidence(reader, path, "result_snapshot", detail["status"], units,
                                                  periods, meaning, detail)
        else:
            path = f"{domain}/reference/current_scores.csv"
            rows = _index(reader.csv(path), master)
            reader.verify(domain, "reference/current_scores.csv")
            deployment = reader.json(f"{domain}/config/deployment_metadata.json")
            reader.verify(domain, "config/deployment_metadata.json")
            spec = reader.json(f"{domain}/config/model_spec.json")[domain]
            reader.verify(domain, "config/model_spec.json")
            if deployment.get("production_approved") is not False:
                raise ValueError("pilot approval metadata changed; review the new release")
            if domain == "energy":
                period = deployment["energy_latest_actual"]
                context_path = "energy/data/energy_quarter.csv"
                context = _index([r for r in reader.csv(context_path) if r["quarter"] == period], master)
                reader.verify(domain, "data/energy_quarter.csv")
                periods = {"energy": period}
                units = ["source_group_assigned_to_administrative_dong"]
                meaning = spec["scope"]
                status = "pilot_not_approved"
            else:
                period = deployment["health_as_of"]
                context_path = "health/data/health_snapshot.csv"
                context = _index(reader.csv(context_path), master)
                reader.verify(domain, "data/health_snapshot.csv")
                periods = spec["component_dates"]
                units = ["administrative_dong", "sigungu"]
                meaning = "의료자원과 자치구 대기환경의 상대 참고지수. 질병확률·실제 도보시간이 아님."
                status = "relative_reference_not_approved"
                warnings.add("CONTEXT_ASSIGNED_HEALTH_AIR")
            global_metadata[domain] = {"deployment": deployment, "model_spec": spec,
                "artifact_kind": "reference_snapshot", "is_forecast": False,
                "note": "배포된 검증용 현재점수 스냅샷을 재사용하며 모델을 새로 추론하지 않음"}
            warnings.add(f"PROVISIONAL_{domain.upper()}")
            for code, row in rows.items():
                raw_score = row[f"{domain}_score"]
                scores[code][domain] = _score(float(raw_score)) if raw_score else None
                ctx = context[code]
                if ctx.get("region_name") != master[code]["region_name"]:
                    raise ValueError("reference snapshot region name mismatch")
                details = {"period": period, "is_forecast": False, "grade": row[f"{domain}_grade"],
                           "deployment": deployment, "row_context": ctx}
                if domain == "health":
                    details["source_units_confirmed"] = spec["exposure"]["source_units_confirmed"]
                evidence[code][domain] = _evidence(reader, path, "reference_snapshot", status, units,
                                                  periods, meaning, details)
    digest = hashlib.sha256(json.dumps(reader.hashes, sort_keys=True).encode()).hexdigest()
    return SnapshotDataset(regions=[SnapshotRegion(region_code=code, region_name=master[code]["region_name"],
        sigungu_code=master[code]["sigungu_code"], category_scores=scores[code], domain_metadata=evidence[code])
        for code in sorted(master)], available_domains=selected, target_month=target_month,
        snapshot_version=f"snapshot-{digest[:16]}", file_hashes=reader.hashes,
        domain_metadata=global_metadata, warnings=sorted(warnings))


def recommend_snapshots(
    dataset: SnapshotDataset, *, weights: dict[str, float], top_k: int = 5,
    min_scores: dict[str, float] | None = None,
) -> SnapshotRecommendation:
    """Explicit domain selection; never auto-renormalize away requested missing domains."""
    if any(d not in DOMAINS for d in weights):
        raise ValueError("unknown weight domain")
    # Unlike the legacy generic API, omitted weights here mean excluded domains.
    full_weights = Weights.model_validate({d: weights.get(d, 0) for d in DOMAINS})
    selected = [d for d in DOMAINS if getattr(full_weights, d) > 0]
    unavailable = [d for d in DOMAINS if d not in dataset.available_domains]
    if any(d in unavailable for d in selected) or any(d in unavailable for d in (min_scores or {})):
        raise ValueError("requested domain unavailable in loaded dataset; change the request explicitly")
    request = RecommendationRequest(weights=full_weights, top_k=top_k, min_scores=min_scores or {})
    # Original provenance is held separately, not mislabeled as dong observations.
    engine_rows = [RegionScore(region_code=r.region_code, region_name=r.region_name,
        spatial_unit="administrative_dong", score_version=dataset.snapshot_version,
        category_scores=r.category_scores, is_mock=False) for r in dataset.regions]
    ranked = recommend_regions(engine_rows, request)
    lookup = {r.region_code: r for r in dataset.regions}
    items = []
    for ranked_row in ranked.items:
        row = lookup[ranked_row.region_code]
        values = row.category_scores.model_dump()
        points = {d: None if values[d] is None else round(values[d] / 5, 6) for d in DOMAINS}
        total = round(sum(values[d] / 5 for d in selected), 6)
        visible = [d for d in selected if values[d] is not None]
        def insights(reverse):
            ordered = sorted(visible, key=lambda d: ((-1 if reverse else 1) * values[d], DOMAINS.index(d)))[:2]
            return [DomainInsight(domain=d, score=values[d], contribution=ranked_row.contributions[d]) for d in ordered]
        items.append(SnapshotRecommendationItem(**row.model_dump(), rank=ranked_row.rank,
            personalized_score_100=ranked_row.total_score, contributions=ranked_row.contributions,
            domain_points_20=points, selected_total_points=total,
            five_domain_total_points=round(sum(values.values()) / 5, 6) if all(v is not None for v in values.values()) else None,
            strengths=insights(True), weaknesses=insights(False)))
    warnings = set(dataset.warnings)
    if len(selected) < len(DOMAINS):
        warnings.add("PARTIAL_DOMAIN_RECOMMENDATION")
    if "comfort" in unavailable:
        warnings.add("COMFORT_NOT_DELIVERED")
    return SnapshotRecommendation(selected_domains=selected, unavailable_domains=unavailable,
        normalized_weights=ranked.normalized_weights, selected_max_points=20 * len(selected), items=items,
        excluded=ranked.excluded, warnings=sorted(warnings), target_month=dataset.target_month,
        snapshot_version=dataset.snapshot_version, file_hashes=dataset.file_hashes,
        domain_metadata=dataset.domain_metadata)
