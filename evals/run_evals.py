"""하네스 검증 루프: python evals/run_evals.py

1) 규칙 단위 테스트 (rules.py)
2) offline 전체 그래프 실행 → 기대 결과와 비교
3) 하네스 ON vs OFF(naive_agent) 7개 항목 채점
"""
import json
import os
import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))
os.environ["OFFLINE"] = "1"
os.environ["DRY_RUN"] = "1"

from agent import nodes, rules, tools  # noqa: E402
from agent.graph import build_graph  # noqa: E402
from evals import naive_agent  # noqa: E402

tools.load_sent_keys = lambda: set()  # 실제 발송 기록(data/sent_history.json)이 평가 결과를 바꾸지 않게
S = json.loads((ROOT / "evals" / "eval_samples.json").read_text(encoding="utf-8"))
TODAY = S["today"]
results: list[tuple[str, bool, str]] = []


def check(name: str, ok: bool, detail: str = ""):
    results.append((name, ok, detail))


# ------------------------------------------------------------ 1) 규칙 테스트
for c in S["rule_cases"]:
    valid, rejected = rules.validate_items([c["item"]], TODAY)
    visible = bool(valid)
    ok = visible == c["expected_visible"]
    detail = ""
    if visible and ok:
        v = valid[0]
        if "expected_end_date" in c and v["end_date"] != c["expected_end_date"]:
            ok, detail = False, f"end_date {v['end_date']}"
        if "expected_badge" in c and v["badge"] != c["expected_badge"]:
            ok, detail = False, f"badge {v['badge']!r}"
    if not visible and ok and "expected_reason" in c:
        got = rejected[0]["reason"].split(":")[0]
        ok, detail = got == c["expected_reason"], f"reason {got}"
    check(f"{c['id']} {c['desc']}", ok, detail)

d = S["dedupe_case"]
valid, _ = rules.validate_items(d["items"], TODAY)
check("D01 " + d["desc"], len(valid) == d["expected_valid"], f"valid {len(valid)}")


class _ShuffledLLM:
    """순서를 뒤집고 빈 항목을 섞어 돌려주는 가짜 LLM (실제 Claude 응답에서 나온 형태)."""
    def with_structured_output(self, schema, **kw):
        return self

    def invoke(self, _prompt):
        return nodes.Items(items=[nodes.Item(idx=1, is_notice=True, title="B"), nodes.Item(),
                                  nodes.Item(idx=0, is_notice=False, title="A")])


_real_get_llm, tools.get_llm = tools.get_llm, lambda: _ShuffledLLM()
out = nodes.extract({"raw_results": [{"title": "A", "url": "https://a.example", "content": ""},
                                     {"title": "B", "url": "https://b.example", "content": ""}]})
tools.get_llm = _real_get_llm
c = out["candidates"]
check("X01 LLM 추출 결과는 idx 로 url 과 짝지어진다",
      len(c) == 1 and c[0]["title"] == "B" and c[0]["url"] == "https://b.example", str(c))

item = S["rule_cases"][0]["item"]
valid, rejected = rules.validate_items([item], TODAY, {rules.dedupe_key({**item, "end_date": "2026-11-30"})})
check("H01 이미 보낸 공고는 다시 보내지 않는다",
      not valid and rejected[0]["reason"] == "already_sent", str([r["reason"] for r in rejected]))

saved: list[set] = []
_real = (tools.send_mail, tools.save_sent_keys)
tools.send_mail, tools.save_sent_keys = (lambda *a: None), saved.append
st = {"recipient": "t@example.com", "mail_subject": "s", "mail_html": "h", "valid": [{**item, "end_date": "2026-11-30"}]}
nodes.send(st)                               # DRY_RUN=1 → 기록하지 않음
os.environ.update(DRY_RUN="0", SMTP_USER="t@example.com")
nodes.send(st)                               # 실제 발송 → 기록
os.environ.update(DRY_RUN="1")
os.environ.pop("SMTP_USER")
tools.send_mail, tools.save_sent_keys = _real
check("H02 발송 기록은 실제 발송 때만 남는다", len(saved) == 1 and len(saved[0]) == 1, str(saved))


