"""배포용 실행 파일.

기존 API(app.main)는 그대로 두고, 아래 두 가지만 더합니다.
1. 빌드한 프론트 화면(frontend/dist)을 같은 주소에서 보여 줍니다.
2. CORS_ALLOW_ORIGINS 환경변수에 적은 주소도 접속을 허용합니다.

실행: cd backend && uvicorn app.deploy_main:app --host 0.0.0.0 --port 8000
"""
import os
from pathlib import Path

from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles

from .main import create_app

app = create_app()

_extra_origins = [o.strip() for o in os.environ.get("CORS_ALLOW_ORIGINS", "").split(",") if o.strip()]
if _extra_origins:
    app.add_middleware(CORSMiddleware, allow_origins=_extra_origins,
                       allow_methods=["*"], allow_headers=["*"])

_dist = Path(os.environ.get("FRONTEND_DIST", Path(__file__).resolve().parents[2] / "frontend" / "dist"))
if (_dist / "index.html").is_file():
    # /api 경로는 위에서 먼저 처리되고, 나머지 주소는 프론트 화면으로 보냅니다.
    app.mount("/", StaticFiles(directory=_dist, html=True), name="frontend")
