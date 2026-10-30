"""노드 = State 를 받아 State(의 일부)를 돌려주는 파이썬 함수.

[LLM] 표시 노드: 판단·언어 처리 (키가 없으면 규칙 기반으로 대체)
[CODE] 표시 노드: 규칙·검증·조립·발송 (항상 같은 결과)
"""
from __future__ import annotations

import html as H
import os
import re

from pydantic import BaseModel, Field

from . import rules, tools
from .state import AgentState

MIN_ITEMS = int(os.getenv("MIN_ITEMS", "3"))       # 이보다 적으면 재검색
MAX_ATTEMPTS = int(os.getenv("MAX_ATTEMPTS", "2"))  # 재검색 최대 라운드


# =============================================================== 1. 검색어 생성 [LLM]
class Queries(BaseModel):
    queries: list[str] = Field(description="웹 검색어 3개. 각각 '공모전' 또는 '해커톤' 단어와 연도를 포함")


def plan_queries(state: AgentState) -> dict:
    topic, year = state["topic"], state["today"][:4]
    llm = tools.get_llm()
    if llm:
        prompt = (f"주제: {topic}\n오늘: {state['today']}\n"
                  "현재 접수 중인 한국 AI 공모전·해커톤 공고를 찾기 위한 웹 검색어 3개를 만들어라. "
                  "각 검색어에는 연도와 '공모전' 또는 '해커톤'을 넣고, 지난 대회 후기나 수상작 기사가 나오지 않게 '모집'·'접수' 같은 단어를 써라.")
        qs = llm.with_structured_output(Queries, method="json_schema").invoke(prompt).queries[:3]
    else:
        qs = [f"{year} {topic} 공모전 모집", f"{year} {topic} 해커톤 참가자 모집", f"{year} AI 경진대회 접수"]
    return {"queries": qs, "attempt": 1, "log": [f"[plan] 검색어 {qs}"]}


# =============================================================== 2. 웹 검색 [CODE/도구]
def search(state: AgentState) -> dict:
    attempt = state.get("attempt", 1)
    results: list[dict] = []
    seen_urls = {r["url"] for r in state.get("raw_results", []) if r.get("url")}
    for q in state["queries"]:
        for r in tools.web_search(q, attempt):
            key = r.get("url") or r.get("title")
            if key in seen_urls:
                continue
            seen_urls.add(key)
            results.append(r)
        if tools.is_offline():   # fixture 는 라운드당 한 번만 읽는다
            break
    # raw_results 는 reducer(add) 라서 이번 라운드 결과가 기존 목록 뒤에 '누적'된다
    return {"raw_results": results, "log": [f"[search] round {attempt}: {len(results)}건"]}


# =============================================================== 3. 스키마 추출 [LLM]
class Item(BaseModel):
    idx: int = Field(-1, description="입력 검색 결과의 번호 [i]")
    is_notice: bool = Field(False, description="참가자를 모집하는 공고면 true, 기사·후기·수상작 발표면 false")
    title: str = ""
    provider: str = Field("", description="주최/주관 기관. 본문에 없으면 빈 값")
    category: str = Field("기타", description="공모전|해커톤|경진대회|기타")
    target: str = Field("기타", description="학생|일반|스타트업|개발자|기타")
    raw_date: str = Field("", description="접수기간/마감일 원문 그대로. 없으면 빈 값")


class Items(BaseModel):
    items: list[Item]


EXTRACT_RULES = """너는 공고 정보 추출기다. 아래 검색 결과를 순서대로 1:1로 변환하라.
- 본문에 있는 정보만 쓴다. 없으면 빈 값으로 둔다. 날짜·기관명을 추측하지 않는다.
- raw_date 에는 접수기간이나 마감일 표현을 원문 그대로 옮긴다.
- 각 결과의 idx 에는 해당 입력의 번호 [i] 를 그대로 쓴다."""


