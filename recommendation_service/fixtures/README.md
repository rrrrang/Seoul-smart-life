# 계약 응답 예제

## 현재 화면용

- weights_request.json: 독립 슬라이더 각20, top_k5
- weights_response_llm.json: 5영역 실제 스냅샷 추천 + 검증된 LLM 선택의 모의 응답
- weights_response_offline.json: 동일 추천 + API 없는 기본 설명
- recommendation_empty.json: 최소점수에 맞는 결과 없음
- explanation_fallback.json: 인증실패를 재현한 기본 설명

## 기존 자연어 호환용

question_provisional.json, question_confirmed.json, question_needs_confirmation.json, request_confirmed.json, error_authentication.json은 기존 질문 경로 예제다. 현재 UI에서 자연어를 사용하지 않으므로 기본 연동은 weights_*를 참고한다. 쾌적은 이제 제공되므로 needs_confirmation은 미지원 임대료 조건으로 재현한다.

python -m examples.build_contract_fixtures로 생성한다. 점수는 실제 제공 스냅샷이며 LLM은 HTTPX MockTransport다. 실제 OpenRouter가 매번 같은 출력을 만든다는 보장은 없다. 가짜 RAG 문서·실제 API 키·사용자 질문 기록은 포함하지 않았다. fixture는 실제 통신 성공 증거가 아니다.
