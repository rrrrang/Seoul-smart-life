"""Rebuild statistical safety scores, backend JSON and five fixed grades."""
from pathlib import Path
import argparse, json, sys
sys.path.insert(0, str(Path(__file__).resolve().parent))
from safety_scoring import score_safety
from evaluation_contract import load_region_master
from backend_contract import convert, validate_backend
from safety_grading import apply_grades, forbidden_paths

ROOT = Path(__file__).resolve().parents[1]
INPUT = ROOT / "data/safety_scoring_input.json"
RESULT = ROOT / "results/safety_scores.json"

def build_payload(input_path=INPUT):
    raw = json.loads(Path(input_path).read_text(encoding="utf-8-sig"))
    scores = score_safety(raw)
    master = load_region_master()
    backend = convert(scores, master)
    validate_backend(backend, scores, master)
    result = apply_grades(backend)
    if forbidden_paths(result):
        raise ValueError("Only statistical scores and grades may be exported")
    return result

def verify_saved(path=RESULT):
    actual = json.loads(Path(path).read_text(encoding="utf-8-sig"))
    expected = build_payload()
    if actual != expected:
        raise ValueError("Saved JSON differs from recomputed input statistics")
    return actual

if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--input", type=Path, default=INPUT)
    parser.add_argument("--output", type=Path, default=RESULT)
    parser.add_argument("--verify", action="store_true", help="Recompute and compare without writing")
    args = parser.parse_args()
    if args.verify:
        if args.input != INPUT:
            parser.error("--verify checks the packaged input; omit --input")
        data = verify_saved(args.output)
    else:
        data = build_payload(args.input)
        args.output.parent.mkdir(parents=True, exist_ok=True)
        args.output.write_text(json.dumps(data, ensure_ascii=False, indent=2, allow_nan=False), encoding="utf-8", newline="\n")
    distribution = {str(g): sum(x["metadata"]["safety"]["grade"] == g for x in data["items"]) for g in range(1, 6)}
    print(json.dumps({"rows": len(data["items"]), "grade_distribution": distribution, "verification": "passed" if args.verify else "generated"}, ensure_ascii=False))
