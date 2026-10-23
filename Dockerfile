# 1단계: 프론트 화면 빌드
FROM node:22-slim AS web
WORKDIR /web
COPY frontend/package.json frontend/package-lock.json ./
RUN npm ci
COPY frontend/ ./
# 카카오 지도 JavaScript 키는 빌드할 때 화면 코드에 들어갑니다 (Render 환경변수로 넣기)
ARG VITE_KAKAO_MAP_KEY
ENV VITE_KAKAO_MAP_KEY=$VITE_KAKAO_MAP_KEY
RUN npm run build

# 2단계: 백엔드 실행 (화면도 같이 보여 줌)
FROM python:3.11-slim
WORKDIR /app
COPY backend/requirements.txt backend/requirements.txt
COPY recommendation_service/requirements-db.txt recommendation_service/requirements-db.txt
COPY recommendation_service/requirements-ai.txt recommendation_service/requirements-ai.txt
RUN pip install --no-cache-dir -r backend/requirements.txt
COPY backend/ backend/
COPY recommendation_service/ recommendation_service/
COPY --from=web /web/dist frontend/dist
WORKDIR /app/backend
ENV PYTHONUNBUFFERED=1
CMD ["sh", "-c", "uvicorn app.deploy_main:app --host 0.0.0.0 --port ${PORT:-8000}"]
