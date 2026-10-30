"""그래프 State 정의 — 노드와 노드 사이를 오가는 '택배 상자'.

AGENTS.md 의 표준 스키마(Contest)와 필드 이름을 반드시 맞춘다.
"""
import operator
from typing import Annotated, TypedDict


class Contest(TypedDict, total=False):
    title: str
    provider: str
    category: str      # 공모전 | 해커톤 | 경진대회 | 기타
    target: str        # 학생 | 일반 | 스타트업 | 개발자 | 기타
    start_date: str    # YYYY-MM-DD
    end_date: str      # YYYY-MM-DD
    url: str
    source_name: str
    raw_date: str
    # validate 단계에서 코드가 채우는 값
    days_left: int
    badge: str
    reason: str        # rejected 일 때 사유


class AgentState(TypedDict, total=False):
    # 입력
    topic: str                     # 예: "AI 해커톤", "학생 대상 AI 공모전"
    recipient: str                 # 받는 사람 메일
    today: str                     # YYYY-MM-DD (평가 재현성을 위해 주입 가능)

    # 검색 루프
    queries: list[str]
    attempt: int                   # 검색 라운드 (1부터)
    # reducer(operator.add): 노드가 리스트를 반환하면 덮어쓰지 않고 '누적'된다
    raw_results: Annotated[list[dict], operator.add]

    # 추출·검증
    candidates: list[Contest]
    valid: list[Contest]
    rejected: list[Contest]

    # 메일
    mail_subject: str
    mail_html: str
    review_errors: list[str]
    preview_path: str
    sent: bool
    status: str                    # sent | dry_run | aborted

    # 실행 로그(누적)
    log: Annotated[list[str], operator.add]
