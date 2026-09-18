#!/usr/bin/env python3
"""
RAG evaluation pipeline for the SOFAFEA eval set (sofafea_rag_eval.md).

For every question in the eval set this script runs the REAL production
pipeline (same services and parameters as POST /api/queries/ask):

    embed query -> keyword extraction -> pgvector retrieval (8 chunks +
    5 ancestry records) -> LLM answer generation

It then measures, per question:

  * The operational metrics rag_summary.json already captures
    (duration, per-step timings, token usage with cache hit/miss split,
    estimated USD cost, reasoning mode).
  * Retrieval quality:
      - context_precision       rank-aware precision (RAGAS-style), judged
                                by the LLM against the gold answer.
      - retrieval_precision@k   plain fraction of relevant chunks.
      - context_recall          fraction of gold-answer sentences supported
                                by the retrieved context (LLM-judged).
      - context_entity_recall   fraction of key entities (years + proper
                                noun phrases) from the gold answer found in
                                the retrieved context. Deterministic, no LLM.
  * Generation quality:
      - faithfulness            fraction of atomic claims in the generated
                                answer supported by the retrieved context
                                (LLM-judged).
      - answer_relevancy        mean cosine similarity between the query
                                embedding and embeddings of questions the
                                LLM derives from the generated answer
                                (falls back to direct answer<->query cosine).
  * Output / citation comparison against the eval set:
      - answer_rubric_score     0/1/2 LLM-judged against the gold answer.
      - answer_semantic_similarity  pooled-embedding cosine (answer vs gold).
      - expected_source_match_ratio  token overlap between the eval set's
                                "Source:" description and the retrieved
                                chunk text/title.
      - answer_citation_validity    fraction of [footnote N] references in
                                the generated answer that actually exist in
                                the retrieved context footnotes.

Results are appended as JSON Lines to app/backend/rag_evaluation_results.json
(one object per question, plus one final "summary" record per run) so repeated
runs are comparable and nothing is ever overwritten.

Usage (from the repo root, venv activated, Ollama + database reachable):

    # Full evaluation with LLM-as-judge metrics
    python rag_evaluation.py

    # Only deterministic/embedding metrics (no judge LLM calls)
    python rag_evaluation.py --skip-judge

    # A subset of questions
    python rag_evaluation.py --questions Q1,Q12,Q18 --limit 3

    # Restrict retrieval to a specific uploaded document
    python rag_evaluation.py --document-title "SOFAFEA"
"""

import argparse
import json
import math
import re
import sys
import time
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

ROOT = Path(__file__).resolve().parent
sys_path = str(ROOT / "app" / "backend")
if sys_path not in sys.path:
    sys.path.insert(0, sys_path)

from config import settings  # noqa: E402
from database import SessionLocal  # noqa: E402
from embedding_service import embedding_service  # noqa: E402
from retrieval_service import RetrievalService  # noqa: E402
from llm_service import llm_service  # noqa: E402
from rag_logging import (  # noqa: E402
    deepseek_pricing_rate,
    estimate_llm_cost,
    log_rag_event,
)
from routes.queries import extract_keywords  # noqa: E402

# --------------------------------------------------------------------------
# Configuration
# --------------------------------------------------------------------------

DEFAULT_EVAL_FILE = ROOT / "sofafea_rag_eval.md"
DEFAULT_OUTPUT = ROOT / "app" / "backend" / "rag_evaluation_results.json"

TOP_K_CHUNKS = 8           # same as /api/queries/ask
TOP_K_ANCESTRY = 5         # same as /api/queries/ask
RELEVANCE_THRESHOLD = 0.35  # same as routes/queries.py
JUDGE_CHUNK_CHARS = 1500    # chunk text sent to the judge (chunks are
                            # CHUNK_SIZE=1000 chars, so this keeps them whole)
JUDGE_CONTEXT_CHARS = 400  # ancestry record text sent to the judge
MAX_GOLD_SENTENCES = 15    # cap on gold-answer sentences for context_recall
EMBED_PIECE_CHARS = 800    # piece size for pooled long-text embeddings

FIELD_MARKER_RE = re.compile(
    r"\*\*(Answer(?:[^*]*)?|Expected behavior|Source|Watch for):\*\*\s*"
)
QUESTION_RE = re.compile(r"\*\*Q(\d+)\.\*\*\s*")
CATEGORY_RE = re.compile(r"^##\s*Category\s*(\d+):\s*(.+)$", re.MULTILINE)

# Words ignored when cleaning entity phrases / matching source descriptions.
ENTITY_LEADING_STOP = {
    "the", "this", "that", "these", "those", "his", "her", "their", "its",
    "he", "she", "it", "they", "we", "our", "your", "my", "a", "an", "which",
    "what", "when", "where", "why", "how", "who", "whom", "both", "also",
    "but", "and", "or", "for", "from", "with", "on", "in", "at", "to", "by",
    "as", "is", "are", "was", "were", "if", "not", "no", "yes", "one", "two",
    "three", "each", "all", "any", "some", "after", "before", "during",
    "according", "note", "answer", "source", "watch", "chart", "table",
    "section", "question", "captain", "capt", "mr", "mrs", "ms", "dr",
    "against", "between", "about", "other",
}
ENTITY_CONNECTOR = {"of", "the", "and", "de", "van", "von", "la", "le",
                    "in", "at", "for"}
SOURCE_STOPWORDS = {
    "the", "and", "for", "with", "was", "were", "his", "her", "this", "that",
    "from", "into", "when", "what", "which", "where", "who", "they", "their",
    "them", "also", "both", "not", "does", "did", "have", "has", "but", "are",
    "article", "section", "sections", "entry", "entries", "generation",
    "generations", "chart", "table", "life", "after", "war", "first",
    "second", "third", "extensive", "two", "three", "one", "all", "some",
    "more", "than", "other", "only", "same", "note", "appears", "twice",
}

