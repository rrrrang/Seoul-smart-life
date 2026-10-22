> 전달 시작 문서: docs/backend_handoff.md. 이번 PR은 추천·DB·백엔드와 문서만 포함하며 frontend/ 변경은 없습니다. 아래 프론트 검증 기록은 별도 로컬 통합 브랜치의 결과입니다.

# 추천 DB·API·프론트 통합 보고서

작성일: 2026-10-22. 작업 사본은 `C:\Users\human\Desktop\Seoul_Smart_Life\.recommendation-upload`, 이번 백엔드 전달 브랜치는 `codex/recommendation-backend-handoff`입니다. **별도 PR로 검토하며 main에 자동 병합하지 않습니다.** 원래 전체 통합은 로컬 `codex/recommendation-db-integration` 브랜치에 보존했습니다.

## 구현 범위

파일 점수 스냅샷 → 검증된 불변 DB 배포본 → Python 가중평균/TOP5 → FastAPI → 기존 슬라이더·상세·비교 화면을 연결했습니다. 사용자 자연어 입력은 없습니다. LLM은 선택적 설명에만 사용하며 없어도 추천/기본 설명이 실행됩니다.

| 위치 | 책임 |
|---|---|
| compose.recommendation.yml | PostgreSQL16, localhost55432, healthcheck, 영속 볼륨 |
| recommendation_service/database/schema.py | recommendation 스키마의 전용4테이블/제약 검증 |
| recommendation_service/database/repository.py | 원자 적재·같은 버전 내용 불변·활성 전환·Dataset 복원 |
| recommendation_service/database/cli.py | 명시적 init/import/activate/status |
| recommendation_service/services/ai_recommendation/api_schemas.py | 5개 슬라이더·코드·배포본 검증 |
| recommendation_service/services/ai_recommendation/application.py | 기존 추천 공식 재사용, 요약/구집계/비교/설명 |
| backend/app/recommendation_api.py | 실데이터 전용 API /api/recommendation |
| frontend/src/services/RecommendationContext.tsx | 페이지 공통 가중치·불변 배포본 고정 |
| frontend/src/services/recommendationApi.ts | API 요청·DTO·AbortSignal·100점 표시 |
| frontend/src/components/DetailAnalysis.tsx | 독립 슬라이더·TOP5·영역점수·명시적 설명 요청 |
| frontend/src/components/RegionComparison.tsx | 같은 가중치·배포본의 두 지역 비교 |
| frontend/src/components/MainPage.tsx | 구별 동 점수 평균과 유효 개수 |

기존 `database/ddl`, 원시 ETL, public 테이블, 다른 작업 사본은 변경하지 않았습니다. 기존 Mock API는 호환용으로 유지하지만 새 화면은 새 실데이터 API만 호출합니다.

## 데이터와 계산 계약

- 행정동 region_code:6자리 문자열. sigungu_code:5자리 문자열. 10자리값은 기존 GeoJSON 경계 키에 한해 명시적 대응 명부로 사용합니다.
- 427개 지역, 점수 관측1733개, 연결2135개입니다. 쾌적은25개 자치구 점수를427개 동에 연결하며 동별 관측값으로 취급하지 않습니다.
- 활성 배포본: `snapshot-687b22575d77a2ae`, 배포 대상월2026-10. 영역별 원천 기간은 다르며 쾌적은2026-09 구단위 상대값입니다.
- 점수/출처/기간/원래 공간 단위/추정·승인 상태를 DB 왕복 시 보존합니다. 동일 배포본에 다른 내용이 들어오면 거부합니다.
- Σ(원점수×중요도)/Σ중요도. 중요도5개는0~100이며 모두0은422입니다. 모두100이면 실제 비중은각20%입니다. 서버가 점수·동점 코드순·순위를 계산하고 LLM은 계산하지 않습니다.
- 선택 가중치가 양수인 영역의 점수가 결측이면 해당 동은 추천에서 제외합니다. 결측을0으로 채우지 않습니다. 가중치0인 영역은 추천 계산에 필요하지 않습니다.
- API/화면 점수는100점 기준입니다. 영역 원점수는 중요도를 바꿔도 변하지 않습니다.
- 자치구 요약은 영역별 유효 동 점수 평균이며 직접 구 관측이 아닙니다. 영역별 유효수/전체수를 제공합니다. 양의 가중치를 가진 영역의 평균을 구할 수 없으면 개인화 점수는null입니다.
- 구 필터를 먼저 적용한 뒤 TOP5를 계산합니다. 비교/선택지역 설명의 순위 범위는 selected_regions이며 서울 전체 순위로 표시하지 않습니다.
- 지도 경계424개, 명부427개. 용두동230533/오류제2동530780/강일동740515는 목록·추천에 유지하고 경계 누락을 안내합니다. 종합색은100점 연속척도이며 정의 없는1~5등급을 만들지 않습니다.

