"""Recommendation entry points, separate from upstream evaluation models."""
from services.ai_recommendation.snapshot_service import load_snapshot_dataset, recommend_snapshots

__all__ = ["load_snapshot_dataset", "recommend_snapshots"]
