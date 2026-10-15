# Seoul Smart Life 백엔드 시작용 코드

가짜(Mock) 데이터로 돌아가는 FastAPI 서버예요. 서울 25개 자치구와 426개 행정동의 목록과 5개 점수를 돌려줘요.

- 자치구 코드: `gnm`(강남구)처럼 3글자 (팀 슬랙 코드표)
- 행정동 코드: `1111051500`(청운효자동)처럼 숫자 10자리 (행정안전부 행정동 코드, `app/data/seoul_dongs.json`)

## 만들어진 API
| 주소 | 하는 일 |
|---|---|
| `GET /api/health` | 서버가 살아 있는지 확인 |
| `GET /api/regions` | 25개 자치구 목록 |
| `GET /api/regions?level=dong` | 426개 행정동 목록 |
| `GET /api/regions?level=dong&parent=jno` | 종로구의 행정동 목록 |
| `GET /api/regions/gnm` | 강남구 정보 (행정동 코드도 가능) |
| `GET /api/regions/gnm/scores` | 강남구 5개 점수 (가짜, 행정동 코드도 가능) |
| `GET /api/compare?codes=gnm,map` | 여러 지역(2~5개) 점수 비교 (가짜, 구·동 섞어도 가능) |

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
| `app/mock_data.py` | 25개 구·426개 동 목록과 가짜 점수 |
| `app/data/seoul_dongs.json` | 서울 행정동 426개 (코드, 이름, 소속 구) |
| `requirements.txt` | 설치할 프로그램 목록 |