def _heuristic_item(r: dict) -> dict:
    """키가 없을 때의 대체 추출기(fixture 형식 'key: value | ...')."""
    text = r.get("content", "")
    field = lambda k: (re.search(rf"{k}\s*:\s*([^|]+)", text) or [None, ""])[1].strip()
    target = field("대상")
    target = "학생" if "학생" in target else (target or "기타")
    return {"is_notice": bool(field("주최")), "title": r.get("title", ""),
            "provider": field("주최"), "category": field("분야") or "기타",
            "target": target, "raw_date": field("접수기간")}


def extract(state: AgentState) -> dict:
    raws = state.get("raw_results", [])
    llm = tools.get_llm()
    if llm and raws:
        listing = "\n\n".join(f"[{i}] 제목: {r['title']}\n본문: {r['content'][:800]}" for i, r in enumerate(raws))
        parsed = llm.with_structured_output(Items, method="json_schema").invoke(f"{EXTRACT_RULES}\n\n{listing}").items
        # 순서·개수가 아니라 idx 로 짝짓는다: 빠지거나 엉뚱한 항목이 다른 공고의 url 을 받지 않게
        by_idx = {p.idx: p.model_dump(exclude={"idx"}) for p in parsed}
        items = [by_idx.get(i, {}) for i in range(len(raws))]
    else:
        items = [_heuristic_item(r) for r in raws]

    candidates, dropped = [], 0
    for r, it in zip(raws, items):
        if not it.get("is_notice"):
            dropped += 1
            continue
        it.pop("is_notice", None)
        if llm:
            source = re.sub(r"\s+", "", r.get("content", "")[:800])
            if any(re.sub(r"\s+", "", it.get(k, "")) not in source
                   for k in ("provider", "raw_date")):
                it["reason"] = "unsupported_source"
        # url·출처는 LLM이 아니라 검색 결과에서 그대로 가져온다 (링크 지어내기 차단)
        candidates.append({**it, "url": r.get("url", ""), "source_name": r.get("source_name", "")})
    return {"candidates": candidates, "log": [f"[extract] 누적 공고 {len(candidates)}건, 공고 아님 {dropped}건"]}


# =============================================================== 4. 검증 [CODE]
def validate(state: AgentState) -> dict:
    valid, rejected = rules.validate_items(state.get("candidates", []), state["today"], tools.load_sent_keys())
    counts = rules.reason_counts(rejected)
    return {"valid": valid, "rejected": rejected,
            "log": [f"[validate] valid {len(valid)} / rejected {len(rejected)} {counts}"]}


def route_after_validate(state: AgentState) -> str:
    """조건부 엣지: 충분하면 메일 작성, 부족하고 기회가 남으면 재검색."""
    if len(state.get("valid", [])) >= MIN_ITEMS:
        return "compose"
    if state.get("attempt", 1) < MAX_ATTEMPTS:
        return "rewrite"
    return "compose"   # 기회를 다 썼으면 있는 만큼(0건이면 안내 메일)


# =============================================================== 5. 검색어 재작성 [LLM]
def rewrite_queries(state: AgentState) -> dict:
    llm, year = tools.get_llm(), state["today"][:4]
    reasons = rules.reason_counts(state.get("rejected", []))
    if llm:
        prompt = (f"주제: {state['topic']}\n이전 검색어: {state['queries']}\n탈락 사유 통계: {reasons}\n"
                  f"유효 공고가 {len(state.get('valid', []))}건뿐이다. 마감 지난 공고와 기사가 덜 나오도록 "
                  f"검색어 3개를 새로 만들어라. 연도 {year}, '모집' 또는 '접수중'을 포함하라.")
        qs = llm.with_structured_output(Queries, method="json_schema").invoke(prompt).queries[:3]
    else:
        topic = state["topic"]
        qs = [f"{year} {topic} 해커톤 접수중", f"{year} {topic} 공모전 모집중", f"{year} {topic} 챌린지 참가 신청"]
    attempt = state.get("attempt", 1) + 1
    return {"queries": qs, "attempt": attempt, "log": [f"[rewrite] round {attempt} 검색어 {qs} (탈락 {reasons})"]}