# --------------------------------------------------------------------------
# Eval-set parsing
# --------------------------------------------------------------------------


def _clean(text: str) -> str:
    """Normalize a field value: strip each line, keep line structure."""
    if not text:
        return ""
    lines = [ln.strip() for ln in text.replace("\r\n", "\n").split("\n")]
    # Drop markdown horizontal rules and stray separators.
    lines = [ln for ln in lines if ln and not re.fullmatch(r"-{3,}", ln)]
    return "\n".join(lines).strip()


def parse_eval_markdown(path: Path) -> List[Dict[str, Any]]:
    """Extract Q1..QN cases (question, answer, source, watch-for) from the
    eval markdown file."""
    text = path.read_text(encoding="utf-8")

    categories: List[Tuple[int, int, Optional[str]]] = []
    for m in CATEGORY_RE.finditer(text):
        categories.append((m.start(), len(text), m.group(2).strip()))

    def category_at(pos: int) -> Optional[str]:
        label = None
        for start, _, name in categories:
            if start <= pos:
                label = name
        return label

    qmatches = list(QUESTION_RE.finditer(text))
    cases: List[Dict[str, Any]] = []
    for i, m in enumerate(qmatches):
        qnum = m.group(1)
        seg_start = m.end()
        seg_end = qmatches[i + 1].start() if i + 1 < len(qmatches) else len(text)
        rubric_at = text.find("## Scoring Rubric", seg_start)
        if rubric_at != -1 and rubric_at < seg_end:
            seg_end = rubric_at

        segment = text[seg_start:seg_end]
        markers = list(FIELD_MARKER_RE.finditer(segment))
        question_text = (
            segment[: markers[0].start()] if markers else segment
        )
        fields: Dict[str, str] = {}
        for j, fm in enumerate(markers):
            value_start = fm.end()
            value_end = (
                markers[j + 1].start() if j + 1 < len(markers) else len(segment)
            )
            key = fm.group(1)
            # Normalize "Answer (from Chart 1)" -> "Answer".
            if key.startswith("Answer"):
                key = "Answer"
            fields.setdefault(key, _clean(segment[value_start:value_end]))

        answer = fields.get("Answer") or fields.get("Expected behavior") or ""
        cases.append(
            {
                "id": f"Q{qnum}",
                "question": _clean(question_text),
                "expected_answer": answer,
                "expected_source": fields.get("Source", ""),
                "watch_for": fields.get("Watch for", ""),
                "category": category_at(m.start()),
                "unanswerable": "Answer" not in fields,
            }
        )
    return cases


# --------------------------------------------------------------------------
# LLM-as-judge helpers
# --------------------------------------------------------------------------

JUDGE_SYSTEM = (
    "You are an impartial, strict RAG evaluation judge. Your input arrives "
    "below 'Question:' as a labeled payload. The 'Context:' section is empty "
    "and must be ignored. Respond with STRICT JSON only — no markdown fences, "
    "no commentary, no extra text before or after the JSON."
)

JUDGE_RELEVANCE = JUDGE_SYSTEM + (
    " Task: given QUESTION, GOLD ANSWER, and RETRIEVED CHUNKS listed in "
    "retrieval order, decide for each chunk whether it contains information "
    "RELEVANT to verifying or answering the question given the gold answer "
    "(1 = relevant, 0 = not relevant). Output exactly one value per chunk: "
    '{"relevance": [1, 0, 1, ...]}.'
)

JUDGE_RECALL = JUDGE_SYSTEM + (
    " Task: given QUESTION, RETRIEVED CONTEXT, and numbered GOLD ANSWER "
    "SENTENCES, decide for each sentence whether the retrieved context "
    "contains the information the sentence states (close paraphrase is "
    "acceptable). Output exactly one boolean per sentence: "
    '{"sentences_found": [true, false, ...]}.'
)

JUDGE_FAITHFULNESS = JUDGE_SYSTEM + (
    " Task: given QUESTION, RETRIEVED CONTEXT, and ANSWER, break the ANSWER "
    "into atomic factual claims. For each claim set supported=true only if "
    "the retrieved context contains that claim or a close paraphrase with "
    "the same factual content. Output: "
    '{"claims": [{"claim": "...", "supported": true}, ...]}. '
    'If the answer makes no factual claims, output {"claims": []}.'
)

JUDGE_RUBRIC = JUDGE_SYSTEM + (
    " Task: given QUESTION, GOLD ANSWER, and ANSWER, score the ANSWER with "
    "this rubric: 2 = complete and accurate, ambiguity/uncertainty correctly "
    "surfaced where applicable; 1 = partially correct, key details missing "
    "or minor factual error; 0 = incorrect, hallucinated, or refuses to "
    "answer an answerable question. Output: "
    '{"score": <0 or 1 or 2>, "reason": "<one sentence>"}.'
)

JUDGE_QUESTIONS = JUDGE_SYSTEM + (
    " Task: given QUESTION and ANSWER, generate up to 3 questions that the "
    "ANSWER directly addresses (questions a user might have asked to receive "
    "this answer). Output: {'questions': [\"...\", \"...\"]}."
)

# Per-question accumulator for judge LLM usage.
_JUDGE_ACC: Dict[str, int] = {}


def _reset_judge_usage() -> None:
    _JUDGE_ACC.clear()
    _JUDGE_ACC.update(
        calls=0, prompt_tokens=0, completion_tokens=0,
        cache_hit=0, cache_miss=0,
    )


def _add_judge_usage(usage: Optional[Dict[str, Any]]) -> None:
    _JUDGE_ACC["calls"] += 1
    if not usage:
        return
    _JUDGE_ACC["prompt_tokens"] += int(usage.get("prompt_tokens") or 0)
    _JUDGE_ACC["completion_tokens"] += int(usage.get("completion_tokens") or 0)
    _JUDGE_ACC["cache_hit"] += int(usage.get("prompt_cache_hit_tokens") or 0)
    _JUDGE_ACC["cache_miss"] += int(usage.get("prompt_cache_miss_tokens") or 0)


