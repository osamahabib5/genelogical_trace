"""
RAG pipeline event logging.

Every notable action in the RAG pipeline (chatbot queries, file uploads,
deletions, and views) is recorded to a JSON summary file with `log_rag_event`.
The file is created on first use and events are always appended — existing
entries are never overwritten.

The output file uses JSON Lines format: one JSON object per line, so the
file can be streamed or parsed line by line (e.g. with `jq` or
`json.loads(line)`), and complex fields (`steps_taken`, `tools_called`,
`api_calls_made`) are stored as real JSON arrays instead of encoded strings.

Usage example (mirrors the /api/queries/ask pipeline in this project):
-------------------------------------------------------------------------
    from rag_logging import log_rag_event, rag_event_context, step_timer

    def run_rag_pipeline(user_query: str) -> str:
        with rag_event_context("query", query_text=user_query) as event:
            # 1. Embed the query (external API call), timed per step
            with step_timer(event, "embed query"):
                query_embedding = embedding_service.embed_text(user_query)
            event["api_calls_made"].append("ollama-embed (nomic-embed-text)")

            # 2. Retrieve similar chunks + ancestry records
            with step_timer(event, "vector retrieval"):
                chunks = RetrievalService.search_similar_chunks(db, query_embedding, top_k=8)
                ancestry = RetrievalService.search_ancestry_data(db, query_embedding, top_k=5)
            event["tools_called"].extend(
                [
                    "RetrievalService.search_similar_chunks",
                    "RetrievalService.search_ancestry_data",
                ]
            )

            # 3. Generate the final answer
            with step_timer(event, "llm answer generation") as llm_step:
                answer, usage = llm_service.generate_response_with_usage(user_query, chunks + ancestry)
            event["response_time_seconds"] = llm_step["seconds"]
            event["api_calls_made"].append("deepseek-v4-pro (chat completion)")
            event["final_response"] = answer
            event["input_tokens"] = (usage or {}).get("prompt_tokens")
            event["output_tokens"] = (usage or {}).get("completion_tokens")
            event["input_cache_hit_tokens"] = (usage or {}).get("prompt_cache_hit_tokens")
            event["input_cache_miss_tokens"] = (usage or {}).get("prompt_cache_miss_tokens")
            event["pricing_rate"] = deepseek_pricing_rate()
            event["estimated_cost_usd"] = estimate_llm_cost(
                provider=settings.llm_provider,
                model=llm_service.get_active_model_name(),
                input_tokens=event["input_tokens"],
                output_tokens=event["output_tokens"],
                input_cache_hit_tokens=event["input_cache_hit_tokens"],
                input_cache_miss_tokens=event["input_cache_miss_tokens"],
            )
            return answer
-------------------------------------------------------------------------
"""

import json
import logging
import threading
import time
from contextlib import contextmanager
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any, Dict, Iterator, List, Optional, Tuple, Union

logger = logging.getLogger(__name__)

VALID_ACTION_TYPES = {"query", "file_upload", "file_delete", "file_view"}

# Default output file sits next to this module (app/backend/rag_summary.json).
DEFAULT_JSON_PATH = Path(__file__).resolve().parent / "rag_summary.json"

# Serializes appends from concurrent FastAPI requests.
_WRITE_LOCK = threading.Lock()

# Fixed EDT (UTC-4) for all timestamps — no daylight saving adjustments.
_TZ = timezone(timedelta(hours=-4))


def _timestamp_edt() -> str:
    """Current time in fixed EDT, formatted as 'YYYY-MM-DD HH:MM:SS EDT'."""
    edt_now = datetime.now(timezone.utc).astimezone(_TZ)
    return f"{edt_now.strftime('%Y-%m-%d %H:%M:%S')} EDT"


def _round_seconds(value: Optional[float]) -> Optional[float]:
    """Round a duration to microsecond precision (None passes through)."""
    if value is None:
        return None
    return round(value, 6)


