경제·치안 점수 전달 (2026-10-21)

region_code는 프로젝트 6자리 행정동 코드 문자열입니다.
sigungu_code는 5자리 자치구 코드 문자열입니다.
공식 원천 표의 10자리 region_code와 구분합니다. 6자리 값은 공식 프로젝트 기준표의 region_short_code 값과 같습니다.

서비스에서 읽을 파일
  economy/results/economy_scores.json
  safety/results/safety_scores.json

둘 다 domains/items 구조이며 행정동 427개가 들어 있습니다.
items[].region에 코드·이름, items[].scores에 영역 점수,
items[].metadata에 원천기간·산출방식·주의사항이 있습니다.
다른 담당자의 점수는 null입니다. null을 0으로 바꾸면 안 됩니다.

두 영역을 함께 읽는 방법 (저장소 루트에서 Python 실행)
  from ai_modeling.load_scores import load_scores
  payload = load_scores(target_month="2026-10")

load_scores는 427개 동의 코드·자치구·이름을 대조하고 경제와 치안 점수를 합쳐 읽습니다.
종합 추천점수나 사용자 가중치를 계산하지 않습니다.
target_month는 서비스에서 표시하려는 월입니다. 파일에 저장된 경제 추정월과 다르면 실패합니다.
과거 10월 결과를 11월 현재값으로 자동 재사용하지 않습니다.

검증
  python ai_modeling/test_integration.py
각 영역별 실행·검증·갱신 방법은 해당 폴더의 README를 참고하세요.

해석
경제: 현재월의 업무·법인 공개사업장 고용·생활서비스 영업 기반 밀도를 0~100점으로 추정합니다.
      실제 관측값이 아니므로 estimated 표시를 유지합니다. 상승·하락 예측 기능은 제공하지 않습니다.
치안: 범죄 80%, 방범 CCTV 10%, 경찰시설 10%의 통계적 상대점수와 5등급입니다.
      자료의 관할권역 또는 자치구 값을 행정동에 연결합니다. 동별 실제 범죄율로 표현하면 안 됩니다.

현재 백엔드와 연결
2026-10-21 확인한 backend/app/mock_data.py는 10자리 행정동 코드와 별도 scores 사전을 사용합니다.
이 폴더의 업로드만으로 웹 API가 자동으로 새 점수를 읽는 것은 아닙니다.
백엔드 담당자는 6자리 지역 목록을 사용하고 위 load_scores 결과를 기존 점수 조회에 연결해야 합니다.
10자리 목록을 계속 써야 한다면 data/processed/서울_지역 엑셀용.csv의 명시적인 10↔6자리 대응을 사용하세요.
코드를 자르거나 자릿수를 임의로 채워 변환하면 안 됩니다. 공개 전달 JSON은 6자리 계약을 유지합니다.
기존 백엔드와 다른 팀원 영역 파일은 이 업로드에서 수정하지 않았습니다.

기존 실험 보고서·전국 원본·중간 파일·이전 모델은 D드라이브에 보관하고 업로드에서 제외했습니다.
