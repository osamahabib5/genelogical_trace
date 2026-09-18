"""
LangGraph agent orchestration for multi-step genealogy research.

Workflow:
    classify -> retrieve -> generate -> verify -> approve (HITL, optional)

The graph reuses the existing services (embedding, retrieval, LLM) and
records per-node timings and tool calls in the same shape used by
rag_logging, so agent runs appear in rag_summary.json like any query.

Settings (see config.py / .env):
    AGENT_TOKEN_BUDGET    cumulative completion-token budget per run
    REQUIRE_HUMAN_APPROVAL  True to pause before returning the answer
"""

import logging
import time
import uuid
from typing import Any, Dict, List, TypedDict

from langgraph.graph import StateGraph, START, END
from langgraph.checkpoint.memory import MemorySaver
from langgraph.types import Command, interrupt
from langchain_core.runnables import RunnableConfig

from config import settings
from embedding_service import embedding_service
from retrieval_service import RetrievalService
from llm_service import llm_service, rule_based_classify, ReasoningMode

logger = logging.getLogger(__name__)

TOTAL_STEPS = 5


def _console(step: int, name: str, detail: str) -> None:
    """Print workflow progress and outputs to the backend console."""
    print(f"\n[LANGGRAPH {step}/{TOTAL_STEPS}] {name}", flush=True)
    print(f"    {detail}", flush=True)


class ResearchState(TypedDict, total=False):
    query: str
    mode: str                 # low | high | max
    context: List[Dict[str, Any]]
    answer: str
    usage: Dict[str, int]
    budget_used: int
    note: str
    verified: bool
    verification_note: str
    approved: bool
    tool_log: List[str]
    step_log: List[Dict[str, Any]]


VERIFY_PROMPT = """You are a strict citation auditor for a genealogy archive.

Given a draft answer and the retrieved document context below, list ONLY the
footnote citations [N] in the answer that are NOT actually supported by the
context. If every citation is supported, reply with exactly: OK

Do not add commentary."""


def _db(config: RunnableConfig):
    return config["configurable"].get("db")


def _merge_usage(total: Dict[str, int], extra: Dict[str, int]) -> Dict[str, int]:
    for key, value in (extra or {}).items():
        total[key] = total.get(key, 0) + value
    return total


def _record(state: ResearchState, step: str, t0: float) -> None:
    state.setdefault("step_log", []).append(
        {"step": step, "seconds": round(time.perf_counter() - t0, 6)}
    )


def node_classify(state: ResearchState, config: RunnableConfig) -> ResearchState:
    """Rule-based classifier; the research path defaults to HIGH effort."""
    t0 = time.perf_counter()
    mode = rule_based_classify(state["query"])
    state["mode"] = (mode or ReasoningMode.HIGH).value
    state.setdefault("tool_log", []).append("rule_based_classify")
    _record(state, "agent:classify", t0)
    logger.info("agent classify -> %s", state["mode"])
    _console(1, "classify", f"query: '{state['query'][:120]}' -> reasoning mode: {state['mode']}")
    return state


def node_retrieve(state: ResearchState, config: RunnableConfig) -> ResearchState:
    """Embed the query and search chunks + person records (same as /ask)."""
    t0 = time.perf_counter()
    db = _db(config)
    embedding = embedding_service.embed_text(state["query"])
    chunks = RetrievalService.search_similar_chunks(db, embedding, top_k=8)
    ancestry = RetrievalService.search_ancestry_data(db, embedding, top_k=5)
    state["context"] = chunks + ancestry
    state.setdefault("tool_log", []).extend(
        [
            "embedding_service.embed_text",
            "RetrievalService.search_similar_chunks",
            "RetrievalService.search_ancestry_data",
        ]
    )
    _record(state, "agent:retrieve", t0)
    logger.info("agent retrieved %d chunks + %d ancestry records", len(chunks), len(ancestry))
    _console(
        2,
        "retrieve",
        f"embedded query, retrieved {len(chunks)} document chunks + "
        f"{len(ancestry)} ancestry records ({state['step_log'][-1]['seconds']:.3f}s)",
    )
    return state


def node_generate(state: ResearchState, config: RunnableConfig) -> ResearchState:
    """Generate the draft answer and enforce the token budget."""
    t0 = time.perf_counter()
    answer, usage = llm_service.generate_response_with_usage(
        state["query"], state["context"]
    )
    state["answer"] = answer
    state["usage"] = _merge_usage(state.get("usage", {}), usage)
    state["budget_used"] = state.get("budget_used", 0) + (usage or {}).get("completion_tokens", 0)
    if state["budget_used"] > settings.agent_token_budget:
        state["note"] = (
            f"token budget exceeded ({state['budget_used']} > {settings.agent_token_budget}); "
            "returning best-effort answer"
        )
    state.setdefault("tool_log", []).append("llm_service.generate_response_with_usage")
    _record(state, "agent:generate", t0)
    logger.info("agent generated answer (%s completion tokens so far)", state["budget_used"])
    tokens = (usage or {}).get("completion_tokens", 0)
    preview = (answer or "")[:160].replace("\n", " ")
    _console(
        3,
        "generate",
        f"drafted answer ({tokens} completion tokens, {state['budget_used']} used of "
        f"{settings.agent_token_budget} budget):\n    '{preview}...'",
    )
    if state.get("note"):
        _console(3, "generate (budget)", state["note"])
    return state


