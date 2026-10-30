"""실행 진입점.

python main.py --offline                 # 키 없이 가상 데이터로 전체 흐름 실습
python main.py --topic "학생 AI 해커톤"   # 실제 검색 (DRY_RUN=1 이면 발송 안 함)
python main.py --auto-send               # 승인 질문 없이 발송 (스케줄 실행용)
"""
import argparse
import os
import uuid
from datetime import date

from langgraph.errors import GraphRecursionError

try:
    from dotenv import load_dotenv
    load_dotenv()
except ImportError:
    pass


def main():
    p = argparse.ArgumentParser()
    p.add_argument("--topic", default=os.getenv("TOPIC", "AI"))
    p.add_argument("--to", default=os.getenv("MAIL_TO", "me@example.com"))
    p.add_argument("--today", default=os.getenv("TODAY", date.today().isoformat()))
    p.add_argument("--offline", action="store_true")
    p.add_argument("--auto-send", action="store_true")
    a = p.parse_args()
    if a.offline:
        os.environ["OFFLINE"] = "1"

    from agent.graph import build_graph  # 환경 변수 설정 후 import
    app = build_graph(require_approval=not a.auto_send)
    config = {"configurable": {"thread_id": str(uuid.uuid4())}, "recursion_limit": 25}
    init = {"topic": a.topic, "recipient": a.to, "today": a.today}

    try:
        for step in app.stream(init, config, stream_mode="updates"):
            for node, upd in step.items():
                for line in (upd or {}).get("log", []):
                    print(line)
    except GraphRecursionError:
        print("[error] recursion_limit 도달 — 재검색 루프를 확인하세요.")
        return

    snap = app.get_state(config)
    if snap.next == ("send",):  # interrupt 로 멈춘 상태
        v = snap.values
        print(f"\n제목: {v['mail_subject']}\n미리보기: {v['preview_path']}")
        if input("이 메일을 발송할까요? (y/N) ").strip().lower() == "y":
            for step in app.stream(None, config, stream_mode="updates"):  # 멈춘 지점부터 재개
                for upd in step.values():
                    for line in (upd or {}).get("log", []):
                        print(line)
        else:
            print("발송을 취소했습니다.")

    final = app.get_state(config).values
    print(f"\n결과: status={final.get('status', 'cancelled')}, valid={len(final.get('valid', []))}, "
          f"rejected={len(final.get('rejected', []))}")


if __name__ == "__main__":
    main()