## 로컬 설정 및 시작

저장소 루트에서 Python3.11 환경을 준비합니다(기존 `.venv-db`가 있으면 재생성하지 않습니다).

```powershell
py -3.11 -m venv .venv-db
& .\.venv-db\Scripts\python.exe -m pip install -r backend/requirements.txt
```

`recommendation.env.example`을 `.env.recommendation`으로 복사한 뒤 본인 로컬 비밀번호와 두 URL을 설정합니다. 기존 파일이 있으면 덮어쓰지 않습니다. 비밀번호는 충분히 긴 임의 영숫자/hex값으로 만들면 URL 인코딩 실수를 줄일 수 있습니다.

```dotenv
RECOMMENDATION_DB_PASSWORD=YOUR_LOCAL_HEX_PASSWORD
RECOMMENDATION_DATABASE_URL=postgresql+psycopg://recommendation:YOUR_LOCAL_HEX_PASSWORD@127.0.0.1:55432/seoul_recommendation
RECOMMENDATION_TEST_DATABASE_URL=postgresql+psycopg://recommendation:YOUR_LOCAL_HEX_PASSWORD@127.0.0.1:55432/seoul_recommendation_test
```

위 값은 형식 예제이며 실제 자격증명이 아닙니다. 이 파일은 Git에서 제외합니다. 선택적 OPENROUTER_API_KEY/OPENROUTER_MODEL은 서버 환경에만 둡니다. 기존 볼륨이 있으면 환경변수의 비밀번호만 바꿔도 DB 계정 비밀번호가 자동으로 바뀌지 않습니다.

```powershell
docker compose --env-file .env.recommendation -f compose.recommendation.yml up -d --wait
```

**최초 한 번만**, 별도 테스트DB가 없을 때 생성합니다. 운영/개발DB를 테스트DB로 대체하지 않습니다.

```powershell
docker compose --env-file .env.recommendation -f compose.recommendation.yml exec recommendation-db psql -U recommendation -d seoul_recommendation -c "CREATE DATABASE seoul_recommendation_test OWNER recommendation;"
```

명시적 DB CLI에만 `.env.recommendation`을 읽히는 PowerShell 도우미입니다. python-dotenv는 위 백엔드 의존성에 포함됩니다. `init`은 호환되지 않는 기존 구조를 자동 변경하지 않습니다.

```powershell
function Invoke-RecommendationDb {
  & .\.venv-db\Scripts\python.exe -c "from dotenv import load_dotenv; load_dotenv('.env.recommendation'); from recommendation_service.database.cli import main; raise SystemExit(main())" @args
}
Invoke-RecommendationDb init
Invoke-RecommendationDb import --modeling-dir recommendation_service/ai_modeling --target-month 2026-10 --domains economy energy comfort health safety --allow-provisional --allow-context-scores --activate
Invoke-RecommendationDb status
```

`--allow-provisional`, `--allow-context-scores`는 현재 제공된 참고/임시 산출물을 사용한다는 명시적 선택이며 운영 승인을 뜻하지 않습니다. 같은 내용은 재적재해도 중복되지 않습니다. 새 자료는 새 배포본으로 적재한 뒤 상태를 확인하고 활성화합니다. 이전 배포본으로 되돌릴 때도 삭제하지 않고 다음과 같이 활성화합니다.

```powershell
Invoke-RecommendationDb activate snapshot-687b22575d77a2ae
```

API는 DDL/적재를 실행하지 않습니다.

```powershell
& .\.venv-db\Scripts\python.exe -m uvicorn backend.app.main:app --env-file .env.recommendation --host 127.0.0.1 --port 8000
```

API 문서는 http://127.0.0.1:8000/docs 에서 확인합니다. 프론트 개발/설정은 이번 전달 범위에서 제외합니다. 아래의 프론트·지도 테스트 기록은 별도 로컬 통합 브랜치에서 얻은 결과입니다.

## 종료와 재시작

개발 서버 터미널은 Ctrl+C로 종료합니다. DB 데이터 보존 종료:

```powershell
docker compose --env-file .env.recommendation -f compose.recommendation.yml stop
```