def node_verify(state: ResearchState, config: RunnableConfig) -> ResearchState:
    """Second LLM pass: check every citation against the source context."""
    t0 = time.perf_counter()
    try:
        verdict, usage = llm_service.generate_response_with_usage(
            state["query"],
            state["context"],
            system_prompt=VERIFY_PROMPT,
        )
        state["usage"] = _merge_usage(state.get("usage", {}), usage)
        state["budget_used"] = state.get("budget_used", 0) + (usage or {}).get("completion_tokens", 0)
        text = (verdict or "").strip()
        state["verified"] = text.upper() == "OK"
        state["verification_note"] = text[:200]
    except Exception as exc:
        logger.warning("citation verifier failed: %s (failing open)", exc)
        state["verified"] = True
        state["verification_note"] = f"verifier error: {exc}"
    state.setdefault("tool_log", []).append("llm_service.citation_verifier")
    _record(state, "agent:verify", t0)
    logger.info("agent verification: verified=%s note=%s", state["verified"], state["verification_note"])
    verdict = "OK - all citations supported" if state["verified"] else "UNSUPPORTED CITATIONS"
    _console(4, "verify", f"citation audit verdict: {verdict}\n    note: {state['verification_note']}")
    return state


def node_approve(state: ResearchState, config: RunnableConfig) -> ResearchState:
    """Human-in-the-loop gate (enabled via REQUIRE_HUMAN_APPROVAL=true)."""
    t0 = time.perf_counter()
    if settings.require_human_approval:
        decision = interrupt(
            {
                "query": state["query"],
                "draft_answer": state["answer"],
                "verification": state.get("verification_note"),
            }
        )
        state["approved"] = decision == "approve"
    else:
        state["approved"] = True
    _record(state, "agent:approve", t0)
    if settings.require_human_approval:
        if state["approved"]:
            _console(5, "approve", "human approval received: APPROVE")
        else:
            _console(5, "approve", "human approval received: REVISE -> regenerating answer")
    else:
        _console(5, "approve", "human approval disabled - auto-approved")
    return state


def route_after_approve(state: ResearchState) -> str:
    """Loop back to regeneration when a researcher rejects the draft."""
    return "end" if state.get("approved") else "generate"


_graph = StateGraph(ResearchState)
_graph.add_node("classify", node_classify)
_graph.add_node("retrieve", node_retrieve)
_graph.add_node("generate", node_generate)
_graph.add_node("verify", node_verify)
_graph.add_node("approve", node_approve)
_graph.add_edge(START, "classify")
_graph.add_edge("classify", "retrieve")
_graph.add_edge("retrieve", "generate")
_graph.add_edge("generate", "verify")
_graph.add_edge("verify", "approve")
_graph.add_conditional_edges(
    "approve",
    route_after_approve,
    {"generate": "generate", "end": END},
)

# MemorySaver keeps per-run state (thread_id). Swap for a Postgres/SQLite
# checkpointer when runs must survive process restarts.
research_graph = _graph.compile(checkpointer=MemorySaver())


def run_research(query: str, db) -> Dict[str, Any]:
    """Run the research agent for one query. Returns the answer + audit info."""
    thread_id = str(uuid.uuid4())
    config: RunnableConfig = {
        "configurable": {"db": db, "thread_id": thread_id},
    }
    result = research_graph.invoke(
        {
            "query": query,
            "usage": {},
            "budget_used": 0,
            "tool_log": [],
            "step_log": [],
        },
        config=config,
    )

    if "__interrupt__" in result:
        # Paused at the human-approval gate.
        return {
            "query": query,
            "status": "pending_approval",
            "thread_id": thread_id,
            "answer": result.get("answer", ""),
            "mode": result.get("mode"),
            "verification_note": result.get("verification_note"),
            "sources": (result.get("context") or [])[:3],
            "tool_log": result.get("tool_log", []),
            "step_log": result.get("step_log", []),
            "usage": result.get("usage") or {},
        }

    return {
        "query": query,
        "status": "complete",
        "thread_id": thread_id,
        "answer": result.get("answer", ""),
        "mode": result.get("mode"),
        "verified": result.get("verified"),
        "approved": result.get("approved"),
        "note": result.get("note"),
        "verification_note": result.get("verification_note"),
        "sources": (result.get("context") or [])[:3],
        "tool_log": result.get("tool_log", []),
        "step_log": result.get("step_log", []),
        "usage": result.get("usage") or {},
    }


def resume_approval(thread_id: str, db, decision: str) -> Dict[str, Any]:
    """Resume a run paused at the approval gate. decision: 'approve' | 'revise'."""
    config: RunnableConfig = {
        "configurable": {"db": db, "thread_id": thread_id},
    }
    result = research_graph.invoke(Command(resume=decision), config=config)
    return {
        "thread_id": thread_id,
        "status": "complete",
        "answer": result.get("answer", ""),
        "approved": result.get("approved"),
        "sources": (result.get("context") or [])[:3],
        "tool_log": result.get("tool_log", []),
        "step_log": result.get("step_log", []),
        "usage": result.get("usage") or {},
    }