# DeepSeek V4 official pricing, USD per 1M tokens (see api-docs.deepseek.com).
# Each entry is (input_cache_hit, input_cache_miss, output).
# Peak hours: 01:00-04:00 and 06:00-10:00 UTC; all other hours are off-peak
# (off-peak rates are half of the peak rates).
DEEPSEEK_V4_PRICING_USD_PER_1M: Dict[str, Dict[str, Tuple[float, float, float]]] = {
    "peak": {
        "deepseek-v4-flash": (0.014, 0.44, 1.32),
        "deepseek-v4-pro": (0.044, 1.32, 3.96),
    },
    "off-peak": {
        "deepseek-v4-flash": (0.007, 0.22, 0.66),
        "deepseek-v4-pro": (0.022, 0.66, 1.98),
    },
}

# Flat USD per 1M tokens for other providers, keyed by model name:
# (input_rate, output_rate). Update these to match each provider's current
# price list. Local Ollama models are free and cost $0.00.
TOKEN_PRICING_USD_PER_1M: Dict[str, Tuple[float, float]] = {
    "deepseek-chat": (0.27, 1.10),  # legacy DeepSeek V3 model names
    "deepseek-reasoner": (0.55, 2.19),
    "gpt-4o-mini": (0.15, 0.60),
    "gpt-4o": (2.50, 10.00),
    "llama-3.1-8b-instant": (0.05, 0.08),
    "llama3.2:1b": (0.0, 0.0),
}


def is_deepseek_peak_hours() -> bool:
    """Whether the current UTC time falls in DeepSeek peak pricing hours."""
    hour = datetime.now(timezone.utc).hour
    # Peak: 01:00-04:00 UTC (hours 1-3) and 06:00-10:00 UTC (hours 6-9).
    return hour in (1, 2, 3, 6, 7, 8, 9)


def deepseek_pricing_rate() -> str:
    """Current DeepSeek billing bucket: 'peak' or 'off-peak'."""
    return "peak" if is_deepseek_peak_hours() else "off-peak"


def estimate_llm_cost(
    provider: str,
    model: str,
    input_tokens: Optional[int],
    output_tokens: Optional[int],
    input_cache_hit_tokens: Optional[int] = None,
    input_cache_miss_tokens: Optional[int] = None,
) -> Optional[float]:
    """Estimate the USD cost of an LLM call for the given provider/model.

    DeepSeek V4 models use the official peak/off-peak rates and split input
    tokens into cache hits and misses (usage.prompt_cache_hit_tokens /
    usage.prompt_cache_miss_tokens). If no cache breakdown is available, all
    input tokens are billed as cache misses. Returns 0.0 for local (Ollama)
    models and None when no pricing is configured for the model.
    """
    input_tokens = input_tokens or 0
    output_tokens = output_tokens or 0
    if provider == "ollama":
        return 0.0

    if provider == "deepseek":
        v4_pricing = DEEPSEEK_V4_PRICING_USD_PER_1M[deepseek_pricing_rate()]
        pricing = v4_pricing.get(model)
        if pricing is not None:
            hit_rate, miss_rate, output_rate = pricing
            cache_hit = input_cache_hit_tokens or 0
            cache_miss = input_cache_miss_tokens or 0
            if cache_hit + cache_miss == 0 and input_tokens > 0:
                # No cache breakdown reported: bill all input as misses.
                cache_miss = input_tokens
            return round(
                (cache_hit * hit_rate + cache_miss * miss_rate + output_tokens * output_rate)
                / 1_000_000,
                6,
            )

    pricing = TOKEN_PRICING_USD_PER_1M.get(model)
    if pricing is None:
        logger.warning(
            "No token pricing configured for model '%s' (provider=%s); "
            "cost recorded as null",
            model,
            provider,
        )
        return None
    input_rate, output_rate = pricing
    return round(
        (input_tokens * input_rate + output_tokens * output_rate) / 1_000_000,
        6,
    )


