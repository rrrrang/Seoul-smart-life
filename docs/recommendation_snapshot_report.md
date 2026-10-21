# 실제 점수 스냅샷 기반 추천 연결 작업 보고서

작성일: 2026-10-21
입력 저장소: https://github.com/rrrrang/Seoul-smart-life
확인한 입력 기준 커밋: `894d022`
개발·검증 환경: Python 3.11.17
결론: 현재 제공된 경제·에너지·건강·치안 4개 영역을 각각 또는 함께 추천할 수 있다. 쾌적은 자료가 없어 미연결이다. 전체 5대 영역 서비스나 실제 데이터용 LLM 설명의 완성을 뜻하지 않는다.

## 1. 요청과 수행 범위

`ai_modeling/`의 실제 제공 데이터를 가져와 추천 모델을 하나씩 연결하고, 영역별 20점 표시 및 파일 위치를 정리했다. 이미 만들어진 영역 평가모델을 다시 학습하지 않고, 제공된 점수 스냅샷을 검증한 뒤 기존 Python 개인화 가중합 엔진을 재사용했다.

경제·에너지·건강·치안의 원본 코드·모델·입력·결과 파일, 백엔드·프론트·DB 파일은 변경하지 않았다. `.joblib` 파일을 역직렬화하거나 실행하지 않았으며 API 키·개인 환경 파일도 추가하지 않았다.

## 2. 영역별 결과

| 순서 | 영역 | 입력 | 범위·제약 | 427동 연결 |
|---|---|---|---|---|
| 1 | 경제 | `economy/results/economy_scores.json` | 2026-10 경제활동 집중도 추정. 주민 소득·집값·현재월 실제 관측 아님 | 완료 |
| 2 | 에너지 | `energy/reference/current_scores.csv` | 2026Q2 검증용 점수 스냅샷. 혼합용도 비교 시범 결과이며 주거 가구 효율 아님 | 완료, 명시적 시범 허용 필요 |
| 3 | 건강 | `health/reference/current_scores.csv` | 의료·자치구 대기환경의 상대 참고지수. 원천별 기간·부분 고령 정보·물질 단위 미확인 보존 | 완료, 시범·지역참고 허용 필요 |
| 4 | 치안 | `safety/results/safety_scores.json` | 경찰 관할권역·자치구 점수를 행정동에 연결. 실제 동별 범죄 관측 아님 | 완료, 지역참고 허용 필요 |
| 5 | 쾌적 | `.gitkeep`만 존재 | 자료 없음. 건강·대기 점수를 복사해 대체하지 않음 | 미연결, `null` |

에너지·건강의 CSV는 원래 평가모델의 회귀 검증용 출력이다. 본 추천 연결은 이를 명시적인 **고정 스냅샷 입력**으로 재사용한다. 평가 서비스 호출·새 추론·재학습을 수행했다고 표시하지 않는다. 모델의 실시간 실행 연결은 별도 작업이다.

## 3. 점수와 데이터 계약

- 식별자는 프로젝트의 6자리 `region_code` 문자열이다. 10자리 공식 코드의 임의 자르기·채우기를 금지한다.
- 경제의 지역 마스터와 각 영역의 427개 코드 집합, 제공된 이름·자치구를 대조한다.
- 원본 점수 0~100은 보존하고 `domain_points_20 = category_scores / 5`로 표시한다.
- `selected_total_points`는 선택한 영역의 20점 환산값 합계다. 네 영역이면 `selected_max_points=80`이다.
- `personalized_score_100`은 선택 영역 내 가중치 정규화 추천점수다. 다섯 영역 전체 평가점수가 아니다.
- `five_domain_total_points`는 다섯 점수가 모두 있어야 계산한다. 현재는 쾌적이 없어 `null`이다.
- 가중치는 음수·비유한값·합계 0을 거부하고 누락 영역은 0으로 제외한다. 자료 없는 영역에 양수 가중치나 최저점수 조건을 요청하면 오류를 반환한다.
- 최저점수 조건은 원본 0~100 척도다. 결측은 0점이 아니며 필요한 값이 없으면 해당 후보를 제외한다.
- 동점은 반올림 전 점수 다음 `region_code` 오름차순이다.
- 출처 파일·SHA-256·원천기간·원래 공간 단위·추정/시범/검토 상태·원래 메타데이터를 결과에 보존한다. 서로 다른 원천연도를 한 연도로 덮어쓰지 않는다.
- 승인·참고점수 허용 옵션은 실제 `bool`만 받는다. 문자열 `"false"`가 허용으로 오인되지 않는다.
- 제공본의 대상월은 2026-10이다. 다른 월을 현재 제공본의 적용월로 지정하면 오류다. 이전 분기·월 자료를 현재 관측이라고 표기하지 않는다.

