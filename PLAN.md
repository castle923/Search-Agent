# PLAN.md

## Task
AI 공모전·해커톤 검색 → 검증 → 메일 발송 LangGraph 에이전트 MVP

## Milestones
| # | 단계 | 산출물 | 성공 기준 |
|---|---|---|---|
| 1 | 표준 스키마·State 정의 | agent/state.py | Contest 필드가 AGENTS.md 와 일치 |
| 2 | 규칙 함수 구현 | agent/rules.py | evals 규칙 테스트 PASS |
| 3 | 도구 연결(검색·LLM·메일) | agent/tools.py | 키 없으면 fixture / dry-run 으로 자동 전환 |
| 4 | 노드 구현 | agent/nodes.py | 노드 1개 = 역할 1개, 입력·출력 모두 State |
| 5 | 그래프 조립 | agent/graph.py | 조건부 엣지 2개(재검색, 리뷰 게이트), 승인 전 interrupt |
| 6 | 평가 실행 | evals/run_evals.py | 전체 PASS, 하네스 OFF 기준선보다 높은 점수 |
| 7 | 문서화 | README.md, checklist.md | 설치·실행·메일 설정 방법 기재 |

## Risks
- 사이트마다 날짜 형식이 다름 (2026.11.30 / 2026년 11월 30일 / ~11/30) → rules.normalize_date 로 흡수, 실패 시 raw_date 보존
- 검색 결과가 블로그·뉴스 재게시라 같은 공고가 여러 번 나옴 → provider+title+end_date 중복 제거
- LLM이 검색 결과에 없는 마감일을 지어낼 수 있음 → 추출 프롬프트에 "없으면 빈 값", 코드에서 필수값 검사
- 이미 끝난 대회가 상위에 노출됨 → expired 제외
- 재검색 무한 루프 → MAX_ATTEMPTS + recursion_limit
- 잘못된 메일이 실제로 발송됨 → DRY_RUN 기본값, review 게이트, 사람 승인 interrupt

## Verification
- python evals/run_evals.py  (규칙 단위 테스트 + offline 전체 그래프 + 하네스 OFF 비교)
- outbox/*.html 을 브라우저로 열어 사람이 확인
- checklist.md 체크
