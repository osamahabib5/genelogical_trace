#!/usr/bin/env python3
"""Evaluate the LangGraph genealogy research workflow against the gold set.

Run from the repository root with the database and configured embedding/LLM
services available. The evaluator appends JSONL records and does not store
retrieved source text in its output.
"""

import argparse
import json
import logging
import re
import sys
import time
from collections import Counter
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List, Optional, Sequence, Tuple

ROOT = Path(__file__).resolve().parent
BACKEND = ROOT / "app" / "backend"
if str(BACKEND) not in sys.path:
    sys.path.insert(0, str(BACKEND))

from agent_orchestration import run_research  # noqa: E402
from config import settings  # noqa: E402
from database import SessionLocal  # noqa: E402
from llm_service import llm_service  # noqa: E402
from rag_evaluation import parse_eval_markdown  # noqa: E402
from rag_logging import estimate_llm_cost  # noqa: E402

DEFAULT_EVAL_FILE = ROOT / "sofafea_rag_eval.md"
DEFAULT_OUTPUT = ROOT / "app" / "backend" / "agent_evaluation_results.jsonl"
EXPECTED_NODES = ["classify", "retrieve", "generate", "verify", "approve"]
EXPECTED_TOOL_BASE = {
    "embedding_service.embed_text",
    "llm_service.generate_response_with_usage",
    "llm_service.citation_verifier",
}
MULTI_AGENT_METRICS = {
    "handoff_accuracy": "not_applicable: the current research graph has one agent and no handoffs",
    "inter_agent_consistency": "not_applicable: the current research graph has no specialist agents",
    "coordination_overhead": "not_applicable: there is no multi-agent orchestration layer",
}

JUDGE_PROMPT = """You are a strict evaluator of an AI research answer. Return JSON only.
Do not reveal or infer private chain-of-thought. Judge only the observable answer
and evidence supplied. Treat the gold answer as a reference, allowing correct
paraphrases and explicitly acknowledged uncertainty when the source is ambiguous.
Return exactly:
{
  "goal_completed": true or false,
  "answer_score": 0, 1, or 2,
  "reasoning_coherence_score": 0, 1, or 2,
  "claims": [{"claim": "short factual claim", "supported": true or false}],
  "reason": "one short sentence"
}
Score 2 means complete/accurate/coherent, 1 means partly correct or incomplete,
and 0 means incorrect, unsupported, incoherent, or an unjustified refusal. For
goal_completed, decide whether the answer fulfills the question's objective.
List atomic factual claims from the answer and mark each supported only when the
provided context supports it. Do not treat citations alone as evidence."""


logger = logging.getLogger("agent_evaluation")


def _exception_details(exc: Exception) -> str:
    """Return the exception and nested transport causes in readable form."""
    details = []
    current = exc
    seen = set()
    while current is not None and id(current) not in seen:
        seen.add(id(current))
        message = str(current).strip() or repr(current)
        details.append(f"{type(current).__name__}: {message}")
        current = current.__cause__ or current.__context__
    return " <- ".join(details)


def _stop_on_agent_error(case: Dict[str, Any], result: Dict[str, Any]) -> None:
    """Stop the eval immediately after a failed workflow service call."""
    failures = [call for call in result.get("call_trace", []) if call.get("status") == "error"]
    answer = str(result.get("answer") or "")
    error = result.get("error")
    if not failures and not error and not answer.startswith("Error generating response:"):
        return

    failed_names = ", ".join(call.get("name", "unknown call") for call in failures)
    detail = answer.removeprefix("Error generating response:").strip() or error
    if not detail:
        detail = "; ".join(
            f"{call.get('name', 'unknown call')}: {call.get('error_type', 'unknown error')}"
            for call in failures
        )
    print(
        f"\nEVALUATION STOPPED after {case['id']} due to a workflow error.\n"
        f"Provider/model: {settings.llm_provider}/{llm_service.get_active_model_name()}\n"
        f"Failed call(s): {failed_names or 'workflow'}\n"
        f"Detailed error: {detail}",
        file=sys.stderr,
        flush=True,
    )
    raise SystemExit(2)


