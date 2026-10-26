import asyncio

import pytest
from pydantic import ValidationError

from services.ai_recommendation.rag_service import retrieve_evidence
from services.ai_recommendation.schemas import EvidenceChunk, EvidenceResult


def test_no_documents_returns_no_evidence():
    result = asyncio.run(retrieve_evidence("치안 지표 정의"))
    assert result.chunks == []
    assert result.status == "no_evidence"


def test_search_interface_preserves_real_metadata_and_region_filter():
    class Retriever:
        async def search(self, query, *, region_code, top_k):
            assert query == "정의"
            assert region_code == "11680"
            assert top_k == 2
            return [EvidenceChunk(chunk_id="real-1", text="제공받은 문서 본문",
                source="https://example.org/document", document_title="지표 정의서",
                reference_year=2025, region_code="11680")]

    result = asyncio.run(retrieve_evidence("정의", Retriever(), region_code="11680", top_k=2))
    assert result.status == "found"
    assert result.chunks[0].reference_year == 2025
    assert result.chunks[0].source == "https://example.org/document"


def test_wrong_region_and_duplicate_evidence_are_rejected():
    class Retriever:
        async def search(self, *args, **kwargs):
            return [EvidenceChunk(chunk_id="x", text="본문", source="출처", document_title="제목",
                                  reference_year=2025, region_code="other")]
    with pytest.raises(ValueError):
        asyncio.run(retrieve_evidence("정의", Retriever(), region_code="11680"))


@pytest.mark.parametrize("kwargs", [{"top_k": 0}, {"top_k": 11}, {"query": " "}])
def test_invalid_search_request(kwargs):
    query = kwargs.pop("query", "정의")
    with pytest.raises(ValueError):
        asyncio.run(retrieve_evidence(query, **kwargs))


def test_evidence_requires_metadata():
    with pytest.raises(ValidationError):
        EvidenceChunk(chunk_id="x", text="본문", source="", document_title="제목", reference_year=2025)
