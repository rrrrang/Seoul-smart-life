import asyncio
import json

import httpx
import pytest

from services.ai_recommendation.llm_service import LLMError, OpenRouterClient
from services.ai_recommendation.mock_data import get_mock_regions
from services.ai_recommendation.pipeline import answer_question


@pytest.mark.parametrize("flag", ["false", "true", 0, 1, None])
def test_fallback_requires_actual_boolean_before_external_call(flag):
    class MustNotCall:
        async def structured(self, *args, **kwargs):
            pytest.fail("invalid options must fail before LLM calls")
    with pytest.raises(ValueError, match="boolean"):
        asyncio.run(answer_question("추천", get_mock_regions(), MustNotCall(), allow_llm_fallback=flag))


def test_pipeline_returns_json_and_falls_back_only_when_explicitly_enabled():
    async def run():
        async with httpx.AsyncClient(transport=httpx.MockTransport(lambda r: httpx.Response(401))) as http:
            client = OpenRouterClient(api_key="test", model="test/model", http_client=http)
            with pytest.raises(LLMError):
                await answer_question("치안 좋은 곳", get_mock_regions(), client)
            result = await answer_question("치안 좋은 곳", get_mock_regions(), client, allow_llm_fallback=True)
            assert result.preferences.extraction_status == "fallback"
            assert result.preferences.weights.safety == 1
            assert len(result.recommendation.items) == 5
            assert result.evidence.status == "no_evidence"
            assert result.explanation.generation_status == "fallback"
            assert json.loads(result.model_dump_json())["recommendation"]["is_mock"] is True
    asyncio.run(run())
