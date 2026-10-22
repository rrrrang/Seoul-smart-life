> 이번 전달의 시작 문서는 저장소 루트 docs/backend_handoff.md입니다. frontend/ 변경은 이번 PR에 포함하지 않습니다.

# DB 연동 상태 (2026-10-22)

추천 전용 PostgreSQL 저장소, FastAPI 실데이터 라우터, 슬라이더/비교 화면을 로컬 작업 브랜치에 구현했습니다. 이번 백엔드 전달은 별도 PR로 공유하며 프론트 변경은 제외합니다. 로컬 통합 검증과 최종 독립 리뷰/중요 지적 수정까지 마쳤으며, 최종 결과는 저장소 루트의 `docs/db_integration_report.md`를 기준으로 확인하세요.

- 기존 `database/ddl`/원시 ETL/`public.*`는 변경하지 않았습니다.
- `recommendation` 스키마의 releases/regions/observations/assignments만 사용합니다.
- 실제 명부427동, 점수 관측1733개, 연결2135개. 쾌적은25구 점수를427동에 연결합니다.
- canonical `region_code`는6자리 문자열, `sigungu_code`는5자리 문자열입니다. 10자리값은 검증된 기존 지도 경계 키일 뿐 DB/API 지역 식별자가 아닙니다.
- 서버 요청은 DB에서 같은 불변 배포본을 읽습니다. DB 장애 시 파일/Mock으로 대체하지 않습니다.
- 모든 화면 점수는100점 기준입니다. 중요도0~100을 합계로 나눠 비중을 계산하며 모두0은 거부합니다.
- LLM은 선택적 설명만 담당합니다. 키가 없거나 통신이 실패하면 계산된 사실 기반 기본 설명으로 동작합니다. 자연어 질문 UI는 없습니다.
- RAG 근거 문서는 아직 없으며 가짜 문서는 만들지 않았습니다.

## 전달 범위

순수 파일 추천은 `recommendation_service/`만으로 동작합니다. **새 DB/API/프론트 통합을 전달할 때는 이 폴더만으로 충분하지 않습니다.** 이번 백엔드 전달에는 저장소 루트의 `compose.recommendation.yml`, `recommendation.env.example`, `backend/`, `recommendation_service/`, 실행 문서가 필요합니다. 프론트는 담당자가 새 API 계약에 맞게 별도로 연결합니다. 실제 `.env.recommendation`, 프론트 `.env`, 가상환경, 캐시는 전달하지 않습니다.

설정은 서버에서 `RECOMMENDATION_DATABASE_URL`, 선택적 `OPENROUTER_API_KEY`/`OPENROUTER_MODEL`로 주입합니다. `requirements-db.txt`는 DB 추가 의존성이고 FastAPI 실행 환경은 `backend/requirements.txt`로 설치합니다. 앱 시작/요청은 DDL이나 점수 적재를 실행하지 않습니다.

현재 데이터는 기간과 승인 상태가 서로 다릅니다. 쾌적2026-09 구단위 상대값과 임시/참고 스냅샷 경고를 유지합니다. 실시간 공기질/실제 동별 관측/거주 만족도나 인과효과로 해석하지 않습니다.