def _parse_json(text: str) -> Optional[Dict[str, Any]]:
    if not text:
        return None
    cleaned = re.sub(r"^```(?:json)?\s*|\s*```$", "", text.strip(), flags=re.M)
    start, end = cleaned.find("{"), cleaned.rfind("}")
    if start < 0 or end < start:
        return None
    try:
        value = json.loads(cleaned[start : end + 1])
        return value if isinstance(value, dict) else None
    except json.JSONDecodeError:
        return None


def _context_text(context: Sequence[Dict[str, Any]], cap: int = 12000) -> str:
    parts = []
    for item in context:
        title = item.get("document_title") or item.get("person_name") or "record"
        body = item.get("text") or item.get("raw_text") or ""
        if not body:
            body = "; ".join(
                f"{k}: {v}" for k, v in item.items()
                if k not in {"embedding", "similarity_score"} and v not in (None, "")
            )
        parts.append(f"[{title}] {body}")
    return "\n\n".join(parts)[:cap]


def _judge(case: Dict[str, Any], answer: str, context: Sequence[Dict[str, Any]]) -> Tuple[Optional[Dict[str, Any]], Dict[str, Any]]:
    payload = (
        f"Question:\n{case['question']}\n\n"
        f"Gold answer / expected behavior:\n{case['expected_answer'] or '(No gold answer; abstention is expected.)'}\n\n"
        f"Source expectation:\n{case.get('expected_source') or '(not specified)'}\n\n"
        f"Failure modes to watch for:\n{case.get('watch_for') or '(none specified)'}\n\n"
        f"Retrieved evidence:\n{_context_text(context)}\n\n"
        f"Agent answer:\n{answer}"
    )
    try:
        raw, usage = llm_service.generate_response_with_usage(
            payload, [], system_prompt=JUDGE_PROMPT
        )
        if raw.startswith("Error generating response:"):
            detail = raw.removeprefix("Error generating response:").strip()
            logger.error("LLM judge provider call failed: %s", detail)
            return None, {"error": detail}
        return _parse_json(raw), usage or {}
    except Exception as exc:
        logger.exception("LLM judge call failed")
        return None, {"error": _exception_details(exc)}


def _path_metrics(result: Dict[str, Any]) -> Dict[str, Any]:
    steps = result.get("step_log") or []
    nodes = [str(item.get("step", "")).removeprefix("agent:") for item in steps]
    approvals = result.get("approval_trace") or []
    status = result.get("status")
    complete = status == "complete"
    answer = str(result.get("answer") or "")
    service_failed = any(
        call.get("status") == "error"
        for call in result.get("call_trace", [])
    )
    error_answer = answer.startswith("Error generating response:")

    # The implemented graph has one normal pass. A human "revise" decision
    # permits another generate -> verify -> approve cycle.
    expected = ["classify", "retrieve"]
    for i, approval in enumerate(approvals):
        expected.extend(["generate", "verify", "approve"])
        if approval.get("decision") != "revise":
            break
    if complete and (not approvals or approvals[-1].get("decision") == "revise"):
        expected.extend(["generate", "verify", "approve"])

    known = {"classify", "retrieve", "generate", "verify", "approve"}
    valid = bool(nodes) and all(node in known for node in nodes)
    valid = valid and nodes[:2] == ["classify", "retrieve"]
    valid = valid and len(nodes) >= 4 and nodes[2:4] == ["generate", "verify"]
    # Check every transition, including the intentional revise loop.
    for idx, node in enumerate(nodes):
        if idx == 0:
            continue
        previous = nodes[idx - 1]
        allowed = {
            "classify": {"retrieve"},
            "retrieve": {"generate"},
            "generate": {"verify"},
            "verify": {"approve"},
            "approve": {"generate"},
        }
        if node not in allowed.get(previous, set()):
            valid = False
            break
    if complete:
        valid = valid and nodes[-1] == "approve"

    trajectory_exact = complete and nodes == expected
    shortest = len(EXPECTED_NODES)
    efficiency = round(min(1.0, shortest / len(nodes)), 4) if nodes and complete else None
    return {
        "node_sequence": nodes,
        "expected_node_sequence": expected,
        "trajectory_valid": valid,
        "trajectory_accuracy": int(trajectory_exact),
        "workflow_path_validity": int(valid),
        "step_count": len(nodes),
        "step_efficiency": efficiency,
        "task_completed": bool(complete and answer and not error_answer and not service_failed),
        "service_call_failure": service_failed or error_answer,
        "pending_human_approval": status == "pending_approval",
    }


