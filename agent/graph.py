"""그래프 조립: 노드 등록 → 엣지 연결 → 조건부 엣지 → 체크포인터·interrupt 로 컴파일."""
from langgraph.checkpoint.memory import MemorySaver
from langgraph.graph import END, START, StateGraph

from . import nodes as n
from .state import AgentState


def build_graph(require_approval: bool = True):
    g = StateGraph(AgentState)

    # 1) 노드 등록: 이름(영문) ↔ 함수
    g.add_node("plan_queries", n.plan_queries)
    g.add_node("search", n.search)
    g.add_node("extract", n.extract)
    g.add_node("validate", n.validate)
    g.add_node("rewrite_queries", n.rewrite_queries)
    g.add_node("compose", n.compose)
    g.add_node("review", n.review)
    g.add_node("send", n.send)
    g.add_node("abort", n.abort)

    # 2) 일반 엣지: 순서대로
    g.add_edge(START, "plan_queries")
    g.add_edge("plan_queries", "search")
    g.add_edge("search", "extract")
    g.add_edge("extract", "validate")

    # 3) 조건부 엣지 ①: 유효 공고가 부족하면 검색어를 바꿔 다시 검색(순환)
    g.add_conditional_edges("validate", n.route_after_validate,
                            {"compose": "compose", "rewrite": "rewrite_queries"})
    g.add_edge("rewrite_queries", "search")

    # 4) 조건부 엣지 ②: 리뷰 게이트 — 통과해야만 발송
    g.add_edge("compose", "review")
    g.add_conditional_edges("review", n.route_after_review, {"send": "send", "abort": "abort"})
    g.add_edge("send", END)
    g.add_edge("abort", END)

    # 5) 체크포인터(기억) + human-in-the-loop: send 직전에 멈춘다
    return g.compile(checkpointer=MemorySaver(),
                     interrupt_before=["send"] if require_approval else [])
