# 에너지 소비효율 백엔드 전달 폴더

이 폴더 전체를 저장소의 `ai_modeling/energy/`에 넣으세요. 전기·가스 기준 소비 모델 2개와 별도 사용량 전망 모델 2개를 포함합니다. 다른 영역 폴더나 원래 분석 프로젝트 없이 실행할 수 있습니다.

Python 3.10 환경에서 이 폴더의 `requirements.txt`를 설치합니다.

```powershell
python -m pip install -r requirements.txt
python predict.py --region-code 110515 --mode current
python predict.py --region-code 110515 --mode forecast
python verify_package.py
```

저장소 최상위에서 백엔드가 호출하는 예시입니다. 서비스는 앱 시작 시 한 번 만들고 재사용하세요.

```python
from ai_modeling.energy import EnergyScoringService

service = EnergyScoringService()
current = service.get_region_scores("110515", mode="current")
future = service.get_region_scores("110515", mode="forecast")
# current["energy_score"], current["energy_grade"]
```

`region_code`는 6자리 문자열, `region_name`은 행정동명, `sigungu_name`은 자치구명입니다. 기존 10자리 코드도 호출에 사용할 수 있습니다. 등급은 아주좋음·좋음·기본·나쁨·아주나쁨이며 고정된 기존 경계를 적용합니다. 계산 보류는 JSON null이며 0점으로 채우지 않습니다.

`evaluate_latest()`는 현재 427동, `forecast_latest()`는 2026Q4 시범 예상 427동의 DataFrame을 반환합니다. reference 폴더는 검증용이며 모델이 결과를 읽어 반환하지 않습니다. 이 영역 점수만 반환하며 추천 순위나 다른 영역 종합점수는 계산하지 않습니다.

저장소 최상위에서 직접 정제 CSV를 넣는 예시입니다.

```python
from pathlib import Path
import pandas as pd
import ai_modeling.energy as domain_module
from ai_modeling.energy import EnergyScoringService

folder = Path(domain_module.__file__).resolve().parent
service = EnergyScoringService()
data = pd.read_csv(folder / "examples/energy_input.csv", dtype={"region_code": str, "source_group": str})
scores = service.score_energy(data)
```

연료별 기준 소비량과 실제 소비량(미래에는 별도 전망량)을 비교해 0~100점으로 만들고 고정 CRITIC 비중으로 합산합니다. 같은 원량을 공유하는 source_group과 학습 행 제외 규칙을 유지합니다. 고정 모델의 미래 검증은 보류입니다.

현재·미래 모두 정식 승인 전 시범 결과입니다. 미래 응답의 production_approved와 energy_validation_passed는 false를 유지합니다. 이번 폴더 분리는 모델 재학습이나 예측 정확도 개선 작업이 아닙니다.

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