def _parse_json(content: str) -> Any:
    """Defensively extract the first JSON object/array from an LLM reply."""
    if not content:
        return None
    text = re.sub(r"^```(?:json)?\s*|\s*```$", "", content.strip(), flags=re.M)
    for opener, closer in (("{", "}"), ("[", "]")):
        start = text.find(opener)
        if start == -1:
            continue
        end = text.rfind(closer)
        for candidate in (text[start:], text[start:end + 1] if end != -1 else ""):
            candidate = candidate.strip()
            if not candidate:
                continue
            try:
                return json.loads(candidate)
            except json.JSONDecodeError:
                continue
    return None


def _judge(system_prompt: str, payload: str, attempts: int = 2) -> Any:
    """One LLM-as-judge call; returns the parsed JSON or None."""
    for attempt in range(1, attempts + 1):
        p = payload if attempt == 1 else (
            payload + "\n\n(Respond with valid JSON only — nothing else.)"
        )
        content, usage = llm_service.generate_response_with_usage(
            p, [], system_prompt
        )
        _add_judge_usage(usage)
        parsed = _parse_json(content)
        if parsed is not None:
            return parsed
    return None


# --------------------------------------------------------------------------
# Deterministic metric helpers
# --------------------------------------------------------------------------


def _cosine(a: List[float], b: List[float]) -> float:
    if len(a) != len(b) or not a:
        return 0.0
    dot = sum(x * y for x, y in zip(a, b))
    na = math.sqrt(sum(x * x for x in a))
    nb = math.sqrt(sum(y * y for y in b))
    if not na or not nb:
        return 0.0
    return dot / (na * nb)


def _pooled_embedding(text: str) -> Optional[List[float]]:
    """Mean-pooled embedding over char pieces (handles long texts)."""
    text = text.strip()
    if not text:
        return None
    pieces = [
        text[i:i + EMBED_PIECE_CHARS]
        for i in range(0, len(text), EMBED_PIECE_CHARS)
    ]
    pieces = [p for p in pieces if p.strip()]
    vecs = embedding_service.embed_texts(
        pieces, batch_size=min(settings.embed_batch_size, len(pieces))
    )
    if not vecs:
        return None
    dim = len(vecs[0])
    mean = [0.0] * dim
    for v in vecs:
        for i, x in enumerate(v):
            mean[i] += x
    return [x / len(vecs) for x in mean]


def text_similarity(a: str, b: str) -> Optional[float]:
    """Pooled-embedding cosine similarity between two texts, clamped 0..1."""
    va, vb = _pooled_embedding(a), _pooled_embedding(b)
    if va is None or vb is None:
        return None
    return round(max(0.0, min(1.0, _cosine(va, vb))), 4)


def split_sentences(text: str, cap: int = MAX_GOLD_SENTENCES) -> Tuple[List[str], bool]:
    """Split a gold answer into sentences, stripping list numbering."""
    sentences: List[str] = []
    for raw in text.splitlines():
        line = re.sub(r"^\s*(?:\d+[.)]\s*|[-*\u2022]\s*)+", "", raw).strip()
        if not line:
            continue
        sentences.extend(s.strip() for s in re.split(r"(?<=[.;:])\s+", line))
    sentences = [s for s in sentences if s]
    truncated = len(sentences) > cap
    return sentences[:cap], truncated


_PHRASE_RE = re.compile(
    r"\b[A-Z][a-z]{2,}(?:\.|,)?"
    r"(?:\s+(?:[A-Z][a-z]{2,}(?:\.|,)?|[IVX]{1,4}\b|2nd|1st|3rd|"
    r"of|the|and|de|van|von|la|le|in|at)){1,6}\b"
)


def extract_key_entities(text: str) -> List[str]:
    """Deterministic key entities: 4-digit years + multi-word proper noun
    phrases (lightweight proxy; no NER model)."""
    years = set(re.findall(r"\b(1[4-9]\d{2})\b", text))
    phrases: set[str] = set()
    for m in _PHRASE_RE.finditer(text):
        words = [w for w in re.findall(r"[A-Za-z0-9]+", m.group(0))]
        while words and words[0].lower() in ENTITY_LEADING_STOP:
            words.pop(0)
        while words and words[-1].lower() in ENTITY_CONNECTOR:
            words.pop()
        if len(words) >= 2 and not all(
            w.lower() in ENTITY_LEADING_STOP for w in words
        ):
            phrases.add(" ".join(words))
    entities = sorted(years) + sorted(phrases, key=str.lower)
    # De-duplicate case-insensitively.
    seen, out = set(), []
    for e in entities:
        if e.lower() not in seen:
            seen.add(e.lower())
            out.append(e)
    return out


def entity_recall(
    entities: List[str], context_blob: str
) -> Tuple[Optional[float], List[str], List[str]]:
    """Fraction of expected entities found in the retrieved context."""
    if not entities:
        return None, [], []
    blob = context_blob.lower()
    matched, missing = [], []
    for e in entities:
        el = e.lower()
        if el.isdigit():
            found = re.search(rf"\b{re.escape(el)}\b", blob) is not None
        else:
            found = el in blob
            if not found:
                caps = [
                    w for w in re.findall(r"[A-Za-z0-9]+", e)
                    if w[:1].isupper()
                ]
                found = len(caps) >= 2 and all(
                    re.search(rf"\b{re.escape(w.lower())}\b", blob)
                    for w in caps
                )
        (matched if found else missing).append(e)
    recall = round(len(matched) / len(entities), 4)
    return recall, matched, missing


