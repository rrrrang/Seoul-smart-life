"""Run from project root: python -m examples.ai_recommendation_demo [--live]."""
import argparse
import asyncio
import json
import os
import sys

from services.ai_recommendation.llm_service import LLMError, OpenRouterClient, generate_explanation
from services.ai_recommendation.mock_data import get_mock_regions
from services.ai_recommendation.pipeline import answer_question
from services.ai_recommendation.recommendation import recommend_regions


async def main():
    parser = argparse.ArgumentParser(description="Mock score recommendation; --live calls OpenRouter")
    parser.add_argument("--live", action="store_true")
    parser.add_argument("--question", default="치안이 좋고 공기가 깨끗한 동네 추천해 줘")
    parser.add_argument("--max-tokens", type=int, default=2000,
                        help="Output budget; increase only if diagnostics report finish_reason=length")
    args = parser.parse_args()
    regions = get_mock_regions()
    if args.live:
        client = OpenRouterClient(api_key=os.environ.get("OPENROUTER_API_KEY", ""),
                                  model=os.environ.get("OPENROUTER_MODEL", ""), max_tokens=args.max_tokens)
        result = await answer_question(args.question, regions, client)
        output = result.model_dump()
    else:
        # Offline mode uses explicit sample weights, never claims LLM extraction.
        result = recommend_regions(regions, {"weights": {
            "economy": 1, "energy": 1, "comfort": 3, "health": 1, "safety": 3}})
        explanation = await generate_explanation(result)
        output = {"mode": "offline_explicit_weights", "recommendation": result.model_dump(),
                  "explanation": explanation.model_dump()}
    print(json.dumps(output, ensure_ascii=False, indent=2, allow_nan=False))


if __name__ == "__main__":
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8")
    try:
        asyncio.run(main())
    except LLMError as error:
        print(json.dumps(error.as_dict(), ensure_ascii=False), file=sys.stderr)
        raise SystemExit(1) from None
    except ValueError as error:
        print(json.dumps({"error": str(error)}, ensure_ascii=False), file=sys.stderr)
        raise SystemExit(1) from None
