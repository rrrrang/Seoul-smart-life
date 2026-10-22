# 추천 DB API 실행

새 실데이터 경로는 `/api/recommendation`입니다. 아래 기존 `/api/*` 문서는 호환용 Mock 경로이며 새 화면에서는 사용하지 않습니다.

저장소 루트에서:
```powershell
& .\.venv-db\Scripts\python.exe -m uvicorn backend.app.main:app --env-file .env.recommendation --host 127.0.0.1 --port 8000
```
`cd backend` 후 `uvicorn app.main:app`도 지원합니다(동일 환경변수 필요). 앱 시작은 DDL/적재를 실행하지 않습니다. DB 초기화/적재는 별도 CLI입니다.

| 메서드 | 경로 | 용도 |
|---|---|---|
| GET | /api/recommendation/status | 활성 배포본/영역/DB 상태 |
| GET | /api/recommendation/districts | 동별 점수의 구별 평균, 유효 개수 |
| GET | /api/recommendation/regions | 6자리 행정동 명부 |
| GET | /api/recommendation/scores | 100점 원점수/개인화 점수 |
| GET | /api/recommendation/regions/{region_code} | 원천 기간/출처/공간 단위 |
| POST | /api/recommendation/recommendations | weights, top_k(1~5), 선택 sigungu_code/release_id |
| POST | /api/recommendation/compare | weights, region_codes(2~5), release_id |
| POST | /api/recommendation/explanations | weights, 선택 region_codes, release_id |

GET districts/scores의 weights는 다섯 키 JSON query입니다. 모든 응답의 snapshot_version을 다음 요청의 release_id로 전달하여 배포본을 고정합니다. 잘못된 입력422, 없는 지역/버전404, DB 장애/활성본 없음503입니다. DB 장애 시 Mock으로 대체하지 않습니다. LLM 키가 없거나 통신에 실패하면 서버에서 계산한 사실 기반 기본 설명을 반환합니다. OpenRouter 키는 서버 환경변수에만 둡니다.

---

# Seoul Smart Life 백엔드 시작용 코드

서울 25개 자치구와 427개 행정동의 목록과 5개 점수를 돌려주는 FastAPI 서버예요.

- **치안(safety) 점수는 진짜**예요. 동현님 치안 점수 결과(`services/safety_scoring/results/safety_scores.json`)를 `app/data/safety_scores.json`에 옮겨 왔어요.
  - 행정동: 그 점수 그대로 (소수 첫째 자리까지) + `safety_grade`(1~5등급, 1등급이 가장 좋음)
  - 자치구: 소속 행정동 점수의 평균 (`safety_grade`는 `null`)
- 나머지 4개(economy, energy, comfort, health)는 아직 **가짜 점수**예요. 응답의 `mock_domains`에 가짜인 영역이 적혀 있어요.

- 자치구 코드: `11680`(강남구)처럼 숫자 5자리 (시군구 코드, 팀 DB의 `sigungu_code`와 같음). 예전 3글자 코드(`gnm`)로 불러도 돼요
- 행정동 코드: `1111051500`(청운효자동)처럼 숫자 10자리 (팀 기준표 `서울_지역_기준.csv`의 427개, `app/data/seoul_dongs.json`)

## 만들어진 API
| 주소 | 하는 일 |
|---|---|
| `GET /api/health` | 서버가 살아 있는지 확인 |
| `GET /api/regions` | 25개 자치구 목록 |
| `GET /api/regions?level=dong` | 427개 행정동 목록 |
| `GET /api/regions?level=dong&parent=11110` | 종로구의 행정동 목록 |
| `GET /api/regions/11680` | 강남구 정보 (행정동 코드도 가능) |
| `GET /api/regions/11680/scores` | 강남구 5개 점수 (치안만 진짜, 행정동 코드도 가능) |
| `GET /api/scores` | 25개 자치구 점수 한 번에 (순위·지도용) |
| `GET /api/scores?level=dong` | 427개 행정동 점수 한 번에 (`&parent=11110`으로 구 하나만도 가능) |
| `GET /api/compare?codes=11680,11440` | 여러 지역(2~5개) 점수 비교 (치안만 진짜, 구·동 섞어도 가능) |

## 윈도우에서 실행하기 (처음 한 번)
1. **Python 3.11 설치**: https://www.python.org/downloads/ 에서 받아 설치해요.
   설치 첫 화면에서 **"Add python.exe to PATH" 체크박스를 꼭 체크**하세요.
2. **VS Code 설치**: https://code.visualstudio.com/
3. 이 폴더(`seoul-backend-starter`)를 바탕화면 같은 곳에 압축 해제해요.
4. VS Code를 열고 **파일 → 폴더 열기**로 이 폴더를 열어요.
5. VS Code 위쪽 메뉴에서 **터미널 → 새 터미널**을 눌러요.
6. 터미널에 아래를 한 줄씩 입력해요.

```
py -3.11 -m venv .venv
.venv\Scripts\activate
pip install -r requirements.txt
uvicorn app.main:app --reload
```

`activate`에서 빨간 오류(스크립트 실행 금지)가 나면 아래 한 줄을 먼저 입력하고 다시 해요.
```
Set-ExecutionPolicy -Scope CurrentUser RemoteSigned
```

## 잘 됐는지 확인
- 브라우저에서 http://127.0.0.1:8000/docs 를 열어요.
- API 목록 화면이 나오면 성공이에요. 항목을 누르고 **Try it out → Execute**를 누르면 결과를 볼 수 있어요.
- 서버를 끌 때는 터미널에서 `Ctrl + C`를 눌러요.

## 다음부터 실행할 때
```
.venv\Scripts\activate
uvicorn app.main:app --reload
```

## 파일 설명
| 파일 | 내용 |
|---|---|
| `app/main.py` | API 주소들 |
| `app/mock_data.py` | 25개 구·427개 동 목록과 점수 (치안은 진짜) |
| `app/data/seoul_dongs.json` | 서울 행정동 427개 (코드, 이름, 소속 구) |
| `app/data/safety_scores.json` | 행정동 427개 진짜 치안 점수와 등급 |
| `requirements.txt` | 설치할 프로그램 목록 |
