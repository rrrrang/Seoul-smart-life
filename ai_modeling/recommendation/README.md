# 영역별 실자료 스냅샷 추천

경제 → 에너지 → 건강 → 치안을 하나씩 확인한 후 선택한 영역을 합쳐 TOP 5를 계산한다. 기존 영역 평가모델·결과 파일은 수정하지 않는다. 새 모델 학습이나 실시간 추론을 했다고 표시하지 않는다. 추천은 기존 Python 가중합 엔진을 재사용하며 API 키가 필요하지 않다.

## 현재 자료 상태

| 영역 | 입력 | 의미·제약 |
|---|---|---|
| 경제 | `economy/results/economy_scores.json` | 2026년 10월 경제활동 집중도 **추정**. 원천 출근·영업 기반 9월, 공개 고용 8월 |
| 에너지 | `energy/reference/current_scores.csv` | 2026Q2의 **검증용 현재점수 스냅샷**. 혼합 용도 소비량의 조건부 비교이며 주거 가구의 물리적 효율 아님 |
| 건강 | `health/reference/current_scores.csv` | 2026-09-30 기준 **승인 전 상대 참고점수**. 의료·인구·자치구 대기 자료의 기준기간을 각각 보존 |
| 치안 | `safety/results/safety_scores.json` | 경찰 관할권역·자치구 값을 연결한 **참고점수**. 행정동 실제 범죄율 아님 |
| 쾌적 | 미제공 | `null` 유지. 건강·대기 점수를 복사해 만들지 않음 |

각 입력에는 427개 행정동이 있다. 지역 코드는 프로젝트의 **6자리 문자열**이며, 10자리 공식 코드를 자르거나 채워 변환하지 않는다. 지역 마스터는 경제 패키지의 `data/regions.csv`이며 코드 집합·이름·자치구를 대조한다. 원본 자료의 진위와 평가모델 정확성은 이 추천 연결 검증과 별개다.

## 설치

아래 명령은 **Git 저장소 루트**에서 실행한다. Python 3.11 이상을 사용한다.

```powershell
py -3.11 -m venv .venv
.\.venv\Scripts\python.exe -m pip install -r requirements-ai.txt
.\.venv\Scripts\python.exe -m pytest tests/ai_recommendation -q
```

현재 Codex 작업 폴더의 전용 Git 사본에서는 기존 가상환경을 사용한다.

```powershell
cd C:\Users\human\Desktop\Seoul_Smart_Life\.publish-repo
..\.venv311\Scripts\python.exe -m pytest tests/ai_recommendation -q
```

## 1. 경제부터 추천

```powershell
python -m ai_modeling.recommendation --target-month 2026-10 --domains economy
```

경제 외 가중치는 명시적으로 0이다. 입력이 없는 영역을 임의로 보충하거나 자동 기본 가중치 1로 끼워 넣지 않는다. 이 고정 제공본의 적용월은 2026-10이며, 어떤 영역을 선택하든 다른 제공월을 요청하면 실패한다. 이는 과거 분기 원천자료를 현재 관측이라고 표시한다는 뜻이 아니다.

## 2. 에너지 추천

```powershell
python -m ai_modeling.recommendation --target-month 2026-10 --domains energy --allow-provisional
```

해시를 확인한 제공본의 `reference/current_scores.csv`를 사용한다. 기존 `EnergyScoringService`를 실행하거나 모델을 재학습하는 기능은 아니다. 기준기간 2026Q2와 승인 전 표시는 결과에 유지한다.

## 3. 건강 추천

```powershell
python -m ai_modeling.recommendation --target-month 2026-10 --domains health --allow-provisional --allow-context-scores
```

자치구 대기 자료가 포함되므로 참고 자료 연결을 명시적으로 허용해야 한다. 물질 단위 미확인·부분 고령 정보·원자료 기준기간은 출력 메타데이터에 보존한다. 질병 위험도나 도보 접근성으로 설명하지 않는다.

## 4. 치안 추천

```powershell
python -m ai_modeling.recommendation --target-month 2026-10 --domains safety --allow-context-scores
```

행정동의 실제 관측값으로 간주하지 않는다. `calculated_draft`, 원래 품질 검토 표식, 원천별 공간 단위를 유지한다. 관할 기반 동점 지역은 코드 순으로 정렬되며 이를 서로 다른 동별 실제 범죄 수준 차이로 해석하지 않는다.

