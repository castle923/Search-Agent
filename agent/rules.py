"""코드가 맡는 규칙 — AGENTS.md 'Data quality rules' 를 그대로 구현한다.

LLM에게 맡기지 않는 이유: 매번 같은 입력에 같은 결과가 나와야 하고,
evals 로 자동 검증할 수 있어야 하기 때문.
"""
from __future__ import annotations

import re
from html import unescape
from datetime import date
from urllib.parse import urlsplit

REQUIRED = ("title", "provider", "end_date", "url")


def _year_for(month: int, day: int, today: date) -> int:
    """연도가 없는 날짜는 올해로 본다. 이미 지났고 내년 날짜가 3개월(92일) 이내일 때만 내년으로 본다.
    (11월에 본 '~1/15' 는 내년, 10월에 본 '4월 24일까지' 는 올해 = 마감)"""
    try:
        cand = date(today.year, month, day)
        nxt = date(today.year + 1, month, day)
    except ValueError:
        return today.year
    return today.year + 1 if cand < today and (nxt - today).days <= 92 else today.year


def normalize_date(raw: str | None, today: date | None = None) -> str:
    """다양한 날짜 표기를 YYYY-MM-DD 로. 실패하면 빈 문자열."""
    if not raw:
        return ""
    today = today or date.today()
    s = str(raw).strip()

    # 기간 표기면 마지막 날짜(마감일)를 쓴다: "2026.10.01 ~ 2026.11.30"
    parts = re.split(r"\s*[~∼〜]\s*|\s+-\s+|\s+–\s+", s)
    s = parts[-1].strip() or s

    m = re.search(r"(\d{4})\s*[.\-/년]\s*(\d{1,2})\s*[.\-/월]\s*(\d{1,2})", s)
    if m:
        y, mo, d = map(int, m.groups())
    else:
        m = re.search(r"(\d{1,2})\s*[.\-/월]\s*(\d{1,2})\s*일?", s)
        if not m:
            return ""
        mo, d = map(int, m.groups())
        y = _year_for(mo, d, today)
    try:
        return date(y, mo, d).isoformat()
    except ValueError:
        return ""


_NOISE = re.compile(r"\[[^\]]*\]|\([^)]*\)|참가자\s*모집|참가팀\s*모집|모집\s*공고|모집|안내|공고")


def norm_title(title: str) -> str:
    """'[재공지] ... 공모전 참가자 모집' 같은 꾸밈말을 지우고 비교한다.
    (PLAN.md Risk: 단순 문자열 비교로는 중복 판정이 부족하다)"""
    t = _NOISE.sub("", str(title or ""))
    return re.sub(r"\s+", "", t).lower()


def dedupe_key(item: dict) -> str:
    provider = re.sub(r"\s+", "", str(item.get("provider") or "")).lower()
    return f"{provider}|{norm_title(item.get('title'))}|{item.get('end_date', '')}"


def badge_for(days_left: int) -> str:
    if days_left == 0:
        return "오늘 마감"
    if days_left <= 7:
        return "이번 주 마감"
    return ""


def validate_items(items: list[dict], today_str: str,
                   sent_keys: set[str] = frozenset()) -> tuple[list[dict], list[dict]]:
    """valid / rejected 로 나눈다. rejected 에는 reason 을 남긴다.
    sent_keys: 이전 메일로 이미 보낸 공고의 dedupe_key (already_sent 로 제외)"""
    today = date.fromisoformat(today_str)
    valid, rejected, seen = [], [], set()

    for raw in items:
        it = dict(raw)
        if it.get("reason") == "unsupported_source":
            rejected.append(it)
            continue
        if not it.get("end_date") and it.get("raw_date"):
            it["end_date"] = normalize_date(it["raw_date"], today)
        elif it.get("end_date"):
            it["end_date"] = normalize_date(it["end_date"], today) or ""

        if it.get("raw_date") and not it.get("end_date"):
            rejected.append({**it, "reason": "bad_date"})
            continue
        missing = [k for k in REQUIRED if not str(it.get(k, "")).strip()]
        if missing:
            rejected.append({**it, "reason": "missing_field:" + ",".join(missing)})
            continue
        try:
            url = urlsplit(it["url"])
            url_ok = (url.scheme in {"http", "https"} and bool(url.hostname)
                      and not re.search(r"\s", it["url"]))
            url.port  # 잘못된 포트도 거부한다.
        except (ValueError, TypeError):
            url_ok = False
        if not url_ok:
            rejected.append({**it, "reason": "bad_url"})
            continue

        days_left = (date.fromisoformat(it["end_date"]) - today).days
        if days_left < 0:
            rejected.append({**it, "reason": "expired", "expired": True})
            continue

        key = dedupe_key(it)
        if key in seen:
            rejected.append({**it, "reason": "duplicate"})
            continue
        seen.add(key)
        if key in sent_keys:
            rejected.append({**it, "reason": "already_sent"})
            continue

        it["days_left"] = days_left
        it["badge"] = badge_for(days_left)
        it.setdefault("target", "기타")
        it.setdefault("category", "기타")
        valid.append(it)

    valid.sort(key=lambda x: x["days_left"])
    return valid, rejected


def reason_counts(rejected: list[dict]) -> dict[str, int]:
    out: dict[str, int] = {}
    for r in rejected:
        k = r.get("reason", "unknown").split(":")[0]
        out[k] = out.get(k, 0) + 1
    return out


def review_mail(subject: str, html: str, valid: list[dict], today_str: str,
                secrets: list[str] | None = None) -> list[str]:
    """mail-release 스킬의 Required checks."""
    errors = []
    expected = f"[AI 공모전 알림] {today_str} · {len(valid)}건"
    if subject != expected:
        errors.append(f"subject 형식 불일치: {subject!r} != {expected!r}")

    links = [unescape(link) for link in re.findall(r'href="([^"]+)"', html)]
    allowed = {v["url"] for v in valid}
    unknown = [l for l in links if l not in allowed]
    if unknown:
        errors.append(f"검증되지 않은 링크 {len(unknown)}개: {unknown[:3]}")
    if set(links) != allowed:
        errors.append("공고 원문 링크 누락")
    if validate_items(valid, today_str)[1]:
        errors.append("유효하지 않거나 마감된 공고 포함")
    if html.count('class="item"') != len(valid):
        errors.append("본문 공고 수와 valid 수가 다름")
    if not valid and "조건에 맞는 공고가 없습니다" not in html:
        errors.append("0건 안내 문구 누락")
    for s in secrets or []:
        if s and len(s) > 6 and s in html:
            errors.append("본문에 비밀 값 노출")
    return errors