def _expected_tools() -> set:
    chunk = "RetrievalService.search_hybrid_chunks" if settings.hybrid_search else "RetrievalService.search_similar_chunks"
    ancestry = "RetrievalService.search_hybrid_ancestry" if settings.hybrid_search else "RetrievalService.search_ancestry_data"
    return EXPECTED_TOOL_BASE | {chunk, ancestry}


def _tool_metrics(result: Dict[str, Any]) -> Dict[str, Any]:
    calls = result.get("call_trace") or []
    expected = _expected_tools()
    actual = {call.get("name") for call in calls if call.get("name")}
    intersection = actual & expected
    precision = len(intersection) / len(actual) if actual else 0.0
    recall = len(intersection) / len(expected) if expected else 1.0
    f1 = 2 * precision * recall / (precision + recall) if precision + recall else 0.0

    retrieval_counts = {}
    for call in calls:
        if call.get("node") == "retrieve" and call.get("status") == "ok":
            name = call.get("name", "")
            retrieval_counts[name] = (call.get("result") or {}).get("result_count", 0)
    expected_context_count = sum(retrieval_counts.values())
    valid_calls = 0
    for call in calls:
        name = call.get("name")
        args = call.get("arguments") or {}
        result_data = call.get("result") or {}
        valid = call.get("status") == "ok" and name in expected
        if name == "embedding_service.embed_text":
            valid = valid and args.get("query_chars", 0) > 0
            valid = valid and result_data.get("dimensions") == settings.embedding_dimension
        elif name and name.startswith("RetrievalService.search_"):
            is_ancestry = "ancestry" in name
            valid = valid and args.get("top_k") == (5 if is_ancestry else 8)
            valid = valid and args.get("hybrid") == settings.hybrid_search
            valid = valid and args.get("query_chars", 0) > 0
        elif name in {"llm_service.generate_response_with_usage", "llm_service.citation_verifier"}:
            valid = valid and args.get("context_count") == expected_context_count
        else:
            valid = False
        valid_calls += int(bool(valid))

    # Retries of generation/verification after a requested human revision are
    # intentional. Duplicate embeddings/retrievals with identical arguments
    # are counted as potentially redundant.
    seen = set()
    redundant = 0
    repeatable = {"embedding_service.embed_text"} | {
        name for name in expected if name.startswith("RetrievalService.search_")
    }
    for call in calls:
        name = call.get("name")
        if name not in repeatable:
            continue
        signature = (name, json.dumps(call.get("arguments") or {}, sort_keys=True))
        if signature in seen:
            redundant += 1
        seen.add(signature)

    action_nodes = {"retrieve", "generate", "verify"}
    node_instances_with_calls = {
        (call.get("node"), call.get("node_iteration"))
        for call in calls
        if call.get("node") and call.get("node_iteration")
    }
    node_count = len(result.get("step_log") or [])
    return {
        "expected_tools": sorted(expected),
        "actual_tools": sorted(actual),
        "tool_selection_precision": round(precision, 4),
        "tool_selection_recall": round(recall, 4),
        "tool_selection_accuracy": round(f1, 4),
        "tool_call_accuracy": round(valid_calls / len(calls), 4) if calls else 0.0,
        "tool_calls_total": len(calls),
        "tool_use_rate": round(
            sum(node in action_nodes for node, _ in node_instances_with_calls) / node_count,
            4,
        ) if node_count else 0.0,
        "redundant_tool_calls": redundant,
        "call_trace": calls,
    }


