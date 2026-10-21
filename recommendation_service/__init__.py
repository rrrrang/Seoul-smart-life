"""Five-domain recommendation module; database adapter is supplied by the backend."""
from .services.ai_recommendation.snapshot_service import load_snapshot_dataset, recommend_snapshots
from .services.ai_recommendation.snapshot_llm import generate_snapshot_explanation
from .services.ai_recommendation.llm_service import OpenRouterClient, LLMError

__all__ = ["load_snapshot_dataset", "recommend_snapshots", "generate_snapshot_explanation", "OpenRouterClient", "LLMError"]
