"""Retrieval boundary only. No synthetic documents or automatic ingestion."""
from typing import Protocol

from .schemas import EvidenceChunk, EvidenceResult


class EvidenceRetriever(Protocol):
    async def search(self, query: str, *, region_code: str | None, top_k: int) -> list[EvidenceChunk]:
        """Search an index populated only from approved real documents."""
        ...


async def retrieve_evidence(
    query: str, retriever: EvidenceRetriever | None = None, *,
    region_code: str | None = None, top_k: int = 5,
) -> EvidenceResult:
    if not isinstance(query, str) or not query.strip() or len(query) > 2000:
        raise ValueError("query must contain 1 to 2000 characters")
    if type(top_k) is not int or not 1 <= top_k <= 10:
        raise ValueError("top_k must be 1 to 10")
    if region_code is not None and (not isinstance(region_code, str) or not region_code.strip()):
        raise ValueError("region_code must be a non-empty string")
    if retriever is None:
        return EvidenceResult(status="no_evidence", chunks=[])
    chunks = [EvidenceChunk.model_validate(c) for c in await retriever.search(
        query.strip(), region_code=region_code, top_k=top_k)]
    if len(chunks) > top_k:
        raise ValueError("retriever returned more than top_k chunks")
    if region_code and any(c.region_code not in (None, region_code) for c in chunks):
        raise ValueError("retriever returned evidence for a different region")
    return EvidenceResult(status="found" if chunks else "no_evidence", chunks=chunks)
