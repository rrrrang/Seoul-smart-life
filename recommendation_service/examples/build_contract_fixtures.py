"""Contract fixtures: actual snapshots, mocked LLM, no external API calls."""
import asyncio
import json
from pathlib import Path
import httpx
from services.ai_recommendation.llm_service import OpenRouterClient, LLMError
from services.ai_recommendation.schemas import RecommendationRequest
from services.ai_recommendation.snapshot_llm import answer_snapshot_question, generate_snapshot_explanation
from services.ai_recommendation.snapshot_service import load_snapshot_dataset, recommend_snapshots

ROOT = Path(__file__).resolve().parents[1]


def save(name, value):
    if hasattr(value, "model_dump"):
        value = value.model_dump(mode="json")
    (ROOT / "fixtures").mkdir(exist_ok=True)
    (ROOT / "fixtures" / name).write_text(
        json.dumps(value, ensure_ascii=False, indent=2, allow_nan=False) + "\n", encoding="utf-8")


async def main():
    modeling = ROOT / "ai_modeling"
    if not (modeling / "economy/results/economy_scores.json").exists():
        modeling = ROOT / ".publish-repo/ai_modeling"
    dataset = load_snapshot_dataset(modeling, target_month="2026-10",
        domains=["economy", "energy", "comfort", "health", "safety"],
        allow_provisional=True, allow_context_scores=True)
    confirmed = RecommendationRequest(weights={"economy": 1, "energy": 1, "comfort": 1, "health": 1, "safety": 3})
    save("request_confirmed.json", confirmed)

    def handler(request):
        payload = json.loads(request.content)
        function = payload["tools"][0]["function"]["name"]
        data = json.loads(payload["messages"][1]["content"])
        if function == "PreferenceDraft":
            priorities = ["safety"]
            unsupported = ["월세 조건"] if data["question"] == "unsupported fixture" else []
            answer = {"weights": None, "priority_domains": priorities, "min_scores": {},
                      "unsupported_conditions": unsupported, "limitations": []}
        else:
            answer = {"items": [{"region_code": row["region_code"],
                "strength_domains": [row["strengths"][0]["domain"]],
                "weakness_domains": [row["weaknesses"][0]["domain"]], "evidence_ids": []}
                for row in data["recommendation"]["items"]]}
        return httpx.Response(200, json={"choices": [{"finish_reason": "tool_calls", "message": {
            "content": None, "tool_calls": [{"id": "fixture_call", "type": "function", "function": {
                "name": function, "arguments": json.dumps(answer)}}]}}]})

    async with httpx.AsyncClient(transport=httpx.MockTransport(handler)) as http:
        client = OpenRouterClient(api_key="fixture-placeholder", model="nvidia/nemotron-3-ultra-550b-a55b:free",
                                  http_client=http, max_retries=0, max_tokens=4096)
        weights = {d: 20 for d in ["economy", "energy", "comfort", "health", "safety"]}
        save("weights_request.json", {"weights": weights, "top_k": 5})
        rec = recommend_snapshots(dataset, weights=weights)
        exp = await generate_snapshot_explanation(rec, client)
        save("weights_response_llm.json", {"recommendation": rec.model_dump(mode="json"),
                                          "explanation": exp.model_dump(mode="json")})
        offline = await generate_snapshot_explanation(rec)
        save("weights_response_offline.json", {"recommendation": rec.model_dump(mode="json"),
                                              "explanation": offline.model_dump(mode="json")})
        provisional = await answer_snapshot_question("safety fixture", dataset, client)
        save("question_provisional.json", provisional)
        save("question_confirmed.json", await answer_snapshot_question(
            "safety fixture", dataset, client, confirmed_request=confirmed))
        save("question_needs_confirmation.json", await answer_snapshot_question("unsupported fixture", dataset, client))
    async with httpx.AsyncClient(transport=httpx.MockTransport(lambda r: httpx.Response(401))) as http:
        client = OpenRouterClient(api_key="fixture-placeholder", model="nvidia/nemotron-3-ultra-550b-a55b:free",
                                  http_client=http, max_retries=0)
        save("explanation_fallback.json", await generate_snapshot_explanation(provisional.recommendation, client))
        try:
            await answer_snapshot_question("safety fixture", dataset, client)
        except LLMError as error:
            save("error_authentication.json", error.as_dict())
    empty = recommend_snapshots(dataset, weights={"energy": 1}, min_scores={"energy": 100})
    assert not empty.items
    save("recommendation_empty.json", empty)


if __name__ == "__main__":
    asyncio.run(main())
