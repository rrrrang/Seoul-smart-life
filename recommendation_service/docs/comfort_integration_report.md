# 쾌적 연결 및 가중치 확정 보고서

작업일: 2026-10-21. Git 커밋·스테이징·업로드 없이 로컬 수정만 진행했다. 기존 가중치 계산 엔진은 유지했고 쾌적 입력과 설명·전달 문서를 보완했다.

## 원본 확인

GitHub rrrrang/Seoul-smart-life의 커밋 `f0948c1be6bb945eeddfb47c8b50412f7d8f38e1`에서 쾌적 JSON·월별 CSV·기간 상대순위 CSV·산출 Python 원본을 변경 없이 가져왔다. 로컬 import_receipt.json에 SHA-256과 커밋을 기록했다. 이 영수증은 upstream 운영 승인이나 전자서명이 아니다.

- comfort_scores.json: 25개 자치구, 평가월2026-09, 사용자료기간2024-01~2026-09.
- monthly_scores.csv: 825행, 최신월25개 구. comfort_score=score_rel이며 JSON은 최신 상대점수를 소수점1자리로 저장한다.
- 산출식은 기온·PM2.5·PM10·소음에 영역 내부 가중치를 적용한다. 오존·습도·공원면적은 현재 최종점수에서 제외한다.
- grade_abs는 별도 절대점수의 4단계 라벨이다. 이를 상대점수의 등급으로 사용하거나 임의1~5등급으로 바꾸지 않았다.
- 기간평균 상대순위 CSV는 최신월 JSON과 다른 평가다. 추천에는 최신월 JSON을 사용하며 두 점수를 혼합하지 않았다.
- 원천 공공자료 설명서·직접 인용 URL·운영 승인 자료는 제공되지 않았다. 해당 부재를 메타데이터와 경고에 남겼다.

## 연결 정책

6자리 region_code와 5자리 sigungu_code를 유지한다. 25개 구 점수를 master427행정동에 sigungu_code로 연결한다. 같은 구의 모든 동은 동일한 쾌적 점수를 사용한다. original_spatial_units=['sigungu'], is_dong_observation=false로 원래 공간단위를 보존한다. 실제 동별 관측값이나 도보/거리 정보로 해석하지 않는다. 특히 쾌적을 중시하는 추천에서 동 단위 세밀한 차이를 설명할 수 없다.

allow_provisional=True와 allow_context_scores=True가 모두 필요하다. 배포월2026-10과 실제 평가월2026-09 차이를 경고하고 원천기간을 따로 보존한다. 최신 서대문구 기온 추정 플래그 등 보간 정보를 row_context에 유지했다. 고정 스냅샷을 로딩하며 upstream 모델 재학습이나 추론을 실행하지 않는다.

## 사용자와 확정한 가중치

독립 슬라이더를 유지한다. 실제 비중=슬라이더값/다섯값합계, 종합점수=각영역100점×실제비중의 합. 다섯값 모두20·100·10은 각각20%로 동일한 결과다. 모두0/음수/비유한값은 오류다. 한 영역만 양수면 해당 점수순으로 추천한다. 중요도는 원점수·원래등급을 바꾸거나 최소등급 필터를 의미하지 않는다.

영역별 막대는 category_scores, 종합점수는 personalized_score_100으로 모두100점 기준이다. 설명에서도 /20 병기를 제거했다. domain_points_20 등의 기존 계약은 호환용으로 유지하되 화면에는 쓰지 않는다. 자연어 질문 UI는 제외하고 추천 근거와 주의할 점만 제공한다. LLM 설명은 선택사항이며 API 없이도 추천·기본 설명이 동작한다.

## 변경 파일

| 위치 | 변경 |
|---|---|
| services/ai_recommendation/snapshot_service.py | 구단위 쾌적 검증·연결, 기간·보정·참고값 메타데이터 |
| services/ai_recommendation/snapshot_llm.py | 100점 표시로 설명 통일 |
| tests/ai_recommendation/test_comfort.py | 공간단위·기간·보정·해시·계약 오류·가중치·동점 검증14개 |
| tests/ai_recommendation/test_snapshots.py, test_snapshot_llm.py | 이전 쾌적미제공 가정과 표시 기대값 갱신, 4영역경로 유지 |
| examples/snapshot_results/five_domains_slider_offline.json | 실제5영역 기본설명 실행 결과 |
| backend_handoff/ | 데이터·코드·테스트·슬라이더용 응답예제·100점화면 계약 갱신 |

프로젝트 루트와 .publish-repo 작업 사본, backend_handoff의 소유 모듈에 같은 변경을 반영했다. 이전4영역 예제는 역사적 자료이며 최신 사용은 five_domains_slider_offline.json 또는 handoff fixtures/weights_response_*를 참고한다.

## 검증

- Python3.11 추천 모듈 전체: **166 passed**. 기존152개+신규14개.
- 인수인계 폴더에서 동봉 데이터만으로도 **166 passed**.
- 쾌적 원본해시 변조, 중복/누락/잘못된구코드, bool점수, 최신월수치 불일치, 미래월, 기간/계산상태 불일치 거부.
- 같은비율 가중치가 동일 결과임, 안전단일영역 순위, 모두0/음수 거부, 100점설명, 원본자치구단위 보존 확인.
- 독립 읽기전용 Red Team 검토에서 신규14개 통과 및 추가 blocker 없음 확인.
- 쾌적 포함 실제 OpenRouter 호출은 이번에 미실행. 이전4영역 실제 호출은 사용자가 llm/diagnostics={}를 확인했다. 현재 fixture의 LLM결과는 명시적으로 MockTransport다.

## 아직 완료하지 않은 서비스 작업

FastAPI 연결·슬라이더 API전달·화면 표시·지도 색 기준·자치구집계·전체 지역조회·TOP10·환경 추이는 별도다. 종합점수의1~5등급 구간을 임의 생성하지 않았다. 도메인별 통계척도와 건강/쾌적의 대기지표 중복 영향, 실제 거주추천 유용성, 시범데이터 운영 승인은 평가담당자와 별도 검토해야 한다. RAG 실문서는 여전히 미제공이다.