## 4. 주요 파일 위치

| 저장소 기준 경로 | 역할 |
|---|---|
| `ai_modeling/recommendation/README.md` | 단계별 실행·점수 해석·백엔드 호출 안내 |
| `ai_modeling/recommendation/__init__.py` | 추천 함수 공개 진입점 |
| `ai_modeling/recommendation/__main__.py` | `python -m ai_modeling.recommendation` 실행 |
| `services/ai_recommendation/snapshot_service.py` | 실제 스냅샷 로딩·검증·근거 보존·20점 환산·추천 조합 |
| `services/ai_recommendation/recommendation.py` | 기존 가중합·정렬·결측 처리·비교 엔진 |
| `services/ai_recommendation/schemas.py` | 기존 공통 Pydantic 계약 |
| `services/ai_recommendation/llm_service.py`, `rag_service.py` 등 | 이전에 개발한 독립 Mock/LLM 기능. 이번 실제 점수 추천은 호출하지 않음 |
| `examples/recommend_snapshot_demo.py` | 가중치·영역·시범 사용 여부를 지정하는 CLI |
| `examples/snapshot_results/economy.json` | 경제 단독 추천 실행 결과 |
| `examples/snapshot_results/energy.json` | 에너지 단독 추천 실행 결과 |
| `examples/snapshot_results/health.json` | 건강 단독 추천 실행 결과 |
| `examples/snapshot_results/safety.json` | 치안 단독 추천 실행 결과 |
| `examples/snapshot_results/combined.json` | 네 영역 동일 비중 추천 실행 결과 |
| `tests/ai_recommendation/test_snapshots.py` | 실제 데이터 연결 회귀·오류·CLI 테스트 29개 |
| `tests/ai_recommendation/`의 다른 테스트 | 이전 추천·LLM·RAG·파이프라인 테스트 82개 |
| `requirements-ai.txt` | 독립 추천 모듈 의존성 |

로컬 Git 사본의 루트는 `C:\Users\human\Desktop\Seoul_Smart_Life\.publish-repo`다. 따라서 추천 진입점 폴더의 전체 경로는 `C:\Users\human\Desktop\Seoul_Smart_Life\.publish-repo\ai_modeling\recommendation`이다.

기존 Codex 작업 폴더의 `services/ai_recommendation/snapshot_service.py`와 테스트에도 같은 구현을 보존했다. 그 위치에서 실행할 때는 `--modeling-dir .publish-repo/ai_modeling`으로 실제 입력 위치를 지정한다.

## 5. 실제 실행 결과

각 영역 단독 실행의 `personalized_score_100`은 그 영역 원본 점수와 같다. 이는 영역별 20점 표시와 구분해야 한다.

| 영역 | 1위 지역 | 추천점수(선택 영역 기준 100) | 영역별 20점 환산 |
|---|---|---:|---:|
| 경제 | 종로1.2.3.4가동 | 100.000000 | 20.000000 |
| 에너지 | 수서동 | 85.710469 | 17.142094 |
| 건강 | 이화동 | 65.026765 | 13.005353 |
| 치안 | 성북동 | 90.416667 | 18.083333 |

네 영역을 동일한 비중으로 선택한 시범 추천:

| 순위 | region_code | 지역명 | 개인화 점수(선택 영역 기준 100) |
|---:|---|---|---:|
| 1 | 200690 | 성수2가제3동 | 67.267192 |
| 2 | 500520 | 등촌제1동 | 65.910544 |
| 3 | 500535 | 등촌제3동 | 65.575614 |
| 4 | 590620 | 사당제1동 | 65.103763 |
| 5 | 590680 | 신대방제2동 | 64.480150 |

이 결과는 해당 제공본과 동일 가중치의 **시범 상대순위**다. 주거비·통근·주택 상태·쾌적이 빠져 있으며 실제 주거 적합성 검증이나 추천 품질의 객관적 정답이 아니다. 업무 집중도가 높은 경제 점수도 모든 거주자에게 좋은 조건은 아니다.

## 6. 실행 방법

Git 사본 루트에서 현재 준비된 Python 3.11 가상환경을 사용할 때:

```powershell
cd C:\Users\human\Desktop\Seoul_Smart_Life\.publish-repo
..\.venv311\Scripts\python.exe -m ai_modeling.recommendation --target-month 2026-10 --domains economy
```

네 영역 시범·참고 점수를 명시적으로 허용해 추천:

```powershell
..\.venv311\Scripts\python.exe -m ai_modeling.recommendation --target-month 2026-10 --domains economy energy health safety --allow-provisional --allow-context-scores
```