def log_rag_event(
    action_type: str,
    *,
    duration_seconds: Optional[float] = None,
    file_name: Optional[str] = None,
    query_text: Optional[str] = None,
    steps_taken: Optional[List[Any]] = None,
    tools_called: Optional[List[str]] = None,
    api_calls_made: Optional[List[str]] = None,
    final_response: Optional[str] = None,
    response_time_seconds: Optional[float] = None,
    input_tokens: Optional[int] = None,
    output_tokens: Optional[int] = None,
    input_cache_hit_tokens: Optional[int] = None,
    input_cache_miss_tokens: Optional[int] = None,
    estimated_cost_usd: Optional[float] = None,
    pricing_rate: Optional[str] = None,
    reasoning_mode: Optional[str] = None,
    json_path: Optional[Union[str, Path]] = None,
) -> None:
    """Append one event object to the RAG summary JSON Lines file.

    Creates `rag_summary.json` on first use and appends one JSON object per
    line on every call. Existing entries are never overwritten.

    Args:
        action_type: One of "query", "file_upload", "file_delete", "file_view".
        duration_seconds: Total time the action took.
        file_name: File involved, if any.
        query_text: User's question, for query events.
        steps_taken: Ordered list of pipeline steps. Use step_timer() to add
            timed entries like {"step": name, "seconds": ...}; plain strings
            are also accepted.
        tools_called: Names of tools/functions invoked.
        api_calls_made: External API calls (e.g. embedding API, LLM API).
        final_response: Chatbot's answer, or status message for file actions.
        response_time_seconds: Time spent specifically on the LLM/response step.
        input_tokens: Prompt tokens used by the LLM call, if available.
        output_tokens: Completion tokens generated by the LLM call, if available.
        input_cache_hit_tokens: Prompt tokens served from cache (DeepSeek).
        input_cache_miss_tokens: Prompt tokens billed at the miss rate (DeepSeek).
        estimated_cost_usd: Estimated cost in USD for the LLM call
            (see estimate_llm_cost()).
        pricing_rate: Billing bucket used, e.g. "peak"/"off-peak" (DeepSeek)
            or "flat" (other providers).
        reasoning_mode: DeepSeek reasoning effort used for the LLM call
            ("low"/"high"/"max"), if applicable.
        json_path: Optional custom output file
            (defaults to app/backend/rag_summary.json).
    """
    if action_type not in VALID_ACTION_TYPES:
        raise ValueError(
            f"Invalid action_type '{action_type}'. "
            f"Must be one of {sorted(VALID_ACTION_TYPES)}"
        )

    record = {
        "timestamp_edt": _timestamp_edt(),
        "action_type": action_type,
        "duration_seconds": _round_seconds(duration_seconds),
        "file_name": file_name or "",
        "query_text": query_text or "",
        "steps_taken": steps_taken or [],
        "tools_called": tools_called or [],
        "api_calls_made": api_calls_made or [],
        "final_response": final_response or "",
        "response_time_seconds": _round_seconds(response_time_seconds),
        "input_tokens": input_tokens,
        "output_tokens": output_tokens,
        "input_cache_hit_tokens": input_cache_hit_tokens,
        "input_cache_miss_tokens": input_cache_miss_tokens,
        "estimated_cost_usd": estimated_cost_usd,
        "pricing_rate": pricing_rate,
        "reasoning_mode": reasoning_mode,
    }

    path = Path(json_path) if json_path else DEFAULT_JSON_PATH
    path.parent.mkdir(parents=True, exist_ok=True)

    with _WRITE_LOCK:
        with path.open("a", encoding="utf-8") as fh:
            fh.write(json.dumps(record, ensure_ascii=False, default=str) + "\n")

    logger.info(
        "RAG event logged: action_type=%s file=%s duration=%ss",
        action_type,
        file_name,
        record["duration_seconds"],
    )


