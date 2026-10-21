import json
import sys

from examples.recommend_snapshot_demo import main
from services.ai_recommendation.llm_service import LLMError

if __name__ == "__main__":
    for stream in (sys.stdout, sys.stderr):
        if hasattr(stream, "reconfigure"):
            stream.reconfigure(encoding="utf-8")
    try:
        main()
    except LLMError as error:
        print(json.dumps(error.as_dict(), ensure_ascii=False), file=sys.stderr)
        raise SystemExit(1) from None
    except (ValueError, OSError, KeyError, TypeError) as error:
        print(json.dumps({"error": str(error)}, ensure_ascii=False), file=sys.stderr)
        raise SystemExit(1) from None
