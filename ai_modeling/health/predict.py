import argparse
import json
from pathlib import Path
import sys
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from health import HealthScoringService

def main():
    for stream in [sys.stdout, sys.stderr]:
        if hasattr(stream, 'reconfigure'):
            stream.reconfigure(encoding='utf-8')
    parser = argparse.ArgumentParser(description="건강·의료 환경 단일 행정동 점수")
    parser.add_argument('--region-code', required=True)
    parser.add_argument('--mode', choices=['current', 'forecast'], default='current')
    args = parser.parse_args()
    try:
        print(json.dumps(HealthScoringService().get_region_scores(args.region_code, args.mode), ensure_ascii=False, allow_nan=False))
    except Exception as exc:
        print(json.dumps({'error': type(exc).__name__, 'message': str(exc)}, ensure_ascii=False), file=sys.stderr)
        raise SystemExit(1)

if __name__ == '__main__':
    main()
