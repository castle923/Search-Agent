"""웹 화면: python web.py → 브라우저에서 http://127.0.0.1:8000

main.py 와 같은 그래프를 브라우저에서 실행한다. 노드가 끝날 때마다 JSON 한 줄씩 흘려보내고(진행 애니메이션),
send 직전 interrupt 에서 멈춘 뒤 [메일 발송] 버튼(/send)으로 그 자리부터 재개한다.
"""
import json
import os
import re
import secrets
import uuid
import webbrowser
from datetime import date
from http.server import BaseHTTPRequestHandler, HTTPServer
from pathlib import Path
from urllib.parse import parse_qs
from dotenv import set_key

try:
    from dotenv import load_dotenv
    load_dotenv(Path(__file__).resolve().parent / ".env")
except ImportError:
    pass

from agent import rules  # noqa: E402
from agent.graph import build_graph  # noqa: E402

PAGE = Path(__file__).resolve().parent / "web" / "index.html"
ENV_FILE = PAGE.parent.parent / ".env"
SETTINGS_TOKEN = secrets.token_urlsafe(32)
APP = build_graph(require_approval=True)  # MemorySaver 가 thread 별 상태를 기억해 승인 후 재개할 수 있다
CARD_FIELDS = ("title", "provider", "category", "target", "end_date", "days_left", "badge", "url")


def _cfg(thread: str) -> dict:
    return {"configurable": {"thread_id": thread}, "recursion_limit": 25}


class Handler(BaseHTTPRequestHandler):
    def do_GET(self):
        if self.path in ("/settings", "/settings?saved=1"):
            style = PAGE.read_text(encoding="utf-8").split("<style>", 1)[1].split("</style>", 1)[0]
            body = (PAGE.parent / "settings.html").read_text(encoding="utf-8")
            body = body.replace("{{style}}", style).replace("{{token}}", SETTINGS_TOKEN)
            status = "설정됨" if os.getenv("ANTHROPIC_API_KEY") else "미설정"
            body = body.replace("{{status}}", "저장했습니다. 다음 검색부터 적용됩니다." if self.path.endswith("saved=1") else f"현재 키: {status}")
            data = body.encode("utf-8")
            self.send_response(200)
            self.send_header("Content-Type", "text/html; charset=utf-8")
            self.send_header("Cache-Control", "no-store")
            self.send_header("Content-Security-Policy", "default-src 'none'; style-src 'unsafe-inline'; form-action 'self'; frame-ancestors 'none'; base-uri 'none'")
            self.send_header("Content-Length", str(len(data)))
            self.end_headers()
            return self.wfile.write(data)
        if self.path != "/":
            return self.send_error(404)
        body = PAGE.read_bytes()
        self.send_response(200)
        self.send_header("Content-Type", "text/html; charset=utf-8")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def do_POST(self):
        if self.path == "/settings":
            return self._settings()
        route = {"/run": self._run, "/send": self._send}.get(self.path)
        if not route:
            return self.send_error(404)
        req = json.loads(self.rfile.read(int(self.headers.get("Content-Length", 0))) or b"{}")
        self.send_response(200)
        self.send_header("Content-Type", "application/x-ndjson; charset=utf-8")
        self.end_headers()
        try:
            route(req)
        except Exception as e:  # 화면에 오류를 보여 주고 서버는 계속 살아 있게
            self._emit({"error": f"{type(e).__name__}: {e}"})

    def _settings(self):
        allowed_hosts = {f"127.0.0.1:{self.server.server_port}", f"localhost:{self.server.server_port}"}
        host = self.headers.get("Host", "")
        if host not in allowed_hosts or self.headers.get("Origin") != f"http://{host}":
            return self.send_error(403, "Open settings from this local server")
        try:
            length = int(self.headers.get("Content-Length", "0"))
            if not 0 < length <= 4096 or self.headers.get_content_type() != "application/x-www-form-urlencoded":
                return self.send_error(400, "Invalid settings request")
            data = parse_qs(self.rfile.read(length).decode("utf-8"), strict_parsing=True)
            if set(data) != {"token", "api_key"} or any(len(v) != 1 for v in data.values()):
                return self.send_error(400, "Invalid settings fields")
            if not secrets.compare_digest(data["token"][0].encode("utf-8"), SETTINGS_TOKEN.encode("utf-8")):
                return self.send_error(403, "Reload settings and retry")
            key = data["api_key"][0].strip()
            if not re.fullmatch(r"sk-ant-[A-Za-z0-9_-]{10,500}", key):
                return self.send_error(400, "Enter a valid Claude API key")
            set_key(str(ENV_FILE), "ANTHROPIC_API_KEY", key)
        except (ValueError, UnicodeError, OSError):
            return self.send_error(400, "Could not save settings")
        os.environ["ANTHROPIC_API_KEY"] = key
        self.send_response(303)
        self.send_header("Location", "/settings?saved=1")
        self.send_header("Cache-Control", "no-store")
        self.end_headers()

    def _emit(self, obj: dict):
        self.wfile.write((json.dumps(obj, ensure_ascii=False) + "\n").encode("utf-8"))
        self.wfile.flush()

    def _stream(self, inp, thread: str):
        for step in APP.stream(inp, _cfg(thread), stream_mode="updates"):
            for node, upd in step.items():
                if not node.startswith("__"):  # __interrupt__ 같은 내부 이벤트는 건너뛴다
                    self._emit({"node": node, "log": (upd or {}).get("log", [])})
        snap = APP.get_state(_cfg(thread))
        v = snap.values
        self._emit({
            "done": True, "thread": thread, "waiting": snap.next == ("send",),
            "status": v.get("status", ""), "subject": v.get("mail_subject", ""),
            "mail_html": v.get("mail_html", ""), "recipient": v.get("recipient", ""),
            "valid": [{k: c.get(k, "") for k in CARD_FIELDS} for c in v.get("valid", [])],
            "rejected": rules.reason_counts(v.get("rejected", [])),
            "review_errors": v.get("review_errors", []),
            # nodes.send 와 같은 조건
            "dry_run": os.getenv("DRY_RUN", "1") == "1" or not os.getenv("SMTP_USER"),
        })

    def _run(self, req: dict):
        topic = str(req.get("topic") or "AI").strip()[:50]
        today = date.fromisoformat(req.get("today") or date.today().isoformat()).isoformat()
        os.environ["OFFLINE"] = "1" if req.get("offline") else "0"
        init = {"topic": topic, "recipient": os.getenv("MAIL_TO", "me@example.com"), "today": today}
        self._stream(init, str(uuid.uuid4()))

    def _send(self, req: dict):
        thread = str(req.get("thread", ""))
        if APP.get_state(_cfg(thread)).next != ("send",):
            return self._emit({"error": "승인 대기 중인 실행이 없습니다. 먼저 검색을 실행하세요."})
        self._stream(None, thread)  # 멈춘 지점(send)부터 재개


if __name__ == "__main__":
    url = "http://127.0.0.1:8000"
    print(f"웹 화면: {url}  (종료: Ctrl+C)")
    server = HTTPServer(("127.0.0.1", 8000), Handler)
    webbrowser.open(url)
    server.serve_forever()  # 내 PC 에서만 접속 가능