같은 `up -d --wait`로 재시작합니다. 볼륨 삭제, Docker 초기화, WSL 배포판 삭제를 기본 복구 절차로 사용하지 않습니다. Docker가 Healthy여도 Windows TCP 연결이 실패하면 엔진/WSL 로그와 실제 연결을 확인해야 합니다.

## 검증 실행

테스트DB URL이 실제 `_test` DB를 가리키는지 먼저 확인하세요. DB fixture는 이 테스트DB의 추천4테이블을 비웁니다. 환경변수를 생략해 DB 테스트가 skip된 결과를 실DB 검증으로 계산하면 안 됩니다.

```powershell
& .\.venv-db\Scripts\python.exe -c "from dotenv import load_dotenv; load_dotenv('.env.recommendation'); import pytest; raise SystemExit(pytest.main(['-c','recommendation_service/pytest.ini','recommendation_service/tests/ai_recommendation','recommendation_service/tests/db','backend/tests','-q']))"
```

`-c`를 생략하면 상위 작업폴더의 pytest 설정/구형 services 패키지가 선택될 수 있습니다. Windows에서 실행 사용자 간 TEMP 권한 충돌이 있으면 `.test-tmp` 아래 새 경로를 `--basetemp`로 지정하고 `-p no:cacheprovider`를 사용합니다.

## 검증 결과와 남은 제한

2026-10-22 최종: 전체 기존추천+실제 PostgreSQL+API **222개 통과**, skip0, AnyIO deprecation 경고1개입니다. 프론트 단위8개·리뷰 회귀 브라우저4개·타입 검사·빌드가 통과했습니다. 독립 Red Team 지적3건과 추가 설명 취소 문제1건을 RED→GREEN으로 수정했습니다. 자세한 재현/판단은 `docs/db_integration_red_team.md`에 기록했습니다.

- 기존173개 추천 회귀가 포함됩니다. 실제 PostgreSQL을 SQLite로 대체하지 않았습니다.
- 개발DB를 재시작한 뒤427개 지역과 동일 배포본이 보존됐고 두 독립 연결의 Dataset이 동일했습니다.
- 프론트 Node8개, TypeScript 검사, Vite 프로덕션 빌드가 통과했습니다.
- Edge에서 실제 API를 사용하는 구TOP5/100비중/치안만 선택/모두0 거부/기본 설명/비교/503 표시를 확인했습니다.
- 실제 OpenRouter 신규 호출은 키가 없어 미검증입니다. 모의 HTTP 오류와 기본 설명 동작은 검증했습니다.
- 실제 Kakao SDK 렌더링은 키가 없어 미검증입니다. 명부·경계키 매핑과424/427 차이는 검증했습니다.
- RAG 실제 문서, 실시간 관측 추이, 원천 데이터 통계 타당성·운영 승인, 운영 배포·인증·부하는 이번 범위 밖입니다.
- FILE_MANIFEST는 전달 파일 무결성 목록이며 전자서명/출처 공인 인증이 아닙니다.

## 완료 증거 대응

| 승인 기준 | 증거 |
|---|---|
| 기존173개 유지 | 최종 Python222개 실행에 포함, skip0 |
| DB 제약/초기화/롤백/동시 활성/버전 일관성 | tests/db/test_schema.py, test_repository.py 실PG 통과 |
| 모든 점수·근거 왕복, 쾌적25/427, 가중치별TOP5 | test_repository.py 전체Dataset 동일, test_application.py 3프로필 동일 |
| 실제 API/오류/LLM fallback | backend/tests 6개 및 실제 HTTP/Edge 통과 |
| 프론트/동일배포본/취소/부분자료/비교 | Node8개, 브라우저4개, 전체 화면 흐름, 타입/빌드 통과 |
| 재시작·보존·독립 연결 | 보존된 개발DB의427동/동일버전을 다른 backend PID2개로 확인 |
| 실행/종료/버전전환/전달/비밀 | 본 문서와 backend/README.md, frontend/README.md |
| 독립 리뷰/중요문제 수정 | docs/db_integration_red_team.md, 브라우저4회귀 RED→GREEN |

승인된 로컬 통합 범위는 검증했습니다. 실제 외부 키가 필요한 항목의 미검증 범위와 운영 범위 밖 항목은 위 제한을 유지합니다. 승인된 백엔드 범위만 별도 브랜치/PR로 공유하며 main 자동 병합은 하지 않습니다.

전달 모듈 FILE_MANIFEST.json은 recommendation_service/의 자기 자신을 제외한 추적 파일93개의 SHA-256을 포함합니다. 실제 로컬 DB 자격증명은 추적 파일에서 발견되지 않았으며 .env/가상환경/캐시는 제외했습니다.
