# AGENTS.md

## Project
대한민국에서 열리는 AI 관련 공모전·해커톤·경진대회 공고를 웹에서 검색해
정규화·검증한 뒤, 사용자에게 요약 메일로 보내는 LangGraph 에이전트를 만든다.

## Product goal
사용자가 여러 사이트를 따로 뒤지지 않아도
- 현재 접수 중인 AI 공모전·해커톤을 한 통의 메일로 받아보고
- 대상(학생/일반/스타트업/개발자)과 마감일을 한눈에 확인하고
- 메일 속 링크로 원문 공고에 바로 이동할 수 있어야 한다.

## Primary user scenarios
1. 사용자가 "이번 달 AI 해커톤"을 메일로 받고 싶다.
2. 사용자가 "학생 대상" 공모전만 받고 싶다.
3. 사용자가 마감 임박(오늘·이번 주) 공고를 먼저 보고 싶다.
4. 사용자가 메일에서 원문 링크를 눌러 바로 신청 페이지로 가고 싶다.

## Non-negotiable product rules
- 메일의 각 공고에는 title, provider, target, end_date, url 을 반드시 표시한다.
- 마감된 공고(end_date < today)는 메일에 넣지 않는다.
- 중복 공고는 제거한다.
- 오늘 마감 / 이번 주 마감(D-7 이내) 뱃지를 붙이고, 마감 임박 순으로 정렬한다.
- 검색 결과에 없는 공고·링크·날짜를 만들어 내지 않는다(LLM 추측 금지).
- 유효한 공고가 0건이면 빈 메일을 보내지 않고 "이번에는 조건에 맞는 공고가 없습니다" 안내 메일을 보낸다.
- 실제 메일 발송은 사람의 승인(또는 --auto-send 플래그)이 있을 때만 한다. 기본값은 DRY_RUN.

## Tech rules
- LangGraph StateGraph 로 구현하고, 노드 하나는 한 가지 일만 한다.
- 판단(검색어 생성, 비정형 텍스트 → 스키마 추출, 요약 문장)은 LLM 노드가,
  규칙(날짜 정규화, 필수값·마감·중복 검사, 메일 HTML 조립, 발송)은 코드 노드가 맡는다.
- 메일 본문의 링크·날짜·기관명은 LLM이 쓰지 않고 검증된 데이터에서 코드로 조립한다.
- 순환(재검색)은 MAX_ATTEMPTS 로 제한하고, invoke 시 recursion_limit 을 반드시 건다.
- API 키는 .env 로만 읽고 코드·로그·메일에 출력하지 않는다.
- 외부 키가 없어도 offline 모드(fixture)로 전체 그래프가 돌아가야 한다.
- 검증 규칙은 agent/rules.py 에, 외부 연동은 agent/tools.py 에 둔다.

## Commands
- install: pip install -r requirements.txt
- run (offline): python main.py --offline
- run (real search, dry-run): python main.py
- send for real: python main.py --auto-send
- eval: python evals/run_evals.py

## Data quality rules
- 날짜는 YYYY-MM-DD 형식으로 정규화한다. 실패하면 raw_date 에 원문을 보존하고 invalid 로 처리한다.
- provider + title + end_date 조합(공백·대소문자 무시)이 같으면 중복으로 본다.
- url, provider, title, end_date 중 하나라도 비면 invalid 로 처리한다.
- url 은 http(s) 로 시작하는 절대경로여야 한다.
- end_date 가 오늘보다 이전이면 expired=true 로 표시하고 메일에서 제외한다.
- invalid / expired / duplicate 는 버리지 말고 rejected 목록에 reason 과 함께 남긴다.

## Review expectations
- 실행이 끝나면 valid N건, rejected M건(사유별)을 로그로 출력한다.
- 메일은 발송 전에 outbox/ 에 HTML 미리보기를 저장해 사람이 검토할 수 있게 한다.
- 규칙을 바꾸면 evals/run_evals.py 를 다시 실행해 통과 여부를 확인한다.

## Done when
- offline 모드에서 그래프가 끝까지 실행되고 outbox 에 메일 미리보기가 생성된다.
- evals/run_evals.py 의 모든 항목이 PASS 다.
- 유효 공고가 MIN_ITEMS 미만이면 검색어를 바꿔 재검색하는 루프가 동작한다.
- 마감 제외·중복 제거·필수값 검사가 동작한다.
- README 에 설치·실행·메일 설정 방법이 있다.