## 5. 준비된 네 영역을 합쳐 추천

```powershell
python -m ai_modeling.recommendation --target-month 2026-10 --domains economy energy health safety --allow-provisional --allow-context-scores
```

경제 1, 에너지 1, 건강 2, 치안 3으로 개인화하려면:

```powershell
python -m ai_modeling.recommendation --target-month 2026-10 --domains economy energy health safety --weights economy=1 energy=1 health=2 safety=3 --allow-provisional --allow-context-scores
```

가중치는 음수·비유한값·합계 0을 거부한다. TOP K는 1~5다. 결측은 가중치가 양수이거나 최저점수 조건에 필요한 영역에서만 제외 사유다. 동점은 반올림 전 점수 다음 `region_code` 오름차순이다.

## 점수 필드 해석

| 필드 | 의미 |
|---|---|
| `category_scores` | 원본 영역별 0~100점. 자료 없는 영역은 `null` |
| `domain_points_20` | 원본 점수를 5로 나눈 영역별 0~20점. 원본 점수는 변경하지 않음 |
| `selected_total_points` | 선택한 영역의 20점 환산값 합계 |
| `selected_max_points` | 선택한 양수 가중치 영역 수 × 20. 네 영역이면 **80점 만점** |
| `personalized_score_100` | 선택한 영역의 사용자 가중치를 정규화한 0~100 추천점수. 전체 다섯 영역 평가가 아님 |
| `five_domain_total_points` | 다섯 점수가 모두 있을 때만 합계 100점. 현재는 쾌적이 없어 **null** |
| `domain_metadata` | 출처 파일·해시·원천기간·원본 공간 단위·추정/시범 상태·원래 품질 표식 |
| `snapshot_version`, `file_hashes` | 동일 입력 제공본을 식별하고 재현하기 위한 값 |

강점·약점은 선택한 영역 내 상대 비교다. 하나의 영역만 선택했거나 동점이라면 추천 대상의 장단점이 뚜렷하다는 뜻이 아니다. 경제는 업무 집중도이므로 점수가 높다고 모든 사람에게 주거 적합성이 높다고 단정할 수 없다.

## 백엔드 함수 호출

```python
from ai_modeling.recommendation import load_snapshot_dataset, recommend_snapshots

dataset = load_snapshot_dataset(
    "ai_modeling", target_month="2026-10",
    domains=["economy", "energy", "health", "safety"],
    allow_provisional=True, allow_context_scores=True,
)
result = recommend_snapshots(
    dataset, weights={"economy": 1, "energy": 1, "health": 2, "safety": 3},
    top_k=5, min_scores={"safety": 70},
)
response_json = result.model_dump(mode="json")
```

`min_scores`는 원본 100점 척도다. 자료 없는 `comfort`에 양수 가중치나 조건을 요청하면 오류이며 몰래 제거하지 않는다. 사용자가 쾌적을 선호한다면 아직 지원할 수 없다고 안내해야 한다.

FastAPI·DB·프론트는 변경하지 않았다. 기존 Mock/LLM 모듈도 `services/ai_recommendation/`에 포함하지만, 실제 스냅샷의 공간 단위·추정·시범 메타데이터를 기존 Mock용 설명 입력으로 무작정 변환해서는 안 된다. 이번 제공본은 우선 결정적 추천과 근거 데이터의 연결 범위다. 실제 스냅샷용 LLM 설명 통합은 이 메타데이터를 보존하는 계약으로 별도 확인해야 한다.

## 결과와 보고서

- 단계별 실행 결과: `examples/snapshot_results/`
- 작업 보고서: `docs/recommendation_snapshot_report.md`
- 코드: `services/ai_recommendation/snapshot_service.py`
- 테스트: `tests/ai_recommendation/test_snapshots.py`
- CLI: `examples/recommend_snapshot_demo.py`

`--output NEW_FILE.json`으로 JSON을 저장할 수 있다. 기존 파일과 원본 모델링 디렉터리 안에는 출력하지 않는다. 실제 문서를 만들지 않았고 RAG는 이번 추천 연결에 사용하지 않았다.
