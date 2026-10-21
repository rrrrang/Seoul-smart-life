# 슬라이더 추천 응답 계약

## 기본 응답

fixtures/weights_request.json → fixtures/weights_response_llm.json 또는 weights_response_offline.json. recommendation과 explanation으로 구성된다. JSON schema는 contracts/*.schema.json을 참고한다. 자연어 요청의 provisional/confirmed/needs_confirmation 상태는 현재 UI에 필요하지 않다. 데이터의 시범·미승인 상태는 별도 보존한다.

| 필드 | 화면/서버 사용 |
|---|---|
| recommendation.items[].rank | 순위. 동점은 region_code 오름차순 |
| region_code / sigungu_code | 6자리/5자리 문자열. 이름으로 조인하거나 10자리로 변환하지 않음 |
| category_scores | 영역별 원점수, 각각100점. 막대에 사용 |
| personalized_score_100 | 사용자 가중치를 정규화한100점 종합점수 |
| normalized_weights | 0~1실제 비중. 화면에서 ×100으로 표시 |
| strengths/weaknesses, contributions | 상대 강약점·종합점수 기여. 서울 평균이나 인과관계를 뜻하지 않음 |
| selected_domains / unavailable_domains | 현재 계산에 사용한 영역과 로드하지 않은 영역 |
| explanation.items[].advantages/disadvantages | 추천 근거와 주의할 점. 100점 기준 설명 |
| explanation.items[].limitations/citations | 지표 한계와 실제 검색 문서 인용. citations가 비어 있어도 점수 출처는 있음 |
| items[].domain_metadata | 원본 공간단위·기준기간·출처파일·해시·추정/보정·승인상태. 상세 보기용 |
| snapshot_version / file_hashes / target_month | 재현성·배포본 식별. 평가기간은 각 domain_metadata.source_periods를 우선 표시 |

domain_points_20/selected_total_points/selected_max_points/five_domain_total_points는 호환용이다. 화면에는 category_scores/personalized_score_100을 사용한다. 모든 영역 점수가 있어도 서로 다른 기간·원천 단위라는 한계는 사라지지 않는다. 건강 지표 일부 대기환경과 쾌적 지표가 겹칠 수 있으며 중복 영향은 평가 담당 검토 대상이다.

## 설명 상태

- llm: 실제 또는 모의 테스트의 LLM 영역/근거 선택이 검증을 통과했다. 최종 문장은 계산값으로 Python이 생성한다.
- fallback: LLM 미설정 또는 실패/잘못된 출력. 기존 추천을 유지한다.
- empty: 조건에 맞는 지역 없음. 임의 지역으로 채우지 않는다.

화면에 테스트 fixture의 llm상태를 실제 통신 성공 증거로 사용하지 않는다. 실제 OpenRouter 검증은 별도 수행한다.

## 검증·오류

가중치는 음수가 아닌 유한값이고 양수 합계가 필요하다. top_k는 실제 정수1~5이다. 모두0이면 입력오류로 안내한다. 누락점수는0이 아니며 선택 영역의 필수점수 결측 지역은 excluded에 포함된다. 선택 조건에 따라 TOP5보다 적게 반환될 수 있다.

권장 HTTP 매핑(라이브러리 자체는 HTTP 응답을 만들지 않음): 사용자 잘못된 입력422, 데이터 경로·해시·키 설정 문제503, 외부 timeout504, 기타 외부 문제502/503. 설명 실패는 정상 추천+fallback으로 제공할 수 있다. 원시 예외/공급자 본문/키/전체 질문을 외부 노출하지 않는다. LLMError.as_dict()의 안전한 code/status_code/retry_after/details만 사용한다.

## 데이터 의미

경제는 집중도 추정, 에너지는 조건부 총량 비교 참고값, 건강은 의료자원·대기 등의 상대 참고지수, 치안은 관할권역·자치구 참고값이다. 쾌적은 자치구2026-09 상대점수이며 동별 관측값이나 절대 환경등급이 아니다. 쾌적 monthly의 grade_abs는 절대점수용 등급으로 현재 상대점수 등급에 복사하지 않는다. 원천 자료 설명서 미제공 플래그를 유지한다. source_group 식별자는 내부에서 보존하고 추천 응답에 노출하지 않는다.

구체적인 종합점수1~5등급 구간, 자치구 평균, 최소등급 필터는 아직 정의하지 않았다. 임의로 계산했다고 표시하지 않는다. 점수나 순위를 LLM이 계산하지 않는다.

## 호환용 자연어 계약

question_result.schema.json과 question_*.json은 기존 경로의 회귀·호환 자료다. 이 경로의 provisional은 사용자 미확인, confirmed는 확인 요청 적용, needs_confirmation은 미지원 조건을 뜻한다. 사용자 확인과 데이터 운영 승인은 서로 다르다. 현재 기본 화면에서는 이 경로를 호출하지 않는다.
