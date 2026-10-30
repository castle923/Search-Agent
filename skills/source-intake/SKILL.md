---
name: source-intake
description: 웹 검색 결과에서 공모전·해커톤 공고를 추출해 표준 스키마로 정규화할 때 사용
---

# Goal
검색 결과(제목·URL·본문 일부)를 표준 스키마의 공고 목록으로 변환한다.

# Trigger
- extract 노드가 실행될 때마다
- 새 검색 소스(예: 다른 검색 API, 특정 사이트 RSS)를 추가할 때

# Standard schema
- title        공고명
- provider     주최·주관 기관
- category     공모전 | 해커톤 | 경진대회 | 기타
- target       학생 | 일반 | 스타트업 | 개발자 | 기타
- start_date   접수 시작일 (YYYY-MM-DD, 없으면 빈 값)
- end_date     접수 마감일 (YYYY-MM-DD)
- url          원문 공고 링크 (절대경로)
- source_name  검색 소스 이름 (tavily | fixture ...)
- raw_date     정규화 전 날짜 원문

# Procedure
1. 검색 결과 1건씩 읽는다.
2. 공고가 아닌 결과(뉴스 해설, 수상작 발표, 지난 대회 후기)는 버린다.
3. 각 필드를 본문에서 그대로 찾아 채운다. 본문에 없으면 빈 값으로 둔다(추측 금지).
4. 날짜는 원문을 raw_date 에 두고, rules.normalize_date 로 end_date 를 만든다.
5. url 은 검색 결과의 url 을 그대로 쓴다(새로 만들지 않는다).
6. 결과를 validate 노드로 넘긴다.

# Quality bar
- 필수 필드(title, provider, end_date, url) 누락 비율이 30%를 넘으면 검색어가 나쁜 것으로 보고 재검색을 고려한다.
- 날짜 파싱 실패 건은 rejected(reason=bad_date)로 남기고 raw_date 를 보존한다.

# Deliverables
- candidates 목록 (State)
- 추출 실패 사유 로그
