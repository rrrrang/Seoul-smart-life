"""Immutable release persistence and atomic activation; no file fallback or implicit DDL."""
from functools import wraps
import hashlib
import json
import re
from sqlalchemy import select, func, text
from sqlalchemy.exc import SQLAlchemyError
from .schema import releases, regions, observations, assignments
from ..services.ai_recommendation.schemas import DOMAINS
from ..services.ai_recommendation.snapshot_service import SnapshotDataset

LOCK_ID = 73428101


class RepositoryUnavailable(RuntimeError):
    pass


class ReleaseNotFound(LookupError):
    pass


class ReleaseConflict(ValueError):
    pass


def _safe_database(operation):
    @wraps(operation)
    def call(*args, **kwargs):
        try:
            return operation(*args, **kwargs)
        except SQLAlchemyError:
            raise RepositoryUnavailable("Recommendation database operation failed") from None
    return call


def _digest(value):
    return hashlib.sha256(json.dumps(value,sort_keys=True,ensure_ascii=False,
        separators=(",",":"),allow_nan=False).encode()).hexdigest()


def _prepare(dataset):
    data = SnapshotDataset.model_validate(dataset).model_copy(deep=True)
    if (not data.regions or not data.available_domains
            or len(set(data.available_domains)) != len(data.available_domains)):
        raise ValueError("Dataset must have unique available domains and nonempty regions")
    if re.fullmatch(r"snapshot-[a-f0-9]{16}", data.snapshot_version) is None:
        raise ValueError("Invalid snapshot identity")
    data.regions.sort(key=lambda row: row.region_code)
    seen, observation_map, region_rows, links = set(), {}, [], []
    for row in data.regions:
        if (re.fullmatch(r"[0-9]{6}",row.region_code) is None or row.region_code in seen
                or re.fullmatch(r"[0-9]{5}",row.sigungu_code) is None or not row.region_name.strip()):
            raise ValueError("Invalid or duplicate dataset region identity")
        seen.add(row.region_code)
        if set(row.domain_metadata) != set(data.available_domains):
            raise ValueError("Dataset evidence coverage differs from available domains")
        scores = row.category_scores.model_dump()
        if any(scores[d] is not None for d in DOMAINS if d not in data.available_domains):
            raise ValueError("Unavailable domain has a score")
        region_rows.append(dict(release_id=data.snapshot_version,region_code=row.region_code,
                                region_name=row.region_name,sigungu_code=row.sigungu_code))
        for domain in data.available_domains:
            evidence = row.domain_metadata[domain].model_dump(mode="json")
            level, code = "dong", row.region_code
            if domain == "comfort":
                if (evidence["original_spatial_units"] != ["sigungu"]
                        or evidence["details"].get("is_dong_observation") is not False
                        or evidence["details"].get("sigungu_code") != row.sigungu_code):
                    raise ValueError("Comfort requires explicit original district context")
                level, code = "sigungu", row.sigungu_code
            key = (domain,level,code)
            observation = dict(release_id=data.snapshot_version,domain=domain,
                score_level=level,score_code=code,score=scores[domain],evidence=evidence)
            if key in observation_map and observation_map[key] != observation:
                raise ValueError("Conflicting district observation cannot be merged")
            observation_map[key] = observation
            links.append(dict(release_id=data.snapshot_version,region_code=row.region_code,
                              sigungu_code=row.sigungu_code,domain=domain,score_level=level,score_code=code))
    payload=data.model_dump(mode="json")
    header={k:v for k,v in payload.items() if k != "regions"}
    return data,header,_digest(payload),region_rows,list(observation_map.values()),links