@contextmanager
def rag_event_context(
    action_type: str,
    *,
    file_name: Optional[str] = None,
    query_text: Optional[str] = None,
    json_path: Optional[Union[str, Path]] = None,
) -> Iterator[Dict[str, Any]]:
    """Wrap a RAG pipeline action and log it automatically on exit.

    `duration_seconds` is captured via `time.perf_counter()` around the whole
    block. The yielded dict is a mutable event record — populate
    `steps_taken` (preferably via step_timer() so each step is timed),
    `tools_called`, `api_calls_made`, `final_response`, and
    `response_time_seconds` while inside the block. The event is logged even
    if the wrapped code raises an exception.
    """
    start = time.perf_counter()
    event: Dict[str, Any] = {
        "action_type": action_type,
        "file_name": file_name,
        "query_text": query_text,
        "steps_taken": [],
        "tools_called": [],
        "api_calls_made": [],
        "final_response": "",
        "response_time_seconds": None,
        "input_tokens": None,
        "output_tokens": None,
        "input_cache_hit_tokens": None,
        "input_cache_miss_tokens": None,
        "estimated_cost_usd": None,
        "pricing_rate": None,
        "reasoning_mode": None,
    }
    try:
        yield event
    finally:
        event["duration_seconds"] = time.perf_counter() - start
        log_rag_event(**event, json_path=json_path)


@contextmanager
def step_timer(
    event: Dict[str, Any],
    step_name: str,
) -> Iterator[Dict[str, Any]]:
    """Time one pipeline step and append the result to `event["steps_taken"]`.

    On exit, appends a dict like `{"step": "vector retrieval", "seconds": 0.0123}`
    to the event's `steps_taken` list. The yielded dict is the same record that
    gets appended, so callers can read the measured time back out of it (for
    example to also populate `response_time_seconds`).

    Usage:
        with step_timer(event, "embed query"):
            query_embedding = embedding_service.embed_text(query)
    """
    record: Dict[str, Any] = {"step": step_name, "seconds": None}
    start = time.perf_counter()
    try:
        yield record
    finally:
        record["seconds"] = round(time.perf_counter() - start, 6)
        event.setdefault("steps_taken", []).append(record)


if __name__ == "__main__":
    # Self-test: simulates a query event and a file event without touching
    # any real API. Writes to a temp file so the real summary stays clean.
    import tempfile

    demo_json = Path(tempfile.gettempdir()) / "rag_summary_demo.json"
    print(f"Demo output -> {demo_json}")

    with rag_event_context(
        "query",
        query_text="Who is Joshua 'Old Jock' Perkins and where was he born?",
        json_path=demo_json,
    ) as event:
        with step_timer(event, "embed query"):
            time.sleep(0.02)  # stand-in for the embedding API call
        event["api_calls_made"].append("ollama-embed (nomic-embed-text)")

        with step_timer(event, "keyword extraction"):
            pass

        with step_timer(event, "vector retrieval"):
            time.sleep(0.03)  # stand-in for vector search
        event["tools_called"].extend(
            [
                "RetrievalService.search_similar_chunks",
                "RetrievalService.search_ancestry_data",
            ]
        )

        with step_timer(event, "context assembly"):
            pass

        with step_timer(event, "llm answer generation") as llm_step:
            time.sleep(0.05)  # stand-in for the LLM call
        event["response_time_seconds"] = llm_step["seconds"]
        event["api_calls_made"].append("deepseek-v4-pro (chat completion)")
        event["final_response"] = (
            "Joshua 'Old Jock' Perkins was born in 1732 in Accomack County, Virginia."
        )

    log_rag_event(
        "file_upload",
        file_name="2022_Journal_SOFAFEA.docx",
        final_response="Processed and chunked 42 chunks",
        json_path=demo_json,
    )

    print(demo_json.read_text(encoding="utf-8"))
