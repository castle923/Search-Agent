---
name: mail-release
description: 조립된 메일이 발송 가능한 수준인지 최종 점검할 때 사용
---

# Goal
잘못된 메일이 실제 사용자에게 나가지 않도록 발송 직전에 점검한다.

# Trigger
- review 노드 (compose 다음, send 이전)

# Required checks
- 제목이 "[AI 공모전 알림] YYYY-MM-DD · N건" 형식인가
- 본문의 공고 수 = valid 공고 수 인가
- 본문의 모든 링크가 valid 목록의 url 인가 (지어낸 링크 없음)
- 마감된 공고가 본문에 없는가
- API 키 등 비밀 값이 본문에 없는가
- 0건일 때 안내 문구가 들어갔는가

# Procedure
1. mail_html 과 valid 목록을 비교한다.
2. 실패 항목을 review_errors 에 적는다.
3. review_errors 가 비어 있으면 approve(사람 승인) 단계로, 있으면 abort 로 보낸다.
4. 승인 전에 outbox/ 에 미리보기를 저장한다.

# Output
- ready / not ready 판정
- review_errors 목록