def source_match(expected_source: str, chunks: List[Dict]) -> Tuple[float, List[str]]:
    """Token-overlap between the eval set's source description and retrieved
    chunk text/titles. Returns (best_ratio, matching_titles)."""
    tokens = {
        t for t in re.findall(r"[a-z]{3,}", expected_source.lower())
        if t not in SOURCE_STOPWORDS
    }
    if not tokens:
        return 0.0, []
    best, titles = 0.0, []
    for c in chunks:
        blob = (
            f"{c.get('document_title', '')} {c.get('text', '')}".lower()
        )
        ratio = sum(1 for t in tokens if t in blob) / len(tokens)
        best = max(best, ratio)
        if ratio >= 0.5:
            titles.append(c.get("document_title") or "?")
    return round(best, 4), sorted(set(titles))


def footnote_validity(answer: str, context: List[Dict]) -> Tuple[List[int], List[int]]:
    """Check [footnote N] references in the answer against the footnotes
    attached to the retrieved chunks."""
    cited = [
        int(n) for n in re.findall(r"\[footnote\s*(\d+)\]", answer, re.IGNORECASE)
    ]
    present: set[int] = set()
    for item in context:
        for fn in item.get("footnotes") or []:
            try:
                present.add(int(fn.get("number")))
            except (TypeError, ValueError):
                continue
    valid = [n for n in cited if n in present]
    return cited, valid


def format_chunks_for_judge(chunks: List[Dict], max_chars: int) -> str:
    parts = []
    for i, c in enumerate(chunks, 1):
        text = (c.get("text") or "").strip()
        if len(text) > max_chars:
            text = text[:max_chars] + " ..."
        parts.append(f"[{i}] {c.get('document_title', '?')} | {text}")
    return "\n".join(parts)


def format_context_for_judge(context: List[Dict]) -> str:
    chunks = [
        c for c in context if isinstance(c, dict) and "text" in c
    ]
    parts = [format_chunks_for_judge(chunks, JUDGE_CHUNK_CHARS)]
    ancestry = [
        c for c in context if isinstance(c, dict) and "person_name" in c
    ]
    for i, a in enumerate(ancestry, 1):
        raw = (a.get("raw_text") or "").strip()
        if len(raw) > JUDGE_CONTEXT_CHARS:
            raw = raw[:JUDGE_CONTEXT_CHARS] + " ..."
        parts.append(
            f"[A{i}] {a.get('person_name')} | birth={a.get('birth_date')} "
            f"death={a.get('death_date')} | {raw}"
        )
    return "\n".join(parts)


# --------------------------------------------------------------------------
# Per-question runner
# --------------------------------------------------------------------------


