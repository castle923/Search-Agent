"""복원 시 보완한 규칙과 승인 흐름의 오프라인 회귀 검사."""
import os
import unittest
from unittest.mock import patch

os.environ.update(OFFLINE="1", DRY_RUN="1")
from agent import nodes, rules, tools
from agent.graph import build_graph

TODAY = "2026-11-02"
ITEM = {"title": "AI 대회", "provider": "기관", "end_date": "2026-11-30",
        "url": "https://example.com/notice?a=1&b=2", "target": "학생"}


class RestoreTests(unittest.TestCase):
    def test_query_url_survives_html_escape(self):
        valid, _ = rules.validate_items([ITEM], TODAY)
        mail = nodes.compose({"valid": valid, "today": TODAY, "topic": "AI"})
        self.assertEqual(rules.review_mail(mail["mail_subject"], mail["mail_html"], valid, TODAY), [])

    def test_invalid_hosts_rejected(self):
        for url in ("https://", "https:///notice", "https://exa mple.com", "https://example.com:wrong"):
            with self.subTest(url=url):
                valid, rejected = rules.validate_items([{**ITEM, "url": url}], TODAY)
                self.assertFalse(valid)
                self.assertEqual(rejected[0]["reason"], "bad_url")

    def test_expired_rechecked_at_review(self):
        item = {**ITEM, "end_date": "2026-10-01"}
        self.assertTrue(rules.review_mail("[AI 공모전 알림] 2026-11-02 · 1건",
                                         '<div class="item"></div>', [item], TODAY))

    def test_source_evidence_required(self):
        class FakeLLM:
            def with_structured_output(self, *args, **kwargs):
                return self

            def invoke(self, prompt):
                return nodes.Items(items=[nodes.Item(idx=0, is_notice=True, title="AI 대회",
                    provider="기관", raw_date="2026-11-30")])

        with patch.object(tools, "get_llm", return_value=FakeLLM()):
            candidates = nodes.extract({"raw_results": [{"title": "AI 대회", "url": ITEM["url"],
                "content": "주최: 기관 | 접수기간: 2026-10-01"}]})["candidates"]
        valid, rejected = rules.validate_items(candidates, TODAY)
        self.assertFalse(valid)
        self.assertEqual(rejected[0]["reason"], "unsupported_source")

    def test_rewrite_keeps_topic(self):
        output = nodes.rewrite_queries({"today": TODAY, "topic": "학생 AI", "queries": []})
        self.assertTrue(all("학생 AI" in q for q in output["queries"]))

    def test_approval_then_dry_run(self):
        with patch.object(tools, "send_mail") as smtp, patch.object(tools, "load_sent_keys", return_value=set()):
            app = build_graph()
            cfg = {"configurable": {"thread_id": "approval-test"}, "recursion_limit": 25}
            app.invoke({"topic": "AI", "recipient": "test@example.com", "today": TODAY}, cfg)
            self.assertEqual(app.get_state(cfg).next, ("send",))
            smtp.assert_not_called()
            result = app.invoke(None, cfg)
            self.assertEqual(result["status"], "dry_run")
            smtp.assert_not_called()

    def test_empty_notice(self):
        mail = nodes.compose({"valid": [], "today": TODAY, "topic": "AI"})
        self.assertIn("조건에 맞는 공고가 없습니다", mail["mail_html"])
        self.assertEqual(rules.review_mail(mail["mail_subject"], mail["mail_html"], [], TODAY), [])

    def test_live_mode_still_requires_approval(self):
        with patch.dict(os.environ, DRY_RUN="0", OFFLINE="1", SMTP_USER="test@example.com"), \
             patch.object(tools, "send_mail") as smtp, \
             patch.object(tools, "save_sent_keys") as history, \
             patch.object(tools, "load_sent_keys", return_value=set()):
            app = build_graph()
            cfg = {"configurable": {"thread_id": "live-approval-test"}, "recursion_limit": 25}
            app.invoke({"topic": "AI", "recipient": "test@example.com", "today": TODAY}, cfg)
            self.assertEqual(app.get_state(cfg).next, ("send",))
            smtp.assert_not_called()
            result = app.invoke(None, cfg)
            self.assertEqual(result["status"], "sent")
            smtp.assert_called_once_with("test@example.com", result["mail_subject"], result["mail_html"])
            history.assert_called_once()


if __name__ == "__main__":
    unittest.main()