# ------------------------------------------------------------ 2) 전체 그래프(하네스 ON)
def run_harness_on() -> dict:
    app = build_graph(require_approval=False)
    cfg = {"configurable": {"thread_id": "eval"}, "recursion_limit": 25}
    return app.invoke({"topic": "AI", "recipient": "test@example.com", "today": TODAY}, cfg)


on = run_harness_on()
exp = S["e2e_expected"]
mail_titles = [v["title"] for v in on["valid"]]
check("E01 기대한 공고만 메일에 포함", sorted(mail_titles) == sorted(exp["visible_titles"]), str(mail_titles))
check("E02 제외 대상이 메일에 없음", not any(t in on["mail_html"] for t in exp["hidden_titles"]))
check("E03 재검색 루프 동작", on["attempt"] >= exp["min_attempts"], f"attempt {on['attempt']}")
check("E04 리뷰 게이트 PASS", not on["review_errors"], str(on["review_errors"]))
check("E05 DRY_RUN 에서 실제 발송 안 함", on["status"] == "dry_run" and not on["sent"])
check("E06 마감 임박 순 정렬", [v["days_left"] for v in on["valid"]] == sorted(v["days_left"] for v in on["valid"]))


# ------------------------------------------------------------ 3) ON vs OFF 채점
def score(mail_html: str, subject: str, attempt: int, review_ok: bool, safe_send: bool) -> dict:
    blocks = re.findall(r'class="item".*?</div>', mail_html, flags=re.S)
    has = lambda t: t in mail_html
    hrefs = re.findall(r'href="([^"]*)"', mail_html)
    titles_in_mail = [t for t in exp["visible_titles"] + exp["hidden_titles"] if has(t)]
    dup = has("제3회 한빛 AI 서비스 아이디어 공모전 참가자 모집") and has("[재공지]")
    return {
        "① 마감 공고 제외 (20)": 0 if has("서해 AI 해커톤") else 20,
        "② 링크 이상 공고 제외 (15)": 15 if all(h.startswith("http") for h in hrefs) and not has("헬스케어") else 0,
        "③ 중복 제거 (15)": 0 if dup else 15,
        "④ 공고 아닌 결과 제외 (10)": 0 if has("트렌드 분석") else 10,
        "⑤ 날짜 정규화·뱃지 (10)": 10 if blocks and all(re.search(r"\d{4}-\d{2}-\d{2}", b) for b in blocks) else 0,
        "⑥ 부족 시 재검색 (10)": 10 if attempt >= 2 else 0,
        "⑦ 발송 안전장치 (20)": (10 if review_ok else 0) + (10 if safe_send else 0),
        "_count": len(titles_in_mail),
    }


off = naive_agent.run("AI", TODAY)
s_on = score(on["mail_html"], on["mail_subject"], on["attempt"], not on["review_errors"], on["status"] == "dry_run")
s_off = score(off["mail_html"], off["mail_subject"], off["attempt"], False, False)

# ------------------------------------------------------------ 출력
print("\n=== 규칙·그래프 테스트 ===")
for name, ok, detail in results:
    print(f"  {'PASS' if ok else 'FAIL'}  {name}" + (f"  ({detail})" if detail and not ok else ""))
passed = sum(ok for _, ok, _ in results)
print(f"  → {passed}/{len(results)} PASS")

print("\n=== 하네스 OFF vs ON (100점) ===")
print(f"  {'항목':<26}{'OFF':>6}{'ON':>6}")
for k in s_on:
    if k.startswith("_"):
        continue
    print(f"  {k:<24}{s_off[k]:>6}{s_on[k]:>6}")
tot = lambda s: sum(v for k, v in s.items() if not k.startswith("_"))
print(f"  {'합계':<26}{tot(s_off):>6}{tot(s_on):>6}")
print(f"\n  OFF 메일 공고 수 {len(off['items'])}건(검증 없음) / ON 메일 공고 수 {len(on['valid'])}건(검증 통과)")

sys.exit(0 if passed == len(results) else 1)