def run_single(
    case: Dict[str, Any],
    db: Any,
    *,
    use_judge: bool,
    title_filter: Optional[str],
    run_id: str,
    log_to_rag_summary: bool,
    tag: str = "",
) -> Dict[str, Any]:
    rec: Dict[str, Any] = {
        "record_type": "question",
        "run_id": run_id,
        "variant": tag or "untagged",
        "question_id": case["id"],
        "category": case["category"],
        "question": case["question"],
        "expected_answer": case["expected_answer"],
        "expected_source": case["expected_source"],
        "watch_for": case["watch_for"],
        "expected_unanswerable": case["unanswerable"],
    }
    _reset_judge_usage()
    q = case["question"]
    steps: List[Dict[str, Any]] = []
    start = time.perf_counter()

    # --- 1. Embed the query -------------------------------------------------
    t0 = time.perf_counter()
    q_embedding = embedding_service.embed_text(q)
    steps.append(
        {"step": "embed query", "seconds": round(time.perf_counter() - t0, 4)}
    )

    # --- 2. Keyword extraction ---------------------------------------------
    t0 = time.perf_counter()
    keyword = extract_keywords(q)
    steps.append(
        {"step": "keyword extraction", "seconds": round(time.perf_counter() - t0, 4)}
    )

    # --- 3. Vector retrieval ------------------------------------------------
    t0 = time.perf_counter()
    if title_filter:
        candidates = RetrievalService.search_similar_chunks(
            db, q_embedding, top_k=TOP_K_CHUNKS * 3, keyword=keyword
        )
        chunks = [
            c for c in candidates
            if title_filter.lower() in (c.get("document_title") or "").lower()
        ][:TOP_K_CHUNKS]
    else:
        chunks = RetrievalService.search_similar_chunks(
            db, q_embedding, top_k=TOP_K_CHUNKS, keyword=keyword
        )
    ancestry = RetrievalService.search_ancestry_data(
        db, q_embedding, top_k=TOP_K_ANCESTRY
    )
    steps.append(
        {"step": "vector retrieval", "seconds": round(time.perf_counter() - t0, 4)}
    )
    context = list(chunks) + list(ancestry)

    # --- 4. LLM answer generation ------------------------------------------
    t0 = time.perf_counter()
    answer, usage = llm_service.generate_response_with_usage(q, context)
    gen_seconds = time.perf_counter() - t0
    steps.append(
        {"step": "llm answer generation", "seconds": round(gen_seconds, 4)}
    )

    duration = round(time.perf_counter() - start, 4)
    best_score = max(
        (float(c.get("similarity_score") or 0) for c in chunks), default=0.0
    )

    # --- Operational metrics (rag_summary.json parity) ----------------------
    rec.update(
        {
            "generated_answer": answer or "",
            "duration_seconds": duration,
            "steps_taken": steps,
            "response_time_seconds": round(gen_seconds, 4),
            "input_tokens": (usage or {}).get("prompt_tokens"),
            "output_tokens": (usage or {}).get("completion_tokens"),
            "input_cache_hit_tokens": (usage or {}).get("prompt_cache_hit_tokens"),
            "input_cache_miss_tokens": (usage or {}).get("prompt_cache_miss_tokens"),
            "estimated_cost_usd": estimate_llm_cost(
                provider=settings.llm_provider,
                model=llm_service.get_active_model_name(),
                input_tokens=(usage or {}).get("prompt_tokens"),
                output_tokens=(usage or {}).get("completion_tokens"),
                input_cache_hit_tokens=(usage or {}).get("prompt_cache_hit_tokens"),
                input_cache_miss_tokens=(usage or {}).get("prompt_cache_miss_tokens"),
            ),
            "pricing_rate": (
                deepseek_pricing_rate()
                if settings.llm_provider == "deepseek"
                else "flat"
            ),
            "reasoning_mode": getattr(llm_service, "last_reasoning_mode", None),
            "best_similarity_score": round(best_score, 4),
            "sources_shown": best_score >= RELEVANCE_THRESHOLD,
            "keyword_used": keyword,
            "retrieved_chunks": [
                {
                    "chunk_id": c.get("chunk_id"),
                    "chunk_number": c.get("chunk_number"),
                    "document_title": c.get("document_title"),
                    "similarity_score": round(float(c.get("similarity_score") or 0), 4),
                }
                for c in chunks
            ],
            "retrieved_ancestry_count": len(ancestry),
            # Full chunk texts, so the RAGAS evaluator can score the same
            # retrieved contexts the generator saw.
            "retrieved_contexts": [c.get("text") or "" for c in chunks],
        }
    )

    # --- Deterministic / embedding metrics ----------------------------------
    context_blob = " ".join(
        [c.get("text") or "" for c in chunks]
        + [a.get("raw_text") or "" for a in ancestry]
    )
    entities = extract_key_entities(case["expected_answer"])
    er, _matched, missing = entity_recall(entities, context_blob)
    rec["context_entity_recall"] = er
    rec["entities_expected"] = entities
    rec["entities_missing"] = missing

    src_ratio, src_titles = source_match(case["expected_source"], chunks)
    rec["expected_source_match_ratio"] = src_ratio
    rec["matched_document_titles"] = src_titles

    cited, valid = footnote_validity(answer or "", context)
    rec["answer_footnote_citations"] = cited
    rec["answer_footnotes_in_context"] = valid
    rec["answer_citation_validity"] = (
        round(len(valid) / len(cited), 4) if cited else None
    )

    rec["answer_semantic_similarity"] = text_similarity(
        answer or "", case["expected_answer"]
    )

    # --- LLM-as-judge metrics ----------------------------------------------
    if use_judge:
        # Context precision (rank-aware, RAGAS-style).
        rel = _judge(
            JUDGE_RELEVANCE,
            "QUESTION:\n{q}\n\nGOLD ANSWER:\n{gold}\n\n"
            "RETRIEVED CHUNKS (in retrieval order):\n{chunks}".format(
                q=q,
                gold=case["expected_answer"][:2000],
                chunks=format_chunks_for_judge(chunks, JUDGE_CHUNK_CHARS),
            ),
        )
        relevance: Optional[List[int]] = None
        if isinstance(rel, dict) and isinstance(rel.get("relevance"), list):
            relevance = [
                1 if v in (1, True, "1", "true", "True") else 0
                for v in rel["relevance"][: len(chunks)]
            ]
            relevance += [0] * (len(chunks) - len(relevance))
        if relevance is not None:
            relevant_hits = 0
            ranked_sum = 0.0
            for rank, r in enumerate(relevance, start=1):
                if r:
                    relevant_hits += 1
                    ranked_sum += relevant_hits / rank
            rec["context_precision"] = (
                round(ranked_sum / relevant_hits, 4) if relevant_hits else 0.0
            )
            rec["retrieval_precision_at_k"] = round(
                relevant_hits / len(relevance), 4
            )
            for chunk_summary, r in zip(rec["retrieved_chunks"], relevance):
                chunk_summary["relevant"] = r
        else:
            rec["context_precision"] = None
            rec["retrieval_precision_at_k"] = None

        # Context recall (gold-answer sentences vs retrieved context).
        gold_sents, truncated = split_sentences(case["expected_answer"])
        rec["gold_answer_sentences"] = gold_sents
        rec["gold_sentences_truncated"] = truncated
        if gold_sents:
            sent_payload = "QUESTION:\n{q}\n\nRETRIEVED CONTEXT:\n{ctx}\n\n" \
                "GOLD ANSWER SENTENCES:\n{sents}".format(
                    q=q,
                    ctx=format_context_for_judge(context),
                    sents="\n".join(
                        f"[{i}] {s}" for i, s in enumerate(gold_sents, 1)
                    ),
                )
            found = _judge(JUDGE_RECALL, sent_payload)
            found_list: Optional[List[bool]] = None
            if isinstance(found, dict) and isinstance(
                found.get("sentences_found"), list
            ):
                found_list = [
                    bool(v) for v in found["sentences_found"][: len(gold_sents)]
                ]
            if found_list is not None:
                rec["context_recall"] = round(
                    sum(found_list) / len(gold_sents), 4
                )
                rec["gold_sentences_found"] = found_list
            else:
                rec["context_recall"] = None
        else:
            rec["context_recall"] = None

        # Faithfulness (claims in the answer vs retrieved context).
        f = _judge(
            JUDGE_FAITHFULNESS,
            "QUESTION:\n{q}\n\nRETRIEVED CONTEXT:\n{ctx}\n\nANSWER:\n{ans}".format(
                q=q,
                ctx=format_context_for_judge(context),
                ans=(answer or "")[:2000],
            ),
        )
        claims = f.get("claims") if isinstance(f, dict) else None
        if isinstance(claims, list):
            supported = [
                c for c in claims
                if isinstance(c, dict)
                and c.get("supported") in (True, 1, "true", "True")
            ]
            rec["faithfulness"] = (
                round(len(supported) / len(claims), 4) if claims else None
            )
            rec["claims_total"] = len(claims)
            rec["claims_supported"] = len(supported)
        else:
            rec["faithfulness"] = None

        # Rubric score vs gold answer.
        r = _judge(
            JUDGE_RUBRIC,
            "QUESTION:\n{q}\n\nGOLD ANSWER:\n{gold}\n\nANSWER:\n{ans}".format(
                q=q,
                gold=case["expected_answer"][:1500],
                ans=(answer or "")[:1500],
            ),
        )
        if isinstance(r, dict) and r.get("score") in (0, 1, 2, "0", "1", "2"):
            rec["answer_rubric_score"] = int(r["score"])
            rec["rubric_reason"] = r.get("reason")
        else:
            rec["answer_rubric_score"] = None

        # Answer relevancy (LLM-derived questions vs query embedding).
        qj = _judge(
            JUDGE_QUESTIONS,
            "QUESTION:\n{q}\n\nANSWER:\n{ans}".format(
                q=q, ans=(answer or "")[:1500]
            ),
        )
        gen_qs = qj.get("questions") if isinstance(qj, dict) else None
        if isinstance(gen_qs, list) and gen_qs:
            gen_qs = [str(s) for s in gen_qs[:3]]
            rec["generated_questions"] = gen_qs
            vecs = embedding_service.embed_texts(
                gen_qs, batch_size=min(settings.embed_batch_size, len(gen_qs))
            )
            if vecs:
                sims = [_cosine(q_embedding, v) for v in vecs]
                rec["answer_relevancy"] = round(
                    max(0.0, sum(sims) / len(sims)), 4
                )
                rec["answer_relevancy_method"] = "llm-generated questions"
            else:
                rec["answer_relevancy"] = None
        else:
            # Fallback: direct cosine between query and answer embeddings.
            ans_vec = _pooled_embedding(answer or "")
            rec["answer_relevancy"] = (
                round(max(0.0, min(1.0, _cosine(q_embedding, ans_vec))), 4)
                if ans_vec is not None
                else None
            )
            rec["answer_relevancy_method"] = "query-answer cosine (fallback)"
    else:
        ans_vec = _pooled_embedding(answer or "")
        rec["answer_relevancy"] = (
            round(max(0.0, min(1.0, _cosine(q_embedding, ans_vec))), 4)
            if ans_vec is not None
            else None
        )
        rec["answer_relevancy_method"] = "query-answer cosine (no judge)"

    # Judge usage / cost for this question.
    rec["judge_llm_calls"] = _JUDGE_ACC["calls"]
    rec["judge_input_tokens"] = _JUDGE_ACC["prompt_tokens"]
    rec["judge_output_tokens"] = _JUDGE_ACC["completion_tokens"]
    rec["judge_cost_usd"] = estimate_llm_cost(
        provider=settings.llm_provider,
        model=llm_service.get_active_model_name(),
        input_tokens=_JUDGE_ACC["prompt_tokens"],
        output_tokens=_JUDGE_ACC["completion_tokens"],
        input_cache_hit_tokens=_JUDGE_ACC["cache_hit"],
        input_cache_miss_tokens=_JUDGE_ACC["cache_miss"],
    )

    # Optionally append the standard production event to rag_summary.json.
    if log_to_rag_summary:
        log_rag_event(
            "query",
            query_text=q,
            duration_seconds=duration,
            steps_taken=steps,
            tools_called=[
                "rag_evaluation.RetrievalService.search_similar_chunks",
                "rag_evaluation.RetrievalService.search_ancestry_data",
            ],
            api_calls_made=[
                f"embedding ({settings.embedding_provider})",
                f"llm ({settings.llm_provider})",
            ],
            final_response=answer or "",
            response_time_seconds=round(gen_seconds, 4),
            input_tokens=(usage or {}).get("prompt_tokens"),
            output_tokens=(usage or {}).get("completion_tokens"),
            input_cache_hit_tokens=(usage or {}).get("prompt_cache_hit_tokens"),
            input_cache_miss_tokens=(usage or {}).get("prompt_cache_miss_tokens"),
            estimated_cost_usd=rec["estimated_cost_usd"],
            pricing_rate=rec["pricing_rate"],
            reasoning_mode=rec["reasoning_mode"],
        )

    return rec


