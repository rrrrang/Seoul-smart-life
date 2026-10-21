"""Recommendation entry points, separate from upstream evaluation models."""
from services.ai_recommendation.snapshot_service import load_snapshot_dataset, recommend_snapshots
from services.ai_recommendation.snapshot_llm import answer_snapshot_question, generate_snapshot_explanation

__all__ = ["load_snapshot_dataset", "recommend_snapshots", "answer_snapshot_question", "generate_snapshot_explanation"]
