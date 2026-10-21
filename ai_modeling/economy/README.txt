경제활력도 현재월 추정 실행 패키지 — 2026년 10월 제공본

이 패키지로 427개 행정동의 경제활력도 추정점수를 재생성하고 서비스에서 읽을 수 있습니다.
출력은 '2026년 10월 경제활동 집중도 추정'입니다. 관측된 10월 실적, 주민 소득,
집값 상승 전망 또는 경제활력도의 상승·하락 예측으로 표시하지 않습니다.
실행·입력 검증을 갖춘 제공본이며, 장기간 운영 성능이 입증되었다는 뜻은 아닙니다.

필수 파일
  economy.py                         점수 추정 함수와 CLI, 재학습 재현
  model_config.json                  고정 계산식·가중치·기준월·입력 및 모델 해시
  models/licensing.joblib            인허가 등록 영업기반용 학습 모델
  data/monthly_inputs.csv            2024-08~2026-09, 427동×26개월 집계 입력
  data/regions.csv                   region_code 6자리, 이름, sigungu_code 5자리, 면적
  results/economy_scores.json        팀원 전달·서비스 조회용 427동 결과
  requirements.txt                   검증한 Python 패키지 버전
  tests/test_economy.py              재현·결측·코드·미래월·신선도 검사
  MODEL_DESIGN.txt                   지표와 모델 설계, 해석, 한계
  validation/monthly_metrics.csv     같은 정비 자료로 비교한 월별 성능
  validation/release_checks.json     기존 점수 재현 및 제공본 점검 결과

실행 (Python 3.12, 터미널의 현재 경로를 이 economy 폴더로)
  python -m pip install -r requirements.txt
  python economy.py predict --as-of 2026-10-21 --target-month 2026-10
  python -m unittest discover -s tests -v

Python 호출
  from economy import estimate, DataContractError
  payload = estimate(as_of="2026-10-21", target_month="2026-10")
  # payload["items"][i]["scores"]["economy"]를 사용합니다.
  # 실패하면 DataContractError가 발생합니다. 실패를 0점으로 바꾸지 마세요.

JSON 계약
  domains / items / is_mock=false / metadata 구조.
  item.region.region_code는 6자리 문자열, sigungu_code는 5자리 문자열입니다.
  item.scores.economy만 값을 채우며 다른 영역은 null입니다.
  item.metadata.economy.grade(정수 1~5), grade_label("3등급" 등)을 함께 제공합니다.
  root.metadata.economy.grade_rules에 구간 정의가 있습니다. 치안과 동일한 20점 간격입니다.
  반올림 전 점수로 80점 이상 1등급, 60점 이상 2등급, 40점 이상 3등급,
  20점 이상 4등급, 20점 미만 5등급입니다. 1등급이 가장 높습니다.
  점수·가중치·모델은 바꾸지 않고 등급만 추가합니다. 결측을 5등급으로 바꾸지 않습니다.
  metadata.economy.status='estimated', target_month, source_periods를 함께 보여주세요.
  메인 백엔드의 10자리 코드 목록과는 직접 조인하면 안 됩니다.
  6자리 프로젝트 코드로 맞춘 조회/병합 계층에서 연결해야 합니다.

화면 표시 예
  '경제활력도 26.3점 · 4등급 · 2026년 10월 추정'
  '사용 자료: 출근 9월, 공개 법인사업장 고용 8월, 등록 영업기반 9월'
  '주민 소득이나 집값 예측을 뜻하지 않습니다.'

운영 시점 제한
  2026-10-21에 확보한 스냅샷입니다. 그 이전 날짜를 기준으로 재사용하면 거부합니다.
  11월 이후에 10월 제공본을 현재값으로 쓰거나 11월을 추정하면 거부합니다.
  10월21일 이후 같은 10월에 재실행해도 원천 스냅샷은 갱신되지 않습니다.
  대상월 1개월 전 출근·인허가, 2개월 전 고용 자료가 모두 있어야 합니다.
  최신 필수값 누락, 중복 동, 10자리 코드, 입력/모델 파일 변경 시 계산을 중단합니다.
  자동 수집 스케줄러나 다음 달 자동 배포는 이 패키지에 포함하지 않았습니다.

동일 모델 재학습 재현
  python economy.py train --output models/licensing_retrained.joblib
  기존 설정으로 인허가 모델만 다시 학습합니다. 기존 배포 파일은 덮어쓰지 않습니다.
  모델 재학습 성공과 다음 달 검증 완료는 별개입니다.

다음 달 갱신 절차
  1) 담당 데이터 엔지니어가 동일 정의/코드로 새 월 입력을 만들고 수집 시점을 기록합니다.
  2) 지역/면적 변경, 결측, 공개범위 변화 및 원천월을 검토합니다.
  3) 복사한 새 제공본에서 target_month, source_months, input_period, 스냅샷일과 해시를 갱신합니다.
     정규화 경계와 세 축 가중치는 유지합니다. 임의 변경은 별도 재검증 대상입니다.
  4) 새 cutoff까지 인허가를 재학습하고, 최근 공개된 월을 전월 유지 기준과 비교합니다.
  5) 별도 후보 모델의 재현·지역·결측·대상월 검사와 점수변화 검토 후 새 모델/해시를 확정합니다.
  6) 새 JSON을 생성하고 종전 제공본을 보관한 뒤 배포합니다.
  외부에서 받은 임의의 joblib 파일을 읽지 마세요. 이 패키지는 해시가 맞는 모델만 읽습니다.

해석과 성능의 중요한 범위
  3개월 재검증 평균 MAE 0.5816점, 전월 최신값 유지 0.6769점 대비 약 14.1% 작았습니다.
  그러나 7월과 8월에는 단순 기준이 더 좋았고, RMSE도 개선되지 않았습니다.
  상승·하락 균형정확도 43.46%로 기준 51.23%보다 낮아 해당 기능은 제공하지 않습니다.
  과거 인허가를 최신 스냅샷으로 복원했으므로 실제 당시 공개본 검증과 동일하지 않습니다.
  '경제력 전반이 확정적으로 높다'가 아니라 3개 관측 기반의 활동 집중도 추정으로 사용하세요.