def _jaccard_answers(answers: Sequence[str]) -> Optional[float]:
    answers = [answer for answer in answers if not answer.startswith("Error generating response:")]
    if len(answers) < 2:
        return None
    token_sets = [
        set(re.findall(r"[a-z0-9]+", answer.lower()))
        for answer in answers
    ]
    pair_scores = []
    for i in range(len(token_sets)):
        for j in range(i + 1, len(token_sets)):
            union = token_sets[i] | token_sets[j]
            pair_scores.append(len(token_sets[i] & token_sets[j]) / len(union) if union else 1.0)
    return round(sum(pair_scores) / len(pair_scores), 4) if pair_scores else None


def _append(path: Path, record: Dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("a", encoding="utf-8") as stream:
        stream.write(json.dumps(record, ensure_ascii=False, default=str) + "\n")


def _average(records: Sequence[Dict[str, Any]], key: str) -> Optional[float]:
    values = [r[key] for r in records if isinstance(r.get(key), (int, float))]
    return round(sum(values) / len(values), 4) if values else None


def main() -> None:
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s %(levelname)s %(name)s: %(message)s",
    )
    parser = argparse.ArgumentParser(description="Evaluate the LangGraph research agent against the project gold set.")
    parser.add_argument("--eval-file", default=str(DEFAULT_EVAL_FILE))
    parser.add_argument("--output", default=str(DEFAULT_OUTPUT))
    parser.add_argument("--questions", default="", help="Question ids, e.g. Q1,Q8,Q22")
    parser.add_argument("--limit", type=int, default=0)
    parser.add_argument("--repeats", type=int, default=1, help="Runs per question for self-consistency scoring")
    parser.add_argument("--skip-judge", action="store_true", help="Skip LLM answer/coherence/hallucination judging")
    parser.add_argument("--tag", default="", help="Variant label for comparisons")
    args = parser.parse_args()

    eval_path = Path(args.eval_file)
    if not eval_path.exists():
        raise SystemExit(f"Eval file not found: {eval_path}")
    cases = parse_eval_markdown(eval_path)
    if args.questions:
        wanted = {item.strip().upper() for item in args.questions.split(",") if item.strip()}
        cases = [case for case in cases if case["id"] in wanted]
    if args.limit:
        cases = cases[: args.limit]
    if not cases:
        raise SystemExit("No evaluation questions selected.")
    if args.repeats < 1:
        raise SystemExit("--repeats must be at least 1")

    run_id = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
    db = SessionLocal()
    records: List[Dict[str, Any]] = []
    started = time.perf_counter()
    try:
        for case in cases:
            case_records = []
            for repeat in range(1, args.repeats + 1):
                print(f"[{case['id']} run {repeat}/{args.repeats}] {case['question'][:75]}", flush=True)
                t0 = time.perf_counter()
                try:
                    result = run_research(case["question"], db, include_eval_data=True)
                except Exception as exc:
                    result = {
                        "status": "error",
                        "answer": "",
                        "step_log": [],
                        "call_trace": [],
                        "approval_trace": [],
                        "eval_context": [],
                        "error": f"{type(exc).__name__}: {exc}",
                    }
                _stop_on_agent_error(case, result)
                context = result.get("eval_context") or []
                answer = result.get("answer") or ""
                record = {
                    "record_type": "agent_question",
                    "run_id": run_id,
                    "variant": args.tag or "untagged",
                    "question_id": case["id"],
                    "repeat": repeat,
                    "question": case["question"],
                    "expected_answer": case["expected_answer"],
                    "expected_source": case.get("expected_source"),
                    "watch_for": case.get("watch_for"),
                    "status": result.get("status"),
                    "answer": answer,
                    "mode": result.get("mode"),
                    "verified": result.get("verified"),
                    "verification_note": result.get("verification_note"),
                    "human_approval_trace": result.get("approval_trace") or [],
                    "duration_seconds": round(time.perf_counter() - t0, 4),
                    "agent_usage": result.get("usage") or {},
                    "error": result.get("error"),
                }
                usage = record["agent_usage"]
                has_call_failure = any(
                    call.get("status") == "error"
                    for call in result.get("call_trace", [])
                ) or answer.startswith("Error generating response:")
                if has_call_failure or (
                    settings.llm_provider != "ollama"
                    and not usage.get("prompt_tokens")
                    and not usage.get("completion_tokens")
                ):
                    record["agent_cost_usd"] = None
                else:
                    record["agent_cost_usd"] = estimate_llm_cost(
                        provider=settings.llm_provider,
                        model=llm_service.get_active_model_name(),
                        input_tokens=usage.get("prompt_tokens"),
                        output_tokens=usage.get("completion_tokens"),
                        input_cache_hit_tokens=usage.get("prompt_cache_hit_tokens"),
                        input_cache_miss_tokens=usage.get("prompt_cache_miss_tokens"),
                    )
                record.update(_path_metrics(result))
                record.update(_tool_metrics(result))

                if not args.skip_judge and answer:
                    judged, judge_usage = _judge(case, answer, context)
                    record["judge_usage"] = judge_usage
                    if judge_usage.get("error"):
                        print(
                            f"\nEVALUATION STOPPED after {case['id']} due to an LLM judge error.\n"
                            f"Provider/model: {settings.llm_provider}/{llm_service.get_active_model_name()}\n"
                            f"Detailed error: {judge_usage['error']}",
                            file=sys.stderr,
                            flush=True,
                        )
                        raise SystemExit(2)
                    if judge_usage.get("error") or (
                        settings.llm_provider != "ollama"
                        and not judge_usage.get("prompt_tokens")
                        and not judge_usage.get("completion_tokens")
                    ):
                        record["judge_cost_usd"] = None
                    else:
                        record["judge_cost_usd"] = estimate_llm_cost(
                            provider=settings.llm_provider,
                            model=llm_service.get_active_model_name(),
                            input_tokens=judge_usage.get("prompt_tokens"),
                            output_tokens=judge_usage.get("completion_tokens"),
                            input_cache_hit_tokens=judge_usage.get("prompt_cache_hit_tokens"),
                            input_cache_miss_tokens=judge_usage.get("prompt_cache_miss_tokens"),
                        )
                    if judged:
                        record["goal_completion"] = int(bool(judged.get("goal_completed")))
                        score = judged.get("answer_score")
                        record["answer_score"] = int(score) if score in (0, 1, 2) else None
                        coherence = judged.get("reasoning_coherence_score")
                        record["reasoning_coherence"] = int(coherence) if coherence in (0, 1, 2) else None
                        claims = judged.get("claims") or []
                        valid_claims = [claim for claim in claims if isinstance(claim, dict) and "supported" in claim]
                        record["claim_count"] = len(valid_claims)
                        record["unsupported_claim_count"] = sum(not bool(c.get("supported")) for c in valid_claims)
                        record["hallucination_rate"] = (
                            round(record["unsupported_claim_count"] / len(valid_claims), 4)
                            if valid_claims else 0.0
                        )
                        record["judge_reason"] = judged.get("reason")
                    else:
                        record["judge_error"] = judge_usage.get("error", "invalid judge JSON")
                else:
                    record["goal_completion"] = None
                    record["answer_score"] = None
                    record["reasoning_coherence"] = None
                    record["hallucination_rate"] = None

                case_records.append(record)
                records.append(record)
            consistency = _jaccard_answers([r.get("answer", "") for r in case_records if r.get("answer")])
            for record in case_records:
                record["self_consistency_jaccard"] = consistency
                _append(Path(args.output), record)

    finally:
        db.close()

    # Human-review metrics use explicit decisions only; automatic approvals
    # and unresolved pauses are not counted as researcher acceptance.
    human_decisions = [
        approval.get("decision")
        for record in records
        for approval in record.get("human_approval_trace", [])
        if approval.get("human") and approval.get("decision") in {"approve", "revise"}
    ]
    summary = {
        "record_type": "agent_summary",
        "run_id": run_id,
        "variant": args.tag or "untagged",
        "timestamp_utc": datetime.now(timezone.utc).isoformat(),
        "questions": len(cases),
        "attempts": len(records),
        "repeats_per_question": args.repeats,
        "elapsed_seconds": round(time.perf_counter() - started, 2),
        "metrics": {
            "task_completion_rate": _average(records, "task_completed"),
            "goal_completion_rate": _average(records, "goal_completion"),
            "mean_answer_score_0_to_2": _average(records, "answer_score"),
            "trajectory_accuracy": _average(records, "trajectory_accuracy"),
            "workflow_path_validity": _average(records, "workflow_path_validity"),
            "step_efficiency": _average(records, "step_efficiency"),
            "tool_selection_accuracy_f1": _average(records, "tool_selection_accuracy"),
            "tool_call_accuracy": _average(records, "tool_call_accuracy"),
            "tool_use_rate": _average(records, "tool_use_rate"),
            "redundant_tool_calls_per_run": _average(records, "redundant_tool_calls"),
            "reasoning_coherence_0_to_2": _average(records, "reasoning_coherence"),
            "hallucination_rate": _average(records, "hallucination_rate"),
            "self_consistency_jaccard": _average(records, "self_consistency_jaccard"),
            "mean_latency_seconds": _average(records, "duration_seconds"),
            "mean_agent_cost_usd": _average(records, "agent_cost_usd"),
            "mean_judge_cost_usd": _average(records, "judge_cost_usd"),
            "mean_agent_completion_tokens": _average(
                [
                    {"completion_tokens": (r.get("agent_usage") or {}).get("completion_tokens")}
                    for r in records
                ],
                "completion_tokens",
            ),
            "human_approval_rate": (
                sum(decision == "approve" for decision in human_decisions) / len(human_decisions)
                if human_decisions else None
            ),
            "human_review_coverage": (
                sum(bool(r.get("human_approval_trace")) and any(
                    a.get("human") and a.get("decision") in {"approve", "revise"}
                    for a in r.get("human_approval_trace", [])
                ) for r in records) / len(records)
                if records else 0.0
            ),
            "plan_validity": None,
            "reasoning_chain_coherence": None,
            "handoff_accuracy": None,
            "inter_agent_consistency": None,
            "coordination_overhead": None,
        },
        "human_review_decisions": dict(Counter(human_decisions)),
        "not_measured_or_not_applicable": {
            "plan_validity": "not_applicable: this graph follows a fixed workflow and does not generate an initial plan",
            "reasoning_chain_coherence": "not_measured: private chain-of-thought is not collected; answer/evidence coherence is scored instead",
            "human_acceptance_rate": "not_available unless runs are resumed with actual human decisions",
            **MULTI_AGENT_METRICS,
        },
        "judge_enabled": not args.skip_judge,
        "self_consistency_method": "pairwise token-set Jaccard similarity; lexical proxy, not semantic equivalence",
        "llm_provider": settings.llm_provider,
        "llm_model": llm_service.get_active_model_name(),
    }
    _append(Path(args.output), summary)
    print("\nAgent evaluation summary")
    for name, value in summary["metrics"].items():
        print(f"  {name}: {value if value is not None else 'n/a'}")
    print(f"Results appended to {args.output}")


if __name__ == "__main__":
    main()