class SnapshotRepository:
    def __init__(self,engine):
        self.engine=engine

    @staticmethod
    def _lock(conn):
        conn.execute(text("SELECT pg_advisory_xact_lock(:lock_id)"),{"lock_id":LOCK_ID})

    @staticmethod
    def _activate(conn,release_id):
        state=conn.execute(select(releases.c.state).where(releases.c.release_id==release_id)).scalar_one_or_none()
        if state is None:raise ReleaseNotFound("Requested release does not exist")
        if state != "ready":raise ReleaseConflict("Only a ready release can be activated")
        conn.execute(releases.update().where(releases.c.is_active.is_(True)).values(is_active=False))
        conn.execute(releases.update().where(releases.c.release_id==release_id).values(is_active=True))

    @_safe_database
    def import_dataset(self,dataset: SnapshotDataset,*,activate: bool=False) -> str:
        if type(activate) is not bool:raise ValueError("activate must be an actual boolean")
        data,header,digest,region_rows,values,links=_prepare(dataset)
        key=data.snapshot_version
        with self.engine.begin() as conn:
            self._lock(conn)
            existing=conn.execute(select(releases).where(releases.c.release_id==key)).mappings().one_or_none()
            if existing is not None:
                if existing["payload_hash"] != digest:
                    raise ReleaseConflict("Release identity already exists with different content")
                self._restore(conn,existing)
            else:
                conn.execute(releases.insert().values(release_id=key,target_month=data.target_month,
                    state="draft",is_active=False,payload_hash=digest,dataset_metadata=header,
                    declared_regions=len(region_rows)))
                conn.execute(regions.insert(),region_rows)
                conn.execute(observations.insert(),values)
                conn.execute(assignments.insert(),links)
                conn.execute(releases.update().where(releases.c.release_id==key).values(state="ready"))
            if activate:self._activate(conn,key)
        return key

    @_safe_database
    def activate_release(self,release_id: str) -> None:
        with self.engine.begin() as conn:
            self._lock(conn)
            record=conn.execute(select(releases).where(releases.c.release_id==release_id)).mappings().one_or_none()
            if record is None:raise ReleaseNotFound("Requested release does not exist")
            self._restore(conn,record)
            self._activate(conn,release_id)

    def _restore(self,conn,record):
        if record["state"] != "ready":raise ReleaseConflict("Requested release is not ready")
        key=record["release_id"]
        rows=conn.execute(select(regions).where(regions.c.release_id==key).order_by(regions.c.region_code)).mappings().all()
        join=assignments.join(observations,
            (assignments.c.release_id==observations.c.release_id)&
            (assignments.c.domain==observations.c.domain)&
            (assignments.c.score_level==observations.c.score_level)&
            (assignments.c.score_code==observations.c.score_code))
        results=conn.execute(select(assignments.c.region_code,assignments.c.domain,
            observations.c.score,observations.c.evidence).select_from(join).where(assignments.c.release_id==key)).mappings().all()
        by_region={row["region_code"]:dict(region_code=row["region_code"],region_name=row["region_name"],
            sigungu_code=row["sigungu_code"],category_scores=dict.fromkeys(DOMAINS),domain_metadata={}) for row in rows}
        for result in results:
            row=by_region[result["region_code"]]
            row["category_scores"][result["domain"]]=result["score"]
            row["domain_metadata"][result["domain"]]=result["evidence"]
        try:
            data,header,digest,*_=_prepare({**record["dataset_metadata"],"regions":list(by_region.values())})
        except (ValueError,TypeError,KeyError):
            raise ReleaseConflict("Stored release payload is inconsistent") from None
        if (data.snapshot_version != key or data.target_month != record["target_month"]
                or len(rows) != record["declared_regions"] or digest != record["payload_hash"]):
            raise ReleaseConflict("Stored release content does not match its immutable digest")
        return data

    @_safe_database
    def load_dataset(self,release_id: str | None=None) -> SnapshotDataset:
        with self.engine.connect() as conn:
            query=select(releases)
            if release_id is None:query=query.where(releases.c.is_active.is_(True))
            else:query=query.where(releases.c.release_id==release_id)
            record=conn.execute(query).mappings().one_or_none()
            if record is None:
                if release_id is None:raise RepositoryUnavailable("No active recommendation release")
                raise ReleaseNotFound("Requested release does not exist")
            return self._restore(conn,record)

    @_safe_database
    def get_status(self) -> dict:
        with self.engine.connect() as conn:
            count=conn.execute(select(func.count()).select_from(releases)).scalar_one()
            active=conn.execute(select(releases.c.release_id,releases.c.target_month,releases.c.declared_regions)
                .where(releases.c.is_active.is_(True))).mappings().one_or_none()
            return {"release_count":count,"active_release":dict(active) if active else None}
