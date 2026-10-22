> 이번 전달의 시작 문서는 저장소 루트 docs/backend_handoff.md입니다. frontend/ 변경은 이번 PR에 포함하지 않습니다.

> 상태(2026-10-22): 파일 단독 추천에 더해 로컬 PostgreSQL 어댑터와 API용 application을 구현했습니다. 통합 실행은 저장소 루트의 docs/db_integration_report.md, 현재 검증 범위는 docs/db_integration_status.md를 확인하세요. 이번 백엔드 전달은 별도 PR로 공유하며 프론트 변경은 제외합니다.

# 서울 생활환경 추천: 백엔드 인수인계

현재 기준: **슬라이더로 5대 영역 중요도 입력 → 행정동 TOP 5 → 추천 근거·주의할 점 표시**. 사용자 자연어 질문 UI는 사용하지 않습니다. 파일 단독 실행은 이 폴더를 작업 루트로 사용합니다. DB 어댑터는 database/에, FastAPI와 프론트 코드는 저장소 루트 backend/와 frontend/에 있습니다.

## 빠른 실행

Python 3.11, PowerShell에서 이 폴더로 이동한 뒤:

```powershell
py -3.11 -m venv .venv
& '.\.venv\Scripts\python.exe' -m pip install -r requirements-ai.txt
& '.\.venv\Scripts\python.exe' -m pytest -q
& '.\.venv\Scripts\python.exe' -m examples.recommend_snapshot_demo --target-month 2026-10 --domains economy energy comfort health safety --weights economy=20 energy=20 comfort=20 health=20 safety=20 --allow-provisional --allow-context-scores --with-explanation
```

API 없이 추천과 기본 설명이 실행됩니다. LLM 설명을 쓸 경우 같은 창에서:

```powershell
$env:OPENROUTER_API_KEY = (Read-Host 'API 키').Trim()
$env:OPENROUTER_MODEL = 'nvidia/nemotron-3-ultra-550b-a55b:free'
& '.\.venv\Scripts\python.exe' -m examples.recommend_snapshot_demo --target-month 2026-10 --domains economy energy comfort health safety --weights economy=20 energy=20 comfort=20 health=20 safety=20 --allow-provisional --allow-context-scores --live
```

`--question`은 사용하지 않습니다. `.env.example`은 설정 이름 안내이며 .env 자동 로딩은 없습니다. 키는 백엔드 환경에만 주입하세요. 설명은 검증된 LLM 영역 선택을 사용해 Python이 사실 문장을 구성하며, LLM이 수치·순위를 계산하지 않습니다.

## 읽는 순서

1. docs/weights.md: 독립 슬라이더·가중평균·지도 색 기준
2. docs/integration.md: 호출 함수와 서버 수명주기
3. docs/contract.md: 100점 화면 필드·오류 처리
4. fixtures/README.md: API 없이 재현하는 응답 예제
5. docs/verification.md: 검증 결과와 한계

## 파일 책임

| 위치 | 책임 |
|---|---|
| services/ai_recommendation/snapshot_service.py | 스냅샷 로딩·해시·공간단위 검증, 가중 추천 |
| services/ai_recommendation/snapshot_llm.py | 실제 점수에 근거한 장단점 설명 |
| services/ai_recommendation/llm_service.py | OpenRouter 도구 호출/JSON schema 및 검증·재시도 |
| services/ai_recommendation/schemas.py | 공통 요청·응답 계약 |
| ai_modeling/ | 5영역 점수와 무결성·원천 맥락 자료. upstream 학습은 실행하지 않음 |
| contracts/ | Pydantic에서 생성한 JSON schema |
| fixtures/weights_request.json | 프론트 슬라이더 입력 예제 |
| fixtures/weights_response_*.json | 추천과 설명 응답 예제 |
| examples/build_contract_fixtures.py | 외부 호출 없이 예제 재생성 |
| tests/ai_recommendation/ | 단위·모의 HTTP·회귀 테스트 |

기존 자연어 서비스와 Mock 파일은 호환·회귀 검증용으로 유지했습니다. 현재 화면에서 answer_snapshot_question/extract_preferences를 호출할 필요는 없습니다. source_group 내부 코드는 응답에서 제외됩니다.

## 쾌적 데이터 주의

쾌적은 2026-09 **25개 자치구의 월별 상대점수**를 sigungu_code로 427개 동에 연결했습니다. 같은 구 동들은 쾌적 점수가 같습니다. 동별 관측값·절대 환경등급·현재 실시간 상태가 아닙니다. 보간·추정 플래그와 원래 공간단위·기간을 보존했습니다. 원천 공공자료 설명서와 운영 승인은 아직 미제공입니다.

모델 재학습 파일·가상환경·실제 키는 제외했습니다. 새 DB 연동 변경은 별도 백엔드 전달 브랜치/PR로 공유합니다. 새 API는 전체 점수 조회·자치구 필터·동 점수 평균 집계·TOP5·지역 비교를 지원합니다. 관측 추이는 미제공입니다.


## 백엔드 전달 데이터 위치

`ai_modeling/`에 경제·에너지·쾌적·건강·치안의 고정 점수와 검증·근거 파일이 있습니다. 이 폴더 전체를 함께 전달하세요. DB를 생성하거나 스키마를 자동 변경하지 않습니다. 현재 배포 기준은2026-10이며 영역별 실제 원천기간은 각각 다릅니다. 쾌적은2026-09 구단위 참고값입니다.

서버 연동은 저장소 루트에서 `from recommendation_service import load_snapshot_dataset, recommend_snapshots, generate_snapshot_explanation`로 시작합니다. 기존 최상위 services 모듈을 import하면 과거 구현을 읽을 수 있으므로 섞어 쓰지 마세요.

DB 연결에 남은 작업은 `docs/db_integration_status.md`, 수정한 입력 검증과 검증 결과는 `docs/release_notes.md`를 참고하세요.

## DB/API 연동 파일

- database/: 명시적 초기화, 불변 점수 배포본 저장/복원/활성 전환
- services/ai_recommendation/api_schemas.py: 5개 슬라이더 필수 및 코드/배포본 검증
- services/ai_recommendation/application.py: 기존 계산 엔진 재사용, 화면 요약/비교/설명
- data/region_identity.json: 프로젝트 코드와 기존 지도 경계 키의 검증된 대응
- tests/db/: 실제 PostgreSQL 무결성/일관성/롤백/응용 테스트

단독 import는 SQLAlchemy를 강제하지 않습니다. DB 응용은 `from recommendation_service.services.ai_recommendation.application import RecommendationApplication`로 명시적으로 가져옵니다.
