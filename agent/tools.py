"""외부 연동(검색·LLM·메일). 키가 없으면 자동으로 offline / dry-run 으로 바뀐다.

환경 제약(하네스): 이 파일만 외부와 통신한다. 노드는 여기 함수만 호출한다.
"""
from __future__ import annotations

import json
import os
import smtplib
from email.mime.text import MIMEText
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
FIXTURE = ROOT / "data" / "fixtures" / "search_results.json"
SENT_HISTORY = ROOT / "data" / "sent_history.json"
# 공모전 모집 공고가 모이는 사이트만 검색한다 (블로그·뉴스·YouTube 재게시 차단)
CONTEST_DOMAINS = ["wevity.com", "linkareer.com", "thinkcontest.com", "contestkorea.com",
                   "allcon.or.kr", "dacon.io", "aifactory.space"]


def is_offline() -> bool:
    return os.getenv("OFFLINE", "0") == "1" or not os.getenv("TAVILY_API_KEY")


# ---------------------------------------------------------------- 검색
def web_search(query: str, attempt: int, max_results: int = 5) -> list[dict]:
    """반환 형식: [{title, url, content, query, source_name}]"""
    if is_offline():
        data = json.loads(FIXTURE.read_text(encoding="utf-8"))
        rows = data.get(f"round{attempt}", [])
        return [{**r, "query": query, "source_name": "fixture"} for r in rows]

    from tavily import TavilyClient  # pip install tavily-python
    client = TavilyClient(api_key=os.environ["TAVILY_API_KEY"])
    res = client.search(query=query, max_results=max_results, search_depth="advanced",
                        include_domains=CONTEST_DOMAINS)
    return [
        {"title": r.get("title", ""), "url": r.get("url", ""),
         "content": r.get("content", ""), "query": query, "source_name": "tavily"}
        for r in res.get("results", [])
    ]


# ---------------------------------------------------------------- LLM
def get_llm():
    """LLM_PROVIDER=anthropic | gemini | openai | none. none 이거나 키가 없으면 None."""
    provider = os.getenv("LLM_PROVIDER", "anthropic").lower()
    if provider == "none" or os.getenv("OFFLINE") == "1":
        return None
    if provider == "anthropic" and os.getenv("ANTHROPIC_API_KEY"):
        from langchain_anthropic import ChatAnthropic
        # temperature 는 넣지 않는다: 최신 Claude 모델은 sampling 파라미터를 400 으로 거부
        return ChatAnthropic(model=os.getenv("LLM_MODEL", "claude-haiku-5-5"), max_tokens=8192)
    if provider == "gemini" and os.getenv("GOOGLE_API_KEY"):
        from langchain_google_genai import ChatGoogleGenerativeAI
        return ChatGoogleGenerativeAI(model=os.getenv("LLM_MODEL", "gemini-2.5-flash"), temperature=0)
    if provider == "openai" and os.getenv("OPENAI_API_KEY"):
        from langchain_openai import ChatOpenAI
        return ChatOpenAI(model=os.getenv("LLM_MODEL", "gpt-4o-mini"), temperature=0)
    return None


# ---------------------------------------------------------------- 보낸 공고 기록
def load_sent_keys() -> set[str]:
    """실제로 발송한 공고의 dedupe_key 목록. 파일이 없거나 깨졌으면 빈 집합."""
    try:
        return set(json.loads(SENT_HISTORY.read_text(encoding="utf-8")))
    except (FileNotFoundError, ValueError):
        return set()


def save_sent_keys(keys: set[str]) -> None:
    # shortcut: 키가 계속 쌓인다(마감 지난 키도 남음), 수천 건이 넘으면 end_date 기준으로 정리
    SENT_HISTORY.write_text(json.dumps(sorted(load_sent_keys() | keys), ensure_ascii=False, indent=1),
                            encoding="utf-8")


# ---------------------------------------------------------------- 메일
def secret_values() -> list[str]:
    keys = ("TAVILY_API_KEY", "ANTHROPIC_API_KEY", "GOOGLE_API_KEY", "OPENAI_API_KEY", "SMTP_PASSWORD")
    return [os.getenv(k, "") for k in keys]


def save_preview(subject: str, html: str, today: str) -> str:
    out = ROOT / "outbox"
    out.mkdir(exist_ok=True)
    path = out / f"mail_{today}.html"
    path.write_text(f"<!-- {subject} -->\n{html}", encoding="utf-8")
    return str(path)


def send_mail(to: str, subject: str, html: str) -> None:
    """Gmail 기준: SMTP_HOST=smtp.gmail.com, 포트 465, 앱 비밀번호 사용."""
    host = os.getenv("SMTP_HOST", "smtp.gmail.com")
    port = int(os.getenv("SMTP_PORT", "465"))
    user = os.environ["SMTP_USER"]
    pw = os.environ["SMTP_PASSWORD"]
    msg = MIMEText(html, "html", "utf-8")
    msg["Subject"], msg["From"], msg["To"] = subject, user, to
    with smtplib.SMTP_SSL(host, port, timeout=30) as s:
        s.login(user, pw)
        s.send_message(msg)