# =============================================================== 6. 메일 조립 [CODE + LLM 한 줄]
def compose(state: AgentState) -> dict:
    valid, today = state.get("valid", []), state["today"]
    subject = f"[AI 공모전 알림] {today} · {len(valid)}건"

    intro = f"{state['topic']} 관련 접수 중인 공고 {len(valid)}건을 마감 임박 순으로 정리했습니다."
    llm = tools.get_llm()
    if llm and valid:
        titles = ", ".join(v["title"] for v in valid[:5])
        intro = llm.invoke(f"다음 공고 목록을 보고 메일 첫 문장 1개를 존댓말로 써라. 링크·날짜는 쓰지 마라: {titles}").text.strip()

    rows = []
    for v in valid:
        badge = f'<span style="background:#c8562a;color:#fff;border-radius:4px;padding:1px 6px;font-size:12px">{H.escape(v["badge"])}</span> ' if v.get("badge") else ""
        rows.append(
            f'<div class="item" style="border:1px solid #ddd;border-radius:8px;padding:12px;margin:8px 0">'
            f'{badge}<b>{H.escape(v["title"])}</b><br>'
            f'<span style="color:#555">{H.escape(v["provider"])} · {H.escape(v.get("category", ""))} · 대상: {H.escape(v.get("target", ""))}</span><br>'
            f'마감 {v["end_date"]} (D-{v["days_left"]}) · <a href="{H.escape(v["url"])}">원문 공고 보기</a></div>')
    body = "".join(rows) or "<p>이번에는 조건에 맞는 공고가 없습니다. 다음 알림에서 다시 확인해 주세요.</p>"
    html = (f'<div style="font-family:sans-serif;max-width:640px"><h2>AI 공모전·해커톤 알림</h2>'
            f'<p>{H.escape(intro)}</p>{body}'
            f'<p style="color:#888;font-size:12px">자동 수집 결과입니다. 신청 전 원문 공고를 꼭 확인하세요.</p></div>')
    return {"mail_subject": subject, "mail_html": html, "log": [f"[compose] {subject}"]}


# =============================================================== 7. 발송 전 리뷰 [CODE]
def review(state: AgentState) -> dict:
    errors = rules.review_mail(state["mail_subject"], state["mail_html"], state.get("valid", []),
                               state["today"], tools.secret_values())
    path = tools.save_preview(state["mail_subject"], state["mail_html"], state["today"])
    return {"review_errors": errors, "preview_path": path,
            "log": [f"[review] {'PASS' if not errors else 'FAIL ' + str(errors)} · 미리보기 {path}"]}


def route_after_review(state: AgentState) -> str:
    return "send" if not state.get("review_errors") else "abort"


# =============================================================== 8. 발송 [CODE]
def send(state: AgentState) -> dict:
    """그래프는 이 노드 '직전'에 멈춘다(interrupt_before). 사람이 승인해야 실행된다."""
    dry = os.getenv("DRY_RUN", "1") == "1" or not os.getenv("SMTP_USER")
    if dry:
        return {"sent": False, "status": "dry_run", "log": ["[send] DRY_RUN: 실제 발송하지 않고 미리보기만 저장"]}
    tools.send_mail(state["recipient"], state["mail_subject"], state["mail_html"])
    tools.save_sent_keys({rules.dedupe_key(v) for v in state.get("valid", [])})  # 발송 성공 후에만 기록
    return {"sent": True, "status": "sent", "log": [f"[send] {state['recipient']} 로 발송 완료"]}


def abort(state: AgentState) -> dict:
    return {"sent": False, "status": "aborted", "log": [f"[abort] 리뷰 실패로 발송 중단: {state.get('review_errors')}"]}
