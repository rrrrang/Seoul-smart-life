"""Step-by-step recommendation from released artifacts; no API key required."""
import argparse
import json
from pathlib import Path
import sys

from services.ai_recommendation.schemas import DOMAINS
from services.ai_recommendation.snapshot_service import load_snapshot_dataset, recommend_snapshots


def main():
    parser = argparse.ArgumentParser(description="Recommend from explicit delivered snapshots, never fresh model inference")
    parser.add_argument("--modeling-dir", type=Path, default=Path(__file__).resolve().parents[1] / "ai_modeling")
    parser.add_argument("--target-month", required=True, help="YYYY-MM; must match the economy estimate if loaded")
    parser.add_argument("--domains", choices=DOMAINS, nargs="+", default=["economy"])
    parser.add_argument("--weights", nargs="+", metavar="DOMAIN=WEIGHT", help="Default: equal weights for selected domains only")
    parser.add_argument("--allow-provisional", action="store_true")
    parser.add_argument("--allow-context-scores", action="store_true")
    parser.add_argument("--top-k", type=int, default=5)
    parser.add_argument("--output", type=Path, help="Optional NEW JSON file; never overwrites an existing file")
    args = parser.parse_args()
    weights = {d: 1 for d in args.domains}
    if args.weights:
        weights = {}
        for entry in args.weights:
            domain, separator, raw = entry.partition("=")
            if not separator or domain not in args.domains or domain in weights:
                raise ValueError("weights must be unique DOMAIN=NUMBER entries for selected domains")
            weights[domain] = float(raw)
    dataset = load_snapshot_dataset(args.modeling_dir, target_month=args.target_month, domains=args.domains,
        allow_provisional=args.allow_provisional, allow_context_scores=args.allow_context_scores)
    result = recommend_snapshots(dataset, weights=weights, top_k=args.top_k)
    output = result.model_dump_json(indent=2)
    if args.output:
        # Source snapshots and upstream code can never be overwritten by CLI output.
        target = args.output.resolve()
        if target.is_relative_to(args.modeling_dir.resolve()):
            raise ValueError("output must be outside the source modeling directory")
        target.parent.mkdir(parents=True, exist_ok=True)
        with target.open("x", encoding="utf-8") as file:
            file.write(output + "\n")
    print(output)


if __name__ == "__main__":
    for stream in (sys.stdout, sys.stderr):
        if hasattr(stream, "reconfigure"):
            stream.reconfigure(encoding="utf-8")
    try:
        main()
    except (ValueError, OSError, KeyError, TypeError) as error:
        print(json.dumps({"error": str(error)}, ensure_ascii=False), file=sys.stderr)
        raise SystemExit(1) from None
