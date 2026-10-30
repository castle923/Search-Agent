---
name: qa-deadline-links
description: 공고의 날짜, 링크, 누락 필드, 중복, 마감 여부를 검증할 때 사용
---

# Goal
메일에 들어갈 공고 데이터의 신뢰성을 코드로 검증한다.

# Trigger
- validate 노드 (매 검색 라운드마다)
- review 노드 (메일 발송 직전)
- rules.py 를 수정했을 때

# Checks
- end_date 파싱 실패 여부 → bad_date
- 필수 필드(title, provider, end_date, url) 누락 → missing_field
- url 이 http(s) 절대경로인지 → bad_url
- 현재 날짜 기준 마감 여부 → expired
- 중복 공고(provider + title + end_date) → duplicate

# Procedure
1. candidates 를 읽는다.
2. rules.validate_items(candidates, today) 실행
3. valid / rejected 를 나누고 사유별로 개수를 센다.
4. valid 는 마감 임박 순으로 정렬하고 뱃지(오늘 마감, 이번 주 마감)를 붙인다.
5. 결과를 로그로 남긴다.

# Severity
- P0: 마감된 공고 또는 링크 없는 공고가 메일에 포함됨 (발송 차단)
- P1: 중복 공고, 날짜 형식 불일치
- P2: target/category 누락 등 경미한 표시 문제

# Output format
1. summary (valid N / rejected M)
2. 사유별 rejected 개수 표
3. P0 가 1건이라도 있으면 발송 중단
