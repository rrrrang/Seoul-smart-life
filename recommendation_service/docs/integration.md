> 현재 DB/API 통합은 저장소 루트 docs/db_integration_report.md 및 backend/README.md를 확인하세요. 아래 첫 예제는 파일 단독 추천용이며 새 실데이터 API의 DB 읽기 경로를 대체하지 않습니다.

# 슬라이더 입력 연동

FastAPI route는 백엔드 담당 범위다. 아래는 서비스 함수 사용 예시다. 아래 서버 예제는 recommendation_service가 있는 저장소 루트에서 실행한다. 라이브러리는 명시적으로 recommendation_service에서 import한다. CLI는 README처럼 recommendation_service 폴더 안에서 실행한다. 데이터 경로는 서버 설정의 절대 경로로 바꿔도 된다.

```python
import os
from pathlib import Path
import httpx
from recommendation_service import (load_snapshot_dataset, recommend_snapshots,
                                    generate_snapshot_explanation, OpenRouterClient, LLMError)

# 서버 시작 시 한 번 로드. opt-in은 사용자 입력이 아니라 서버 배포 정책이다.
dataset = load_snapshot_dataset(
    Path('recommendation_service/ai_modeling').resolve(), target_month='2026-10',
    domains=['economy', 'energy', 'comfort', 'health', 'safety'],
    allow_provisional=True, allow_context_scores=True,
)

async def handle_recommendation(weights: dict[str, float], top_k: int = 5):
    rec = recommend_snapshots(dataset, weights=weights, top_k=top_k)
    # API 없이 기본 설명을 쓰려면 아래 한 줄 사용:
    # explanation = await generate_snapshot_explanation(rec)
    async with httpx.AsyncClient(trust_env=False, follow_redirects=False) as http:
        client = OpenRouterClient(
            api_key=os.environ['OPENROUTER_API_KEY'], model=os.environ['OPENROUTER_MODEL'],
            http_client=http, max_tokens=4096, timeout_seconds=20,
            total_timeout_seconds=60, max_retries=2,
        )
        explanation = await generate_snapshot_explanation(rec, client)
    return {'recommendation': rec.model_dump(mode='json'),
            'explanation': explanation.model_dump(mode='json')}
```

예제 입력은 fixtures/weights_request.json이다. recommend_snapshots에서 생략한 영역 가중치는0이다. 프론트는 항상 다섯 영역을 보내는 것을 권장한다. Pydantic RecommendationRequest를 직접 사용하는 경우 Weights 기본값은 각1이므로 생략 필드 의미가 다르다는 점에 주의한다. 기본값 혼동을 막으려면 API DTO에서 다섯 키를 모두 필수로 받아 전달한다. 요청 지역은 문자열 region_code6자리/sigungu_code5자리다.

## 서버 수명주기와 비용

데이터는 시작 시 검증 후 재사용하고 갱신 시 새 객체로 교체한다. 주입한 HTTPX 클라이언트는 서버 lifespan에서 공유하고 종료 시 aclose할 수 있다. 종료 책임은 백엔드에 있다. 동기 데이터 로딩을 요청마다 실행하지 않는다. async endpoint에서 asyncio.run을 사용하지 않는다.

슬라이더 움직임마다 LLM을 호출하지 않는다. 점수·순위 재계산은 API 없이 가능하므로 debounce 또는 적용 버튼으로 요청을 줄이고, 설명은 확정된 선택 지역·TOP5에 대해 생성한다. 같은 스냅샷·가중치·지역·모델 조건의 설명 캐시는 백엔드 정책으로 구현할 수 있다. 실제 무료 모델 지연·한도를 측정한 뒤 gateway 전체 제한과 사용자별 제한을 정한다.

설명 실패 시 함수는 계산된 추천을 유지하고 generation_status=fallback, diagnostics를 반환한다. 클라이언트 생성 전 키/모델 누락은 서버 설정 오류다. 오프라인 운영에서는 OpenRouterClient를 만들지 말고 client=None 기본 설명 경로를 사용한다. timeout_seconds20/total_timeout_seconds60은 설명 호출 기준이며 무조건60초 내 전체 서버응답을 보증하지 않는다.

## 범위

사용자 자연어 추출과 질문 UI는 사용하지 않는다. 기존 answer_snapshot_question은 호환용으로 남아 있으며 기본 화면 응답에는 question status가 없다. API 응답은 recommendation/explanation 묶음이다. FastAPI·DB·프론트 코드, 전체 지역/자치구 조회·TOP10·집계·관측 추이는 별도 구현이다. TOP5 결과만으로 전체 지도를 채우지 않는다.

## DB 응용 함수 사용 예시

저장소 루트에서 실행하고 서버 설정으로 DB URL을 주입합니다. 아래 코드는 테이블을 만들거나 자료를 적재하지 않습니다. 초기화/적재/활성 전환은 별도 CLI입니다.

```python
import os
from recommendation_service.database.connection import create_db_engine
from recommendation_service.database.repository import SnapshotRepository
from recommendation_service.services.ai_recommendation.application import RecommendationApplication
from recommendation_service.services.ai_recommendation.api_schemas import SliderRequest, CompareRequest, ExplainRequest

engine = create_db_engine(os.environ["RECOMMENDATION_DATABASE_URL"])
application = RecommendationApplication(SnapshotRepository(engine))
weights = {"economy":20,"energy":15,"comfort":25,"health":20,"safety":20}
result = application.recommend(SliderRequest(weights=weights, top_k=5))
version = result["snapshot_version"]
compared = application.compare(CompareRequest(
    weights=weights, release_id=version, region_codes=["110515", "110530"]
))
# async 서버 핸들러 내부에서, 키 없이 기본 설명:
# explained = await application.explain(ExplainRequest(
#     weights=weights, release_id=version, region_codes=["110515"]
# ), client=None)
# 서버 종료 시: engine.dispose()
```

동기 DB/계산은 API의 threadpool에서 실행합니다. 비동기 설명 use case는 DB 선행 작업을 asyncio.to_thread로 옮깁니다. FastAPI appfactory가 엔진과 선택적 HTTPX 클라이언트의 수명주기를 관리하므로 요청마다 새 엔진을 만들지 마세요.
