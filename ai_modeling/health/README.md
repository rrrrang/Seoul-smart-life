# 건강·의료 환경 백엔드 전달 폴더

이 폴더 전체를 저장소의 `ai_modeling/health/`에 넣으세요. 의료·응급·환경 점수 설정과 대기 전망 모델 3개를 포함합니다. 다른 영역 폴더나 원래 분석 프로젝트 없이 실행할 수 있습니다.

Python 3.10 환경에서 이 폴더의 `requirements.txt`를 설치합니다.

```powershell
python -m pip install -r requirements.txt
python predict.py --region-code 110515 --mode current
python predict.py --region-code 110515 --mode forecast
python verify_package.py
```

저장소 최상위에서 백엔드가 호출하는 예시입니다. 서비스는 앱 시작 시 한 번 만들고 재사용하세요.

```python
from ai_modeling.health import HealthScoringService

service = HealthScoringService()
current = service.get_region_scores("110515", mode="current")
future = service.get_region_scores("110515", mode="forecast")
# current["health_score"], current["health_grade"]
```

`region_code`는 6자리 문자열, `region_name`은 행정동명, `sigungu_name`은 자치구명입니다. 기존 10자리 코드도 호출에 사용할 수 있습니다. 등급은 아주좋음·좋음·기본·나쁨·아주나쁨이며 고정된 기존 경계를 적용합니다. 계산 보류는 JSON null이며 0점으로 채우지 않습니다.

`evaluate_latest()`는 현재 427동, `forecast_latest()`는 2026Q4 시범 예상 427동의 DataFrame을 반환합니다. reference 폴더는 검증용이며 모델이 결과를 읽어 반환하지 않습니다. 이 영역 점수만 반환하며 추천 순위나 다른 영역 종합점수는 계산하지 않습니다.

저장소 최상위에서 직접 정제 CSV를 넣는 예시입니다.

```python
from pathlib import Path
import pandas as pd
import ai_modeling.health as domain_module
from ai_modeling.health import HealthScoringService

folder = Path(domain_module.__file__).resolve().parent
service = HealthScoringService()
medical = pd.read_csv(folder / "examples/health_input.csv", dtype={"region_code": str, "sigungu_code": str})
air = pd.read_csv(folder / "examples/air_quarter_input.csv", dtype={"sigungu_code": str})
scores = service.score_health(medical, air)
```

인구 1만명당 의료자원과 응급자원 보유 점수의 엔트로피 가중합, 대기 환경 안전점수의 CRITIC 가중합을 각각 만든 뒤 50:50으로 합칩니다. 미래에는 의료·인구·응급 조건을 유지하고 대기만 전망합니다. 질병 확률·실제 도보시간 예측이 아니며 전체 미래 건강 정확도는 검증되지 않았습니다. 27동의 부분 고령정보와 금천구 10동의 미래 대기 보완 사용 표식을 유지합니다.

현재·미래 모두 정식 승인 전 시범 결과입니다. 미래 응답의 production_approved와 health_validation_passed는 false를 유지합니다. 이번 폴더 분리는 모델 재학습이나 예측 정확도 개선 작업이 아닙니다.

| 경로 | 역할 |
|---|---|
| models/ | 이 영역의 저장 모델과 점수·전망 설정 |
| config/ | 등급·자료 시점·입력 조건 |
| data/ | 이 영역 계산에 필요한 정제 입력 |
| service.py, runtime/ | 호출 코드·모델 추론·점수 계산 |
| examples/, schema/ | 입력 예시·실제 응답·입출력 명세 |
| reference/, verify_package.py | 기존 점수 일치·결측·누수·독립 실행 검증 |
| MANIFEST.json | 폴더 내부 파일 변경 검사 |

원래 프로젝트 경로를 참조하지 않습니다. models·config·동봉 data를 변경하면 다시 내보내고 검증하세요. 추가 입력은 파일을 덮어쓰지 않고 서비스 메서드의 인자로 전달할 수 있습니다. 실제 HTTP API 연결은 백엔드에서 구현합니다.
