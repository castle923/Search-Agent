"""하네스 OFF 기준선 — "AI 공모전 찾아서 메일로 보내줘" 한 줄 요구만 구현한 버전.

검증·재검색·리뷰·승인 없이 검색 결과를 그대로 메일로 만든다.
영상 속 'Without' 폴더처럼 겉보기엔 동작하지만 무엇이 빠졌는지 evals 로 확인한다.
"""
import html as H
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from agent import tools  # noqa: E402


def run(topic: str, today: str) -> dict:
    results = tools.web_search(f"{topic} 공모전", attempt=1)
    rows = "".join(
        f'<div class="item"><b>{H.escape(r["title"])}</b><br>{H.escape(r["content"][:120])}'
        f'<br><a href="{H.escape(r["url"])}">링크</a></div>' for r in results)
    return {"mail_subject": f"AI 공모전 {len(results)}건", "mail_html": rows,
            "status": "sent", "attempt": 1, "items": results}
