# 백엔드 전달 안내: 추천 시스템·LLM 설명·PostgreSQL

작성일: 2026-10-22. 이번 전달은 별도 브랜치/PR이며 main에 자동 병합하지 않습니다. 프론트 변경은 포함하지 않습니다.

## 전달 이력

- 이전 파일 기반 추천 패키지는 main의 recommendation_service/에 이미 올라가 있습니다(88d4f75).
- 이번 전달은 그 패키지에 PostgreSQL 저장소와 실데이터 API를 추가하는 작업입니다.
- 백엔드 담당자에게 직접 연락하거나 인수 확인을 받은 기록은 없습니다. 이 문서와 PR을 담당자에게 전달하면 됩니다.

## 어디를 보면 되나요?

| 위치 | 내용 |
|---|---|
| recommendation_service/ | 추천·설명·DB 어댑터·점수 데이터·테스트 전체 |
| recommendation_service/database/ | 전용4테이블·명시적 CLI·불변 배포본 저장/활성화 |
| recommendation_service/services/ai_recommendation/application.py | 백엔드가 호출하는 추천·비교·설명 use case |
| backend/app/recommendation_api.py | /api/recommendation 실데이터 API |
| backend/app/main.py | 기존 API를 유지하며 새 라우터 연결 |
| compose.recommendation.yml | 로컬 PostgreSQL16 구성 |
| recommendation.env.example | 실제 비밀값 없는 설정 이름 안내 |
| docs/db_integration_report.md | 설치·DB 초기화·점수 적재·활성화·종료·테스트 명령 |
| docs/db_integration_red_team.md | 독립 검토·수정·미검증 항목 |

## 백엔드 담당자가 해야 할 일

1. PR의 기존 main.py/requirements 변경을 팀 API 구조와 비교해 검토합니다. 기존 원시 통계 DDL/ETL은 이번 추천 초기화 과정에서 실행하지 않습니다.
2. 로컬 Compose 또는 팀 PostgreSQL에 recommendation 스키마를 명시적으로 초기화합니다. 팀 DB에서는 권한/기존 스키마를 먼저 확인합니다.
3. 보고서의 CLI로 현재 제공 점수를 새 배포본에 적재하고 활성화합니다. 서버 시작/요청은 DDL이나 점수 적재를 하지 않습니다.
4. 서버 환경변수 RECOMMENDATION_DATABASE_URL을 설정합니다. 선택적 LLM 설명을 사용할 때만 OPENROUTER_API_KEY와 OPENROUTER_MODEL을 설정합니다.
5. 상태→점수 조회→추천 TOP5→지역 비교→설명 순서로 확인합니다. 테스트는 별도 이름이 _test로 끝나는 DB에서만 실행합니다.
6. 프론트 담당자에게 새 API의 입력/응답과 snapshot_version 고정 규칙을 전달합니다. 프론트 코드는 이번 PR에 없습니다.

설치(저장소 루트, Python3.11):
```powershell
py -3.11 -m venv .venv-db
& .\.venv-db\Scripts\python.exe -m pip install -r backend/requirements.txt
```
기존 환경이 있으면 재생성하지 말고 사용합니다. 이후 상세 명령은 db_integration_report.md를 따릅니다.

## 핵심 API와 계약

- GET /api/recommendation/status, /districts, /regions, /scores
- GET /api/recommendation/regions/{region_code}
- POST /api/recommendation/recommendations, /compare, /explanations
- 행정동 region_code6자리 문자열, sigungu_code5자리 문자열입니다. 10자리는 기존 지도 경계 키이며 canonical API 키가 아닙니다.
- 다섯 중요도0~100을 합계로 정규화합니다. 모두0은422, 동점은 region_code 오름차순입니다. 화면용 점수는100점 기준입니다.
- 요청 예: {"weights":{"economy":20,"energy":15,"comfort":25,"health":20,"safety":20},"top_k":5}
- 응답 snapshot_version을 후속 요청 release_id로 전달하여 같은 배포본을 조회합니다.
- 구 필터는 추천 전에 적용합니다. 선택지역 설명의 순위를 서울 전체 순위로 표시하지 않습니다.
- 결측 점수는0이 아닙니다. DB 장애는503이며 Mock으로 대체하지 않습니다.
- 쾌적은25구 참고값을427개 동에 연결한 값이며 동별 실측이 아닙니다. 출처·기간·원본 공간 단위·승인 경고를 보존합니다.
- LLM은 점수/순위를 계산하지 않습니다. 키가 없거나 호출에 실패하면 계산된 사실 기반 기본 설명을 반환합니다.

## 검증과 제외 파일

로컬 실제 PostgreSQL을 사용한 Python222개 통과 기록이 있습니다. 프론트를 제외한 이번 전달 브랜치에서도 222개 통과(skip0, 65.77초)를 재확인했습니다. 기존173개 추천 회귀를 포함합니다.

실제 OpenRouter 신규 통신은 키가 없어 미검증입니다. RAG 실제 문서는 미제공이며 가짜 문서는 만들지 않았습니다. 프론트/지도 검증은 별도 작업 브랜치에서 수행한 기록으로 이번 PR의 구현 범위와 구분합니다.

실제 .env, API 키, DB 비밀번호, 가상환경, node_modules, 캐시, 로컬 Docker 볼륨은 전달하지 않습니다. 실제 자격증명은 팀 서버의 환경변수/비밀 저장소로 주입하세요.