새로 clone한 저장소는 `requirements-ai.txt`를 자신의 Python 3.11 가상환경에 설치하고 `python -m ai_modeling.recommendation ...`을 실행하면 된다. 추천 자체에는 OpenRouter 키가 필요하지 않다.

## 7. 테스트와 Red Team 결과

| 검증 | 결과 |
|---|---|
| 추천·LLM 기존 82개 + 새 연결 29개, Python 3.11 | **111개 통과**. Git 사본에서 `111 passed in 6.34s` |
| 저장소 전체 `python -m pytest -q --tb=short` | 수집 단계 미완료. 기존 `ai_modeling/economy/tests/test_economy.py`가 요구하는 `joblib`이 현재 추천 전용 가상환경에 없어 `ModuleNotFoundError` 발생. 전체 저장소 테스트가 모두 통과했다고 주장하지 않음 |
| 단계별 CLI 경제·에너지·건강·치안·네 영역 결합 | 5개 실행 모두 성공, JSON 저장 |
| 원래 `ai_modeling/test_integration.py` | 8개 통과 |
| 원래 치안 계약 테스트, Python 3.12 | 19개 통과 |
| 원래 치안 `build_safety.py --verify`, Python 3.12 | 427행 재계산 일치 |
| 원래 치안 테스트, Python 3.11 | 19개 중 18개 통과, 정확 일치 검사 1개 실패. 아래에 원인 기록 |
| 새 경제·에너지·건강 모델 추론/재학습 | 미실행. 제공 점수 스냅샷을 연결하는 범위 |
| 실제 점수에 대한 LLM·RAG·웹 API 통합 | 미실행. 이번 추천 연결의 범위 밖 |

치안 Python 3.11의 실패 항목은 `test_saved_result_reproduces_from_packaged_statistics`와 그 내부 `verify_saved()`의 정확 JSON 동일성 검사다. 저장 결과와 3.11 재계산 결과 사이에서 수치 차이 58개(행정동 치안 점수 55개 포함)가 관찰됐으며 최대 치안 점수 차이는 약 `1.4210854715202004e-14`다. Python 3.12에서는 동일 검사와 19개 테스트가 모두 통과했다. 추천 연결은 전달된 JSON을 그대로 사용하므로 이 검사 실패를 숨기거나 원본 결과를 덮어써서 없애지 않았다. 평가 담당자에게 런타임별 부동소수점 합산과 정확 동일성 검사의 호환성 검토를 전달해야 한다.

추천 전용 검증 명령은 `python -m pytest tests/ai_recommendation -q`다. upstream 영역 모델들은 별도 버전의 학습·추론 의존성과 환경을 사용한다. 전체 저장소 테스트 수집을 피하도록 프로젝트 전역 테스트 설정을 새로 추가하지 않았으며, 추천 테스트와 원래 영역 테스트 결과를 구분해 기록한다.

독립 리뷰에서 문자열 `"false"`로 시범·참고점수 허용 검사를 우회할 수 있는 문제가 발견됐다. 실제 `bool`만 받도록 수정하고 8개 회귀 사례를 추가했다. 경제가 아닌 영역에서 임의 미래 제공월을 지정할 수 있던 부분도 제공월 검사와 회귀 테스트로 보강했다.

원본 파일 보존, 결측과 0점 구분, 허용하지 않은 영역 값 혼입, 잘못된 지역 코드, 중복 코드, 스냅샷 해시 변경, 쾌적 대체 금지, 부분 점수 표시, 가중치 검증, 기존 출력 파일 덮어쓰기 방지를 점검했다. 정제 CSV 참조 및 고정 스냅샷 추천의 재현성을 확인했으며, upstream 평가모델의 통계적 타당성이나 운영 승인까지 인증한 것은 아니다.

## 8. 남은 작업

1. 쾌적 담당자의 점수·출처·기간·공간 단위 계약을 받아 다섯 영역 전체 추천을 연결한다. 지금은 점수를 만들지 않는다.
2. 백엔드 담당자가 이 함수의 응답을 API에 연결하고 6자리 코드와 10자리 코드 대응을 명시적으로 처리한다.
3. 실제 스냅샷용 LLM 설명에서는 경제 추정·시범·치안 관할참고·여러 원천기간을 보존하도록 설명 계약을 연결하고 검증한다. 기존 Mock 설명만으로 이 검증을 대체하지 않는다.
4. 실제 문서가 준비되면 별도로 RAG 문서 로딩·임베딩·검색을 구현한다.
5. 시범 점수의 운영 승인, 자료 갱신, 실제 추천 유용성 검토는 평가·데이터 담당자와 진행한다.