# --------------------------------------------------------------------------
# Output / summary
# --------------------------------------------------------------------------


def append_record(path: Path, record: Dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("a", encoding="utf-8") as fh:
        fh.write(json.dumps(record, ensure_ascii=False, default=str) + "\n")


# --------------------------------------------------------------------------
# RAGAS library evaluator (optional dependency: ragas, langchain-openai,
# langchain-ollama). Provides library-standard implementations of the same
# judge metrics the custom evaluator computes by hand — useful as a
# cross-validation layer. DeepSeek judges via its OpenAI-compatible API and
# local Ollama nomic-embed-text embeddings keep the privacy stance.
# --------------------------------------------------------------------------


def _ragas_available() -> bool:
    try:
        import ragas  # noqa: F401
        return True
    except ImportError:
        return False


def _build_ragas_wrappers():
    """DeepSeek judge LLM + local Ollama embeddings wrapped for RAGAS."""
    from ragas.llms import LangchainLLMWrapper
    from ragas.embeddings import LangchainEmbeddingsWrapper
    from langchain_openai import ChatOpenAI
    from langchain_ollama import OllamaEmbeddings

    llm = LangchainLLMWrapper(
        ChatOpenAI(
            model=settings.deepseek_model,
            api_key=settings.deepseek_api_key,
            base_url=settings.deepseek_base_url,
            temperature=0,
            max_tokens=2000,
        )
    )
    embeddings = LangchainEmbeddingsWrapper(
        OllamaEmbeddings(
            model=settings.ollama_embed_model,
            base_url=settings.ollama_base_url,
        )
    )
    return llm, embeddings


def _evaluate_ragas(
    results: List[Dict[str, Any]],
) -> Dict[str, Dict[str, Any]]:
    """Run RAGAS metrics over the collected question records.

    Returns {question_id: {"ragas_faithfulness": ..., ...}} using the same
    metric names as the custom evaluator (answer_similarity is RAGAS's name
    for answer semantic similarity).
    """
    from ragas import evaluate
    from ragas.dataset_schema import EvaluationDataset, SingleTurnSample
    from ragas.run_config import RunConfig
    import ragas.metrics as ragas_metrics

    llm, embeddings = _build_ragas_wrappers()
    samples: List[Any] = []
    ids: List[str] = []
    for rec in results:
        if rec.get("error") or not (rec.get("generated_answer") or "").strip():
            continue
        contexts = rec.get("retrieved_contexts") or []
        if not contexts:
            continue
        samples.append(
            SingleTurnSample(
                user_input=rec["question"],
                response=rec["generated_answer"],
                retrieved_contexts=contexts,
                reference=rec.get("expected_answer") or "",
            )
        )
        ids.append(rec["question_id"])

    if not samples:
        return {}

    dataset = EvaluationDataset(samples=samples)
    result = evaluate(
        dataset,
        metrics=[
            ragas_metrics.faithfulness,
            ragas_metrics.answer_relevancy,
            ragas_metrics.context_precision,
            ragas_metrics.context_recall,
            ragas_metrics.answer_similarity,
        ],
        llm=llm,
        embeddings=embeddings,
        run_config=RunConfig(timeout=240, max_retries=1),
    )

    df = result.to_pandas()
    column_map = {
        "faithfulness": "ragas_faithfulness",
        "answer_relevancy": "ragas_answer_relevancy",
        "context_precision": "ragas_context_precision",
        "context_recall": "ragas_context_recall",
        "semantic_similarity": "ragas_answer_semantic_similarity",
    }
    out: Dict[str, Dict[str, Any]] = {}
    for i, qid in enumerate(ids):
        metrics: Dict[str, Any] = {}
        for col, key in column_map.items():
            if col not in df.columns:
                metrics[key] = None
                continue
            try:
                value = float(df.iloc[i][col])
                metrics[key] = None if math.isnan(value) else round(value, 4)
            except (TypeError, ValueError):
                metrics[key] = None
        out[qid] = metrics
    return out


def _avg(values: List[float]) -> Optional[float]:
    values = [
        v for v in values
        if v is not None and not (isinstance(v, float) and math.isnan(v))
    ]
    return round(sum(values) / len(values), 4) if values else None


def build_summary(
    results: List[Dict[str, Any]],
    run_id: str,
    elapsed: float,
    tag: str = "",
) -> Dict[str, Any]:
    metric_keys = [
        "context_precision",
        "retrieval_precision_at_k",
        "context_recall",
        "context_entity_recall",
        "faithfulness",
        "answer_relevancy",
        "answer_semantic_similarity",
        "answer_rubric_score",
        "ragas_faithfulness",
        "ragas_answer_relevancy",
        "ragas_context_precision",
        "ragas_context_recall",
        "ragas_answer_semantic_similarity",
    ]
    averages = {k: _avg([r.get(k) for r in results]) for k in metric_keys}
    costs = [
        (r.get("estimated_cost_usd") or 0) + (r.get("judge_cost_usd") or 0)
        for r in results
    ]
    return {
        "record_type": "summary",
        "run_id": run_id,
        "variant": tag or "untagged",
        "timestamp": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
        "questions_run": len(results),
        "elapsed_seconds": round(elapsed, 2),
        "average_metrics": averages,
        "rubric_score_distribution": {
            str(score): sum(
                1 for r in results if r.get("answer_rubric_score") == score
            )
            for score in (0, 1, 2)
        },
        "total_cost_usd": round(sum(costs), 6),
        "total_answer_cost_usd": round(
            sum(r.get("estimated_cost_usd") or 0 for r in results), 6
        ),
        "total_judge_cost_usd": round(
            sum(r.get("judge_cost_usd") or 0 for r in results), 6
        ),
        "llm_provider": settings.llm_provider,
        "llm_model": llm_service.get_active_model_name(),
        "embedding_provider": settings.embedding_provider,
    }


def print_table(results: List[Dict[str, Any]]) -> None:
    header = (
        f"{'Q':>3} | {'Prec':>5} | {'P@k':>5} | {'Rec':>5} | {'EntR':>5} | "
        f"{'Faith':>5} | {'Rel':>5} | {'Sim':>5} | {'Rubr':>4} | {'cost$':>7} | "
        f"{'srcMatch':>8} | {'cit':>4}"
    )
    print("\n" + header)
    print("-" * len(header))
    for r in results:
        if "error" in r and r["error"]:
            print(f"{r['question_id']:>3} | ERROR: {r['error'][:60]}")
            continue
        cit = r.get("answer_citation_validity")
        print(
            f"{r['question_id']:>3} | {_f(r.get('context_precision')):>5} | "
            f"{_f(r.get('retrieval_precision_at_k')):>5} | "
            f"{_f(r.get('context_recall')):>5} | "
            f"{_f(r.get('context_entity_recall')):>5} | "
            f"{_f(r.get('faithfulness')):>5} | "
            f"{_f(r.get('answer_relevancy')):>5} | "
            f"{_f(r.get('answer_semantic_similarity')):>5} | "
            f"{_s(r.get('answer_rubric_score')):>4} | "
            f"{((r.get('estimated_cost_usd') or 0) + (r.get('judge_cost_usd') or 0)):>7.5f} | "
            f"{_f(r.get('expected_source_match_ratio')):>8} | "
            f"{_f(cit):>4}"
        )


def _f(v: Optional[float]) -> str:
    return "  n/a" if v is None else f"{v:5.3f}"


def _s(v: Optional[int]) -> str:
    return " n/a" if v is None else f"  {v}"


# --------------------------------------------------------------------------
# Main
# --------------------------------------------------------------------------


def main() -> None:
    ap = argparse.ArgumentParser(
        description="Run the RAG evaluation pipeline over sofafea_rag_eval.md."
    )
    ap.add_argument("--eval-file", default=str(DEFAULT_EVAL_FILE),
                    help="Path to the eval markdown (default: sofafea_rag_eval.md).")
    ap.add_argument("--output", default=str(DEFAULT_OUTPUT),
                    help="JSON Lines results file (default: app/backend/rag_evaluation_results.json).")
    ap.add_argument("--questions", default="",
                    help="Comma-separated question ids to run, e.g. Q1,Q12,Q18.")
    ap.add_argument("--limit", type=int, default=0,
                    help="Run only the first N questions (0 = all).")
    ap.add_argument("--skip-judge", action="store_true",
                    help="Skip all LLM-as-judge metrics (custom judges AND ragas).")
    ap.add_argument("--evaluator", choices=["custom", "ragas", "both"], default="custom",
                    help="Which judge layer to run: custom (hand-rolled prompts), ragas (library metrics), or both.")
    ap.add_argument("--document-title", default="",
                    help="Only retrieve chunks whose document title contains this substring.")
    ap.add_argument("--log-to-rag-summary", action="store_true",
                    help="Also append each evaluated query as a standard event in rag_summary.json.")
    ap.add_argument("--tag", default="",
                    help="Short variant label stored on every record (e.g. baseline, semantic) for A/B comparisons.")
    args = ap.parse_args()

    eval_path = Path(args.eval_file)
    if not eval_path.exists():
        raise SystemExit(f"Eval file not found: {eval_path}")

    cases = parse_eval_markdown(eval_path)
    if not cases:
        raise SystemExit(f"No questions parsed from {eval_path}")

    if args.questions:
        wanted = {q.strip().upper() for q in args.questions.split(",") if q.strip()}
        cases = [c for c in cases if c["id"] in wanted]
        if not cases:
            raise SystemExit(
                f"No matching questions. Available ids: "
                f"{[c['id'] for c in parse_eval_markdown(eval_path)]}"
            )
    if args.limit:
        cases = cases[: args.limit]

    out_path = Path(args.output)
    run_id = datetime.now().strftime("%Y%m%d-%H%M%S")
    run_start = time.perf_counter()

    use_custom_judge = (args.evaluator in ("custom", "both")) and not args.skip_judge
    use_ragas = (args.evaluator in ("ragas", "both")) and not args.skip_judge
    if use_ragas and not _ragas_available():
        raise SystemExit(
            "--evaluator ragas/both requires the ragas library: "
            "pip install 'ragas==0.2.15' langchain-openai langchain-ollama"
        )

    print(f"Eval file      : {eval_path}")
    print(f"Questions      : {len(cases)} ({', '.join(c['id'] for c in cases)})")
    print(f"Variant tag    : {args.tag or '(untagged)'}")
    print(f"Evaluator      : {args.evaluator} (custom judge={use_custom_judge}, ragas={use_ragas})")
    print(f"LLM judge      : {'off (--skip-judge)' if args.skip_judge else 'on'}")
    print(f"LLM provider   : {settings.llm_provider} ({llm_service.get_active_model_name()})")
    print(f"Embeddings     : {settings.embedding_provider}")
    if args.document_title:
        print(f"Doc filter     : title contains '{args.document_title}'")
    print(f"Results append : {out_path}\n")

    db = SessionLocal()
    results: List[Dict[str, Any]] = []
    try:
        for i, case in enumerate(cases, 1):
            print(
                f"[{i}/{len(cases)}] {case['id']} | "
                f"{case['question'][:70].replace(chr(10), ' ')}",
                flush=True,
            )
            try:
                rec = run_single(
                    case,
                    db,
                    use_judge=use_custom_judge,
                    title_filter=args.document_title or None,
                    run_id=run_id,
                    log_to_rag_summary=args.log_to_rag_summary,
                    tag=args.tag,
                )
                rec["error"] = None
            except Exception as exc:  # keep the run alive on per-question errors
                rec = {
                    "record_type": "question",
                    "run_id": run_id,
                    "variant": args.tag or "untagged",
                    "question_id": case["id"],
                    "question": case["question"],
                    "error": f"{type(exc).__name__}: {exc}",
                }
                print(f"    ERROR: {exc}", flush=True)
            results.append(rec)
            if not use_ragas:
                # RAGAS runs are appended after enrichment below, so every
                # record carries its ragas_* metrics too.
                append_record(out_path, rec)
    finally:
        db.close()

    if use_ragas:
        print("\nRunning RAGAS metrics (DeepSeek judge + Ollama embeddings)...", flush=True)
        try:
            ragas_by_qid = _evaluate_ragas(results)
        except Exception as exc:
            ragas_by_qid = {}
            print(f"    RAGAS evaluation failed: {type(exc).__name__}: {exc}", flush=True)
        for rec in results:
            qid = rec.get("question_id")
            if qid in ragas_by_qid:
                rec.update(ragas_by_qid[qid])
            elif not rec.get("error"):
                rec["ragas_error"] = "skipped or failed"
            append_record(out_path, rec)

    elapsed = time.perf_counter() - run_start
    summary = build_summary(results, run_id, elapsed, tag=args.tag)
    append_record(out_path, summary)

    print_table(results)
    print("\n=== SUMMARY (averages) ===")
    for k, v in summary["average_metrics"].items():
        print(f"  {k:28} {v if v is not None else 'n/a'}")
    print(f"  rubric distribution (0/1/2): {summary['rubric_score_distribution']}")
    print(f"  total answer cost          : ${summary['total_answer_cost_usd']}")
    print(f"  total judge cost           : ${summary['total_judge_cost_usd']}")
    print(f"  elapsed                    : {summary['elapsed_seconds']}s")
    print(f"\nResults appended to {out_path}")


if __name__ == "__main__":
    main()
