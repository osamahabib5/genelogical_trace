# AI Solutions Architect — Second-Round Interview Prep (Sr. AI Solutions Architect)

Second-round questions are deeper, scenario-driven, and whiteboard-heavy. These sample answers go one level below the first-round prep: trade-offs with numbers, failure stories, and customer scenarios — all grounded in the Genealogy RAG platform and the companion admin panel.

**Anchor facts you can cite anywhere:**
- Full RAG stack: FastAPI + React, Supabase PostgreSQL + pgvector (768-dim), DeepSeek LLM with Groq fallback, local Ollama `nomic-embed-text` embeddings.
- Per-query event log (`rag_summary.json`): per-step timings, token usage, cache hit/miss split, USD cost with DeepSeek peak/off-peak pricing, reasoning mode.
- Measured numbers: ~2.2s fixed overhead per Ollama embedding call; upload embedding dropped from ~294s to <60s via batching (`EMBED_BATCH_SIZE`); LLM generation 2–45s depending on reasoning effort (default `low`).
- Admin panel: JWT + RBAC (admin/moderator/viewer), database-trigger audit trail, Azure PostgreSQL logical replication to a backup server, Vercel serverless.
- Agent orchestration (implemented): LangGraph research agent in `agent_orchestration.py`, exposed at `POST /api/queries/research` — classify → retrieve → generate → verify → approve, with token budget, citation verifier, human-in-the-loop resume, and automatic fallback to direct RAG.
- Security guardrails (implemented): retrieved context wrapped in escaped `<retrieved_document>` delimiters; static system prompts with a data-plane assertion; `answer_verifier.py` honesty audit on every `/ask` (`VERIFY_ANSWERS=true`); magic-byte upload validation.
- RAG eval harness (implemented): `rag_evaluation.py` runs the 23-question SOFAFEA eval set through the real pipeline and logs context precision/recall, entity recall, faithfulness, answer relevancy, and rubric scores to `rag_evaluation_results.json`. Two judge layers: hand-rolled LLM judges (default) and the `ragas` library (`--evaluator ragas`) with DeepSeek as judge and local Ollama embeddings.
- Chunking A/B (measured): heading-aware semantic chunking (`SEMANTIC_CHUNKING`) raised context precision 0.68→0.79 but cut context recall 0.48→0.32 and rubric 1.29→1.14 — the harness proved overlap wasn't the problem, so fixed 1000/100 stays the default.
- Hybrid retrieval (implemented + measured): `RetrievalService` fuses vector cosine with Postgres full-text search (`tsvector` + GIN, `websearch_to_tsquery` + `ts_rank`) via Reciprocal Rank Fusion (`RRF_K=60`) behind `HYBRID_SEARCH`. Measured on the 23-question set: fixed the exact-name questions (Q13 rubric 0→2, Q10 1→2) and lifted faithfulness 0.856→0.923, but regressed multi-hop/numeric questions (Q11, Q19, Q22) and average rubric 1.609→1.478 — so the default rolled back to vector-only, and the next moves are weighted RRF and query-type gating.

---

## Core Concepts (30-second definitions)

- **RAG (Retrieval-Augmented Generation)** — a pattern where a retriever first fetches relevant passages from a knowledge base and the generator then answers strictly from those passages, so answers stay grounded and citable instead of relying on the model's parametric memory. *In this project: pgvector cosine search over document chunks + ancestry records feeding DeepSeek, with footnote citations and an answer verifier.*
- **LangChain** — a framework of building blocks for LLM applications: model wrappers, prompt templates, retrievers, and tools, with the classic `AgentExecutor` loop (thought → action → observation). *In this project: the document-intake agent in `agent_service.py` (quality assessment, cleaning, and storage tools).*
- **LangGraph** — a graph-based orchestration library built on LangChain that models agent workflows as explicit nodes and edges (state machines), adding checkpointing, branching, retries, and human-in-the-loop interrupts. *In this project: `agent_orchestration.py` — classify → retrieve → generate → verify → approve, resumable by `thread_id`.*
- **Agentic AI** — AI systems that don't just answer: they reason, plan, choose tools, act, and observe results iteratively toward a goal, wrapped in guardrails and human oversight. *In this project: the LangGraph research agent with a token budget, a verification pass, an honesty verifier on `/ask`, and optional human approval.*

---

## 1. "Walk me through one query, end to end, and defend the latency and cost at every step."

> A query hits `/api/queries/ask`. Step one: embed it with local Ollama — historically 2–4s on CPU, dominated by a fixed ~2.2s per-request overhead, which is why I benchmarked batch sizes and made them configurable. Step two: retrieval — pgvector cosine search over chunks plus person records, ~0.1–0.9s. Step three: the LLM call — anywhere from 2s to 45s depending on the reasoning effort my classifier picks (`low` for factoid questions, `high` for comparisons, `max` for multi-step research). Step four: the honesty verifier — a second LLM pass auditing the draft against the retrieved context, measured at ~2s and ~$0.0027 per query, with the verdict and reason logged. Step five: every step, token count, and dollar cost lands in a JSONL event log.
> The trade-offs I defend: (1) local embeddings — privacy and zero cost, at the price of CPU latency; acceptable because retrieval is the cheap part. (2) reasoning classification — it converts latency/cost from a fixed tax into a per-question decision, so "who is Joshua Perkins" doesn't pay for a 40-second thinking session. (3) honesty over coverage — off-topic queries skip retrieval entirely rather than waste tokens on irrelevant context. (4) verification over trust — the verifier doubles LLM calls per query, but hallucinated answers in a genealogy archive cost far more than ~$0.003, and the `VERIFY_ANSWERS` flag makes it a reversible, budgeted decision.

## 2. "Walk me through one document, end to end — upload to vector store — and defend each step."

> A file lands at `POST /api/documents/upload` and is validated first: extension whitelist plus magic-byte checks (PDF `%PDF-`, DOCX `PK`, UTF-8 for TXT/JSON), empty-file rejection, a size cap, and a UUID-prefixed filename. Then `DocumentProcessor` extracts the text and chunks it — a fixed 1,000-char sliding window with 100-char overlap by default, or heading-aware semantic chunking behind `SEMANTIC_CHUNKING`. Each chunk is embedded by local Ollama `nomic-embed-text` into a 768-dim vector and inserted into pgvector (`document_chunks`) alongside the raw text; a regex/heuristic entity extractor also writes names, dates, and relationships as `AncestryRecord` rows with their own embeddings — that second table powers the `/person` and `/family` lookups, and footnotes land in `document_footnotes`.
> The trade-offs I defend: (1) batching — embeddings ship in configurable batches (`EMBED_BATCH_SIZE`), which cut an upload's embedding phase from ~294s to under 60s, because Ollama's ~2.2s fixed per-call overhead is paid once per batch instead of once per chunk. (2) local embeddings — zero cost and documents never leave the trust boundary, at the price of CPU-bound upload latency. (3) chunking is a stored decision — the window is fixed when a document is ingested, so switching strategies requires re-uploading; that's why I A/B-tested semantic chunking before touching the default. (4) deterministic extraction over a paid LLM pass — entities come from regex/heuristics, keeping ingestion cheap and predictable; and in the 1M-record whiteboard, this same pipeline moves behind an async queue with backpressure so a 10,000-page upload never blocks an HTTP worker.

## 3. "Your retrieval is pure vector search. Where does it fail, and how would you fix it?"

> Three failure classes, and I can show each in my logs: (1) **Exact-name misses** — "J. Perkins" vs "Joshua Perkins"; embeddings are fuzzy, so exact spellings and abbreviations suffer. (2) **Cross-chunk answers** — a fact split across two 1,000-char chunks retrieves one but not the other. (3) **Ambiguous pronouns** — "his mother" retrieves nothing relevant.
> Fixes in order of cost: hybrid retrieval — **implemented and measured, not just proposed** — BM25-style full-text plus vector cosine fused with reciprocal rank fusion (`tsvector` + GIN in the same pgvector Postgres, `websearch_to_tsquery` + `ts_rank`, `RRF_K=60`, behind `HYBRID_SEARCH`); then a cross-encoder re-ranker over top-50 candidates; query rewriting by the LLM before embedding; and entity linking so a detected name forces a metadata-filtered search. The hybrid shipped behind a config flag with a vector-only fallback, and I A/B-tested it on the full 23-question set: it fixed the exact-name questions (Q13 rubric 0→2, Q10 1→2) and lifted faithfulness 0.856→0.923, but regressed relationship/numeric questions (Q22 2→0, Q11 1→0) and average rubric 1.609→1.478 — so the default stays vector-only while I tune weighted RRF and query-type gating. The decision rule is unchanged: keep the change that wins on recall@k without hurting p95 latency, which is exactly what my chunking A/B taught me (semantic chunking raised precision 0.68→0.79 but cut recall 0.48→0.32 and rubric 1.29→1.14, so overlap wasn't the problem and I kept the fixed window).

---

## A/B Debrief: Semantic vs. Fixed-Window Chunking

**What I tested (the semantic strategy)** — implemented in `document_processor.py` behind `SEMANTIC_CHUNKING`:
- Split on heading boundaries: Word `Heading 1/2/3` styles for DOCX, plus a title-case / ALL-CAPS heuristic for PDF/TXT/JSON.
- Consecutive headings nest into breadcrumbs (`Fused Legacies > Life After the War`; `Maine's Tobias Hill > Generation 1`).
- Long sections are split with overlap applied **only inside the section** — never across a heading boundary.
- Every chunk is stored with a `Section: ...` breadcrumb prefix, so retrieved chunks are self-contained.
- On the 2023 journal this produced **233 chunks from 42 detected headings**, vs. **175 chunks** from the baseline.

**The baseline** — fixed 1,000-char sliding window with 100-char overlap (the shipped default).

**Protocol** — same 7 multi-hop/list questions (Q8–Q11, Q15–Q17), same DeepSeek judges, retrieval scoped to the 2023 journal (`--document-title "2023 Journal SOFAFEA"`), tagged `baseline` vs `semantic` in `rag_evaluation_results.json`.

**Results:**

| Metric | Fixed window | Semantic | Verdict |
|---|---|---|---|
| context_precision | 0.68 | **0.79** | semantic wins (+15%) |
| retrieval_precision@k | 0.34 | 0.33 | tie |
| context_recall | **0.48** | 0.32 | fixed wins (−34%) |
| context_entity_recall | **0.77** | 0.49 | fixed wins |
| faithfulness | **0.84** | 0.80 | fixed wins |
| answer relevancy | **0.92** | 0.90 | ≈ tie |
| answer semantic similarity | **0.84** | 0.82 | ≈ tie |
| rubric score (avg 0–2) | **1.29** | 1.14 | fixed wins |
| rubric distribution (0/1/2) | 1/3/3 | 0/6/1 | fixed wins (fewer perfect 2s) |

**Per-question casualties and winners:** Q9 was identical (perfect in both). Q16 *improved* (recall 0→0.25, rubric 0→1). But Q15 collapsed (recall 1.0→0.0, rubric 2→1) and Q17 regressed (recall 1.0→0.63, rubric 2→1) — the list questions lost completeness when the Chart/table content was re-segmented.

**Verdict: do not ship.** The decision rule was "ship if recall and rubric rise without hurting precision" — they fell. The fixed 1000/100 window stays the default, and `SEMANTIC_CHUNKING` ships as an opt-in experiment for precision-sensitive corpora.

**What the harness taught me:** precision and recall pull in opposite directions when you change chunking — breadcrumbs made retrieved chunks better *labeled* but the re-segmentation hid facts the overlap used to carry. Overlap wasn't the problem, so the next experiments are retrieval-side (a cross-encoder reranker; the hybrid BM25+vector leg has since been implemented), not chunking-side. And the whole decision cost ~30 minutes of eval runs instead of a rewrite — the harness made the experiment falsifiable.

---

## Hybrid Retrieval: Change Log, Measured A/B, Trade-offs & Decision

**Why I made the change** — pure vector cosine fails in three logged ways: exact-name misses ("J. Perkins" vs "Joshua Perkins"), cross-chunk answers, and ambiguous pronouns. The first two are lexical, not semantic, problems — no embedding will equate an abbreviation with a full name. A keyword leg fixes them, and because pgvector already lives inside Postgres, full-text search costs zero new infrastructure.

**What changed (all implemented):**
- Schema: `document_chunks` and `ancestry_data` gained a generated `tsvector` column (`search_vector`, `to_tsvector('english', ...)`) plus a GIN index — in `database/supabase_setup.sql` (with an idempotent `ALTER TABLE ... ADD COLUMN IF NOT EXISTS` block for existing databases) and in the SQLAlchemy models so fresh `create_all` installs get it too.
- Retrieval: `RetrievalService.search_hybrid_chunks()` / `search_hybrid_ancestry()` run the vector cosine query and a `websearch_to_tsquery` full-text query, then fuse the two ranked lists with Reciprocal Rank Fusion — score = Σ 1 / (k + rank), `RRF_K=60`.
- Wiring: `/search`, `/ask`, and the LangGraph `retrieve` node call the hybrid methods when `HYBRID_SEARCH=true`.
- Safety: if the full-text leg errors (migration not yet applied), the service logs and falls back to vector-only — the flag can never break retrieval.

**Trade-offs I defend:** plus — no new system to run (FTS is native Postgres), ~1–5 ms added latency, zero token cost, ingestion unchanged because the column is generated. Minus — `ts_rank` is term-frequency based, not literal BM25 (true BM25 would need OpenSearch/ParadeDB); both legs share one database, so hybrid can't mask a broken vector index; and RRF gives a rank-based score, not a calibrated probability, so the fused score is ordering-only.

**Measured A/B (harness, 23 questions, full 3-document archive — 2023 + 2022 journals + ARHO scrap):**
- Protocol: `rag_evaluation.py --evaluator custom` run twice over the identical eval set and documents, tagged `vector-baseline` (HYBRID_SEARCH=false) vs `hybrid`. The harness itself was made hybrid-aware first — it now routes retrieval through `search_hybrid_chunks` / `search_hybrid_ancestry` exactly like `/ask`, so the measured path is the production path.

| Metric | Vector-only | Hybrid | Verdict |
|---|---|---|---|
| context_precision | **0.656** | 0.639 | vector wins (−2.6%) |
| retrieval_precision@k | **0.401** | 0.363 | vector wins |
| context_recall | **0.511** | 0.497 | ≈ tie (−2.7%) |
| context_entity_recall | 0.675 | **0.709** | hybrid wins (+5.1%) |
| faithfulness | 0.856 | **0.923** | hybrid wins (+7.8%) |
| answer relevancy | 0.890 | **0.905** | ≈ tie |
| answer semantic similarity | **0.835** | 0.828 | ≈ tie |
| rubric score (avg 0–2) | **1.609** | 1.478 | vector wins (−8.1%) |
| rubric distribution (0/1/2) | 3/3/17 | 5/2/16 | vector wins (more 0s) |
| avg retrieval step | 267 ms | 333 ms | +66 ms (one extra SQL query) |
| total answer cost (23 q) | $0.0631 | $0.0634 | flat |

**Where it improved:** Q13 "Did Caesar Russell marry Juda Cakenahew?" went rubric 0→2 (precision 0→0.50, recall 0→0.67) — the textbook exact-name miss the keyword leg was built for. Q10 (evidence Caesar Russell died in Africa) went 1→2 (precision →0.93, recall 0→0.60). Aggregate faithfulness rose 0.856→0.923 and entity recall 0.675→0.709 — FTS surfaces proper nouns the embedding misses.

**Where it failed:** four regressions — Q3 ship-to-Calcutta 2→1 (recall 1.0→0.67), Q11 Robert Carter III's religious journey 1→0 (precision 1.0→0.0), Q19 count of enslaved people freed 2→0 (precision 0.25→0.0), Q22 Harriet Brooker↔Caesar Russell relationship 2→0 (recall 1.0→0.33). The pattern: multi-hop, numeric, and relationship questions — the FTS leg matches the *names* in the question and RRF promotes those keyword-only chunks over the semantically-right ones. RRF is rank-based, so a name-matching chunk can outrank the vector's contextual answer.

**Verdict: do not ship as the default.** Same decision rule as the chunking A/B (keep the change if recall and rubric rise without hurting precision) — they fell: rubric 1.609→1.478, precision 0.656→0.639, and zero-rubric answers rose 3→5. The exact-name hypothesis was confirmed, but only on name-centric questions, and the fusion paid for it everywhere else.

**Final decision & next steps:**
- Roll the default back to vector-only (`hybrid_search=False` in `config.py`); keep the hybrid path implemented and one env var away for name-heavy corpora.
- Next experiments, in order: (1) **weighted RRF** — damp the FTS leg (e.g. 0.5×) or require a vector-similarity floor so keyword-only chunks can't hijack ranking; (2) **query-type gating** — apply the FTS leg only when the classifier detects a name/entity query, skip it for multi-hop/numeric/relationship questions; (3) **cross-encoder reranker** over the fused candidates — the next retrieval-side experiment; (4) iterate with `--questions` subsets instead of full 23-question runs.

---

## 4. "How would you prove this system is actually good — with numbers?"

> Four layers, and the first two already have a working harness — `rag_evaluation.py` runs a 23-question golden eval set (SOFAFEA journal questions with gold answers and expected sources) through the real `/ask` pipeline and logs per-question metrics to `rag_evaluation_results.json`. **Retrieval:** context precision (are relevant chunks ranked high), retrieval precision@k, context recall (did retrieval surface everything the gold answer needs), and context entity recall (key entities present in the retrieved context). **Generation:** faithfulness (is every claim in the answer supported by the context), answer relevancy, answer↔gold semantic similarity, and a 0/1/2 rubric score against the gold answer — LLM-as-judge plus deterministic checks. Every LLM-judged metric has two independent implementations — my hand-rolled judge prompts and the `ragas` library running the same metrics through DeepSeek + local Ollama (`--evaluator ragas`); on a 3-question sample they agree on direction while differing in strictness (ragas faithfulness 0.84, relevancy 0.93, precision 0.67, recall 0.56), which is exactly the cross-validation I want before trusting any judge. **Operations:** per-step latency percentiles, token usage, and USD cost per query from my event log — including peak vs off-peak and cache hit/miss splits. **Business:** answer rate and cost per research session. The key design decision: I instrumented *before* optimizing, which is how I found the 2.2s embedding overhead and the thinking-mode cost problem — so I could prove each fix with before/after numbers, not vibes. What's left is the CI gate that runs the harness weekly and blocks merges on regressions.

## 5. "Design the multi-agent research workflow you'd build on this platform."

> I built it — `agent_orchestration.py`, a LangGraph state machine exposed as `POST /api/queries/research`. The graph is `classify → retrieve → generate → verify → approve`, reusing the existing services rather than duplicating them: `rule_based_classify` picks the reasoning effort (default `high`), `embedding_service` + `RetrievalService` gather context (top-8 chunks + top-5 person records), `generate_response_with_usage` drafts the answer, and a second LLM pass — the **verifier** — checks every footnote citation against the retrieved context and reports unsupported ones. The **approve** node is a human-in-the-loop gate: with `REQUIRE_HUMAN_APPROVAL=true` the run pauses via LangGraph's `interrupt()` and resumes through `POST /research/{thread_id}/approve` with `approve|revise`, looping rejected drafts back to `generate`. Two guardrails are enforced in code, not prose: a cumulative token budget per run (`AGENT_TOKEN_BUDGET`) that caps runaway agent loops, and an automatic fallback — if the agent errors, the endpoint drops to the direct RAG path so the caller always gets an answer. Runs are checkpointed by `thread_id`, and every node logs its timings and tool calls into `rag_summary.json`, so an agent run is as auditable as a plain query.

## 6. Whiteboard: "A state archive wants this for 1M+ records, multiple research groups, strict privacy. Design it."

> **Tenancy:** row-level `tenant_id` on documents, chunks, and person records with PostgreSQL RLS as the enforcement boundary; pgvector queries filtered by tenant metadata, not separate vector stores per tenant at this scale. **Scale:** Postgres is fine for metadata and a few million vectors; beyond ~5M vectors I'd benchmark a dedicated vector store (Qdrant/Milvus) and split — Postgres for truth, vector store for recall. **Ingestion:** async task queue with backpressure; batched embeddings (my `EMBED_BATCH_SIZE` work applies directly). **Privacy:** local embeddings by default so records never leave the tenant's trust boundary; on-prem GPU inference for tenants that prohibit cloud LLMs; encryption at rest, TLS, audit trail on every read and write. **Cost governance:** per-tenant token/cost budgets with alerts, because "unlimited AI" is the scariest phrase in a government budget. **Availability:** stateless API replicas, multi-AZ Postgres with PITR, RPO/RTO agreed per tenant tier.

## 7. Whiteboard: "Same customer, but air-gapped on-prem. No cloud at all."

> First decision: measure before buying. Benchmark required tokens/sec at p95 for the expected question volume, then size GPUs. For a modest archive: 1–2 GPUs with MIG slices for deterministic multi-tenant isolation (vGPU for bursty dev use, passthrough only for fine-tuning). Fabric: fat-tree topology; RoCE unless the budget can justify InfiniBand (I'd ask whether they're *training* models — IB pays off at training scale, RoCE is usually the right default). Storage: fast NVMe-backed shared filesystem for models and vector indices, object storage for document originals. Serving: vLLM or Triton for LLM inference, Kubernetes with Helm and operators, images from an on-prem registry (Quay) with scanning. Observability: Prometheus/Grafana inside the enclave. The narratives that win here: derived data is rebuildable (keep source documents as the system of record), and every component must support offline updates and an offline model path.

## 8. "You track cost per query. How would you cut the AI bill 10×?"

> Five levers, most already proven in this project: (1) **Route by difficulty** — my reasoning classifier sends "hi" and "who is X" to `low` effort; a small/fast model for simple queries and the big model only for research questions. (2) **Prompt-cache discipline** — I log cache hit/miss tokens because DeepSeek bills them at different rates; keeping the system prompt and shared context stable turns a big slice of input tokens into cheap cache hits. (3) **Batch where possible** — embeddings are already batched (the 294s → <60s fix); batch LLM calls for offline tasks like entity extraction. (4) **Off-peak scheduling** — DeepSeek charges 2× during 01:00–04:00 and 06:00–10:00 UTC; heavy batch jobs run off-peak. (5) **Caching** — semantic-dedup cache for repeated answers; Redis for hot embeddings. I'd also add a daily spend dashboard and per-query cost alerts, because the first cost optimization is making cost visible — which this system already does.

## 9. "How do you secure a RAG system? Attack it for me."

> The structural attack is prompt injection — RAG pastes untrusted document text into a prompt, so the document *is* the attack surface. I implemented the layered defenses in the genealogy platform. **Treat retrieved text strictly as data:** `llm_service.py` wraps every retrieved chunk between `<retrieved_document>` tags and HTML-escapes angle brackets inside the content, so a malicious document cannot inject its own closing tag to break out of the data block — and the system prompt's SECURITY RULES order the model to ignore instructions found inside excerpts. **Keep the system prompt outside the retrievable data plane:** prompts are static code constants, context is injected only into the user message, and a runtime assertion rejects any caller-supplied prompt carrying the data-plane delimiters. **Make the honesty rule enforceable, not a request:** `answer_verifier.py` runs a second LLM pass after every `/ask` (gated by `VERIFY_ANSWERS=true`) that audits each claim against the retrieved context; an `unsupported` draft is replaced with an honest refusal, the verifier fails open on its own errors, and its verdict, reason, tokens, and cost land in `rag_summary.json` — measured at ~2s and ~$0.0027 per query, so the guardrail's cost is visible, not free. Uploads get defense-in-depth: extension whitelist plus magic-byte checks (PDF `%PDF-`, DOCX `PK`, UTF-8 for text/JSON), UUID-prefixed filenames, and a size cap — sandboxed parsing and malware scanning are still on the roadmap. The research agent already ran a citation auditor with a human-in-the-loop gate, and it inherits the same delimited context. Around that: RBAC and SSO from my admin panel, a tamper-proof database-level audit trail, rate limiting, secrets in a manager, and TLS everywhere. The line I'd deliver: for RAG, security isn't a perimeter — it's prompt construction plus auditability.

## 10. "What's your actual disaster-recovery story, with real numbers?"

> The admin panel's production database on Azure PostgreSQL streams changes continuously to a second Azure server via native logical replication — publication on the primary, subscription on the backup, SSL and a dedicated least-privilege replication user. That's a near-zero-RPO data story. I monitor lag with `pg_wal_lsn_diff(pg_current_wal_lsn(), confirmed_flush_lsn)` and validate with row-count checks plus deliberate test inserts. The lessons I hit: logical replication ships row data, **not schema** — keys and constraints had to be rebuilt on the target; and an unattended replication slot accumulates WAL and can fill the source disk, so slot hygiene is operational, not optional. RTO is covered by redeployable stateless services plus PITR. And I'd only quote RPO/RTO numbers after a real restore drill.

## 11. "What does your production observability dashboard look like for this system?"

> Four tiles. **Latency:** p50/p95 per stage (embed, retrieval, LLM, verifier) from the event log — the p95 is almost always the LLM step, which is why reasoning classification exists. **Cost:** tokens and USD per day, split cache hit/miss and peak/off-peak, with a budget alert. **Quality:** best retrieval similarity distribution per query, plus `rag_evaluation.py` running the 23-question golden set so its context precision/recall and faithfulness scores surface as a dashboard trend (the weekly CI job is the remaining piece). **Reliability:** embedding failure rate, LLM error rate, and verifier fail-open events. Underneath: structured logs with correlation IDs and traces across embed → search → LLM → verify. My `rag_summary.json` is the lightweight prototype of this; production goes Prometheus + Grafana + OpenTelemetry.

## 12. "Kubernetes: how exactly would you run this platform?"

> Helm chart with three components: a stateless API Deployment behind an ingress with TLS, HPA on request latency; an ingestion worker Deployment that drains a queue (Redis or a Postgres-backed queue) with backpressure; and Redis as a cache. State stays out of the cluster where possible — Postgres is managed. Images in Quay, signed and scanned in CI. Networking: NetworkPolicies so only the API talks to the DB and workers talk to the queue. Storage: PVCs only for ephemeral uploads before they move to object storage — never as the system of record. GPU note: if we ever self-host inference, the serving pods request GPU slices via device plugin with node labels per MIG profile, and I'd right-size requests/limits from the per-step timing data I already collect.

## 13. "Pick the storage for this archive and defend it."

> Document originals → **object storage** (Azure Blob): immutable, cheap, versioned, and they're the source of truth from which embeddings can be rebuilt. Database → managed block storage behind Azure PostgreSQL: IOPS and latency matter, and managed PaaS removes undifferentiated ops. For an on-prem version: Postgres on **SAN** for the write-heavy OLTP side, shared file storage (NFS) for uploads if simplicity wins, and I'd mention vSAN only in a VMware hyperconverged estate. Backups: daily snapshots + PITR, with retention matched to RPO/RTO and tested restores.

## 14. Customer objection: "Our data is too sensitive for cloud LLMs. What do you propose?"

> "Then the data never leaves your control." Architecture: local embedding models (my default is already local Ollama), and self-hosted open-weight LLMs via vLLM on your GPU estate — with vGPU/MIG partitioning per tenant. The pipeline, vector store, and logs all stay on-prem; observability via Prometheus/Grafana in-enclave. I'd frame the trade-off honestly: you trade the latest hosted model quality and zero-ops for sovereignty and compliance — and I can show the cost/latency delta with a benchmark. This is exactly the on-prem story a Solutions Architect is hired to design, not dodge.

## 15. "How do you build a 30-minute demo that wins the deal?"

> Reverse the usual mistake of showing features. I start from the customer's problem: load a *real* document from their world (for this project, a SOFAFEA journal), ask a hard research question — "Who was Joshua 'Old Jock' Perkins and where was he born?" — and show the cited answer land with footnotes. Then the three trust moments: the per-query cost and latency dashboard (financial transparency), an honest "not in the documents" refusal — now enforced by the answer verifier, not just requested in the prompt (trust), and the audit trail (governance). I always demo on their data, never canned data; and I rehearse the failure paths — if Ollama is slow or the LLM errors, the demo should visibly retry and recover, because prospects buy resilience, not slides.

## 16. "Tell me about a time you were wrong or something failed in production."

> The thinking-mode bug: DeepSeek's reasoning tokens counted against a 300-token budget, so the model spent its entire budget thinking and returned an empty answer — the chatbot showed only sources. I'd shipped a feature (thinking mode) without checking its interaction with token limits. The fix had three parts: reserve enough budget for the final answer, retry without thinking mode if content is empty, and log the reasoning mode per query so it's visible. The lesson I carry: every new LLM feature needs a budget and an observable fallback — and my per-query logging is what made the failure diagnosable in the first place.

## 17. Rapid technical judgment (answer in 2–3 sentences each)

- **Fine-tuning vs RAG for genealogy?** RAG first: the archive changes constantly, answers must be citable, and RAG is cheaper to maintain; fine-tuning only for style/language specialization once RAG quality plateaus.
- **pgvector vs a dedicated vector store?** pgvector at this scale — one less system, transactional consistency with metadata, IVFFlat→HNSW when needed; re-evaluate past ~5M vectors or when filtering gets complex.
- **RoCE or InfiniBand for a customer?** RoCE by default — Ethernet economics and existing fabrics; InfiniBand when training large models where the fabric is the bottleneck.
- **When would you add a GPU to this system?** When either the customer demands on-prem inference or batch embedding volume makes CPU p95 unacceptable — then size by measured tokens/sec, not spec sheets.
- **How do you size a GPU cluster?** From workload benchmarks: tokens/sec at p95 for inference, model size + interconnect for training — never from the vendor's slide.
- **Why is your embedding model local?** Privacy and zero marginal cost; the abstraction layer lets a customer swap to OpenAI/Azure embeddings when they need multilingual quality and accept the data egress.
- **How do you prevent an agent loop from burning money?** I enforce a cumulative completion-token budget inside the generate/verify nodes (`AGENT_TOKEN_BUDGET`), the workflow is a fixed acyclic graph with one optional revision loop gated by human approval, and every node logs its tool calls and timings to `rag_summary.json` — all implemented in `agent_orchestration.py`.
- **How do you defend against prompt injection?** Delimit and escape retrieved text so it is strictly data, keep prompts out of the data plane with a runtime assertion, and run `answer_verifier.py` to catch the model if it obeys injected instructions — all implemented, failing open on verifier errors.

---

## Scenario cheat-sheet (30-second story per persona)

- **CIO:** cost per query is visible and budgeted; data stays sovereign via local embeddings/on-prem inference.
- **Security lead:** RBAC, DB-trigger audit trail, prompt-injection defenses (escaped delimiters + verifier-enforced honesty rule), TLS/SSO, least-privilege replication.
- **Data steward:** 30,311 records with a tamper-proof audit trail and real-time replicated backup.
- **Researcher:** cited, honest answers from the archive itself — no invented facts.
- **Developer/platform team:** instrumented pipeline, config-driven batch tuning, retry-and-fail-loudly, benchmark harness.

*Tip for round two: the interviewer is probing judgment under uncertainty. Every answer above follows one pattern — state the trade-off, give your decision, back it with a number from this project, and name what you'd measure next.*

---

## Metric Definitions (2–3 sentences each)

- **RAGAS** — an open-source Python library for RAG evaluation that computes LLM-as-judge metrics (faithfulness, context precision/recall, answer relevancy, answer semantic similarity) from question/answer/retrieved-contexts/reference rows. In this project it runs as a second judge layer in `rag_evaluation.py` (`--evaluator ragas`) with DeepSeek as the judge and local Ollama embeddings, cross-validating my hand-rolled judge prompts on the same inputs.
- **p50 and p99** — latency percentiles that summarize a response-time distribution: p50 (the median) is the value 50% of requests beat, representing the typical experience; p99 is the value 99% of requests beat, so only the worst 1% are slower — it captures the tail latency that the unluckiest users actually feel. SLAs are almost always written on p95/p99 rather than averages, because an average hides slow outliers while a single slow request can dominate a user's entire impression.
- **Reranker latency** — the time a cross-encoder model takes to score each retrieved candidate (query, chunk) pair in order to re-sort the top results for relevance. It is added latency that sits between retrieval and generation, which is why you only rerank a small candidate set (top-50, not top-500) and batch the scoring — the quality gain must justify the latency it adds to the pipeline.
- **Total response time** — the end-to-end wall-clock duration from the user submitting a query until the final answer is fully returned, i.e., embed + retrieval (+ optional rerank) + LLM generation combined. This is the number the user actually experiences — in my system it's the `duration_seconds` field logged per query in `rag_summary.json`, decomposed into per-step timings so the slowest stage can be identified.
- **Chunk hit rate** — in retrieval evaluation, the fraction of test queries for which the known-correct chunk appears within the top-k retrieved results (also called hit-rate@k); in my project, the best similarity score logged per query is its live proxy. It is the first number to measure in a golden-dataset evaluation, because if the right chunk is never retrieved, no amount of prompt engineering can produce a correct answer — retrieval recall is the ceiling for the whole pipeline.

---

## Lio interview questions

**Format note:** this is a 30-minute technical deep dive with a Forward Deployed Engineer. The instruction is to pick *one* project and walk it through. Lead with the **Genealogy RAG platform** — it hits every box in the JD: Python + React (+ TypeScript build tooling), LLMs, a multi-step LangGraph agent, enterprise-grade integration (Supabase/Azure Postgres, logical replication, RBAC + audit trail), and measured outcomes. Suggested 30-minute arc: (0–5) what it is and your exact role; (5–15) architecture walkthrough with the two decisions you're proudest of; (15–22) one failure + fix with numbers; (22–27) the enterprise/customer angle (the 1M-record whiteboard, or map it to procurement); (27–30) your questions for them.

**The one-line opener:** *"I built a genealogy research platform that answers questions over a 30,000-record archive with cited, verifiable answers — FastAPI + React, Supabase + pgvector, DeepSeek with a Groq fallback, local embeddings, a LangGraph research agent, and a per-query cost/latency event log. I owned the full stack end to end, from ingestion and retrieval to a second-LLM honesty verifier."*

---

1. **"Walk me through a project you've built."**

> I'll walk you through the genealogy research platform. The problem was that researchers needed answers from a 30,000-record historical archive with citations, and a wrong or invented fact was unacceptable. The stack is FastAPI on the backend, React on the frontend, Supabase PostgreSQL with pgvector for vector search, DeepSeek as the primary LLM with Groq as a fallback, and local Ollama embeddings so documents never leave the customer's trust boundary. The pipeline is upload → extract text → chunk → embed → store in pgvector → retrieve → generate → verify. Two results I'm proudest of: uploads used to take about 294 seconds because every chunk made its own embedding call and Ollama has a fixed ~2.2-second overhead per call. I made the batch size configurable, and uploads dropped under 60 seconds. Second, after every answer, a second LLM pass audits the claims against the retrieved context and replaces unsupported ones with an honest refusal — about 2 seconds and 0.3 cents per query. And I built a 23-question evaluation harness that measures context precision, recall, and rubric scores, so every change I make is provable.

2. **"What was your role, and what did you personally own?"**

> I owned it end to end — this was effectively a solo full-stack build. I wrote the retrieval and embedding services, the LLM wrapper, the document processor, the LangGraph research agent, the answer verifier, and the upload security path with magic-byte validation. I also built the admin panel with JWT authentication, role-based access control, a database-trigger audit trail, and Azure logical replication to a backup server. The habit I'm most deliberate about: I instrumented before I optimized. Every query logs per-step timings, token usage, and dollar cost, so when I claim a fix worked, I can show before-and-after numbers instead of a feeling.

3. **"Tell me about a technical decision where the data changed your mind."**

> Semantic chunking. I built heading-aware chunking with breadcrumb prefixes because I expected it to win — chunks become self-contained and better labeled. I ran an A/B on a 7-question evaluation set and the data disagreed with my hypothesis: it raised context precision from 0.68 to 0.79, but context recall fell from 0.48 to 0.32 and the average rubric score dropped from 1.29 to 1.14. The re-segmentation was hiding facts that the fixed-window overlap used to carry. So I did not ship it. I kept the fixed 1,000-character window with 100-character overlap as the default and made semantic chunking an opt-in flag. That decision cost me about 30 minutes of eval runs instead of a rewrite — the harness let me falsify my own idea cheaply.

4. **"Tell me about a time something failed in production."**

> The thinking-mode bug. DeepSeek has a reasoning mode, and the reasoning tokens counted against a 300-token output budget. So the model spent its entire budget thinking and returned an empty answer — the chatbot showed sources but no response. I had shipped thinking mode without checking its interaction with the token limit. The fix had three parts: reserve enough budget for the final answer, retry without thinking mode if the output comes back empty, and log the reasoning mode per query so it stays visible. The lesson I carry: every new LLM feature ships with a budget and an observable fallback — and the per-query logging is what made this diagnosable in the first place.

5. **"How do you make an LLM feature reliable enough for an enterprise customer?"**

> Three layers. Grounding: the model answers from retrieved chunks with footnotes, so every claim is traceable to a source. Enforcement: I don't rely on the model promising to behave — a second LLM pass audits every answer against the retrieved context, and drafts with unsupported claims get replaced by an honest "I can't verify this" refusal. That verifier fails open if it itself errors, so it can never break the answer path. Observability: every query logs per-step latency, token usage, cache hits, and USD cost. For an enterprise, reliability and cost have to be visible before you can sell them — otherwise you're asking the customer to trust you twice.

6. **"Where does your retrieval fail, and what did you do about it?"**

> Three failure classes showed up in my logs: exact-name misses — "J. Perkins" versus "Joshua Perkins" — because embeddings are fuzzy; cross-chunk answers, where a fact is split across two chunks; and ambiguous pronouns like "his mother." Pure vector search can't equate an abbreviation with a full name, so I implemented hybrid retrieval: Postgres full-text search — `tsvector` with a GIN index, `websearch_to_tsquery` plus `ts_rank` — fused with vector cosine using Reciprocal Rank Fusion, where each ranked list contributes one over (k plus rank). It runs behind a config flag with a vector-only fallback, and it cost zero new infrastructure because full-text search lives in the same Postgres. That pattern maps directly to procurement data, which is full of exact identifiers — vendor names, part numbers, contract IDs.

7. **"A customer runs SAP or Coupa. How would you integrate with their ERP?"**

> Treat the ERP as the system of record and integrate at the data plane. First, read-only connectors — their APIs, webhooks, or file feeds — to pull vendors, contracts, and pricing into the agent's context; never a copied database that drifts out of sync. Then map their schema once and reuse it. For writes — creating a purchase order or triggering an approval — every action sits behind a human-in-the-loop gate. That's exactly how my research agent works today: it drafts and verifies, and with `REQUIRE_HUMAN_APPROVAL=true` it pauses and waits for a human decision before anything executes. On top of that: SSO and role-based access, plus a tamper-proof audit trail, because in procurement every action needs to answer "who did what, when, and why."

8. **"How would you build an agent that negotiates with a vendor without burning money?"**

> Three guardrails, and I've already enforced all three in code. One: a cumulative token budget per run, so the agent physically cannot loop forever. Two: a fixed acyclic workflow — classify, retrieve, generate, verify, approve — with a single optional revision loop that's gated by human approval, so runaway behavior is structurally impossible. Three: per-node logging of every tool call, timing, and token cost, so an agent run is as auditable as a normal query. Negotiation is just another node in that graph — but the commit action, actually sending the counter-offer, is always the human-approved step. And if the agent errors, it falls back to a simpler direct path, so the customer always gets a result.

9. **"How do you move from discovery to production quickly?"**

> Instrument first, then ship behind flags with fallbacks. In this project, every optimization — semantic chunking, hybrid retrieval, the answer verifier — shipped behind a config flag, and every risky LLM feature had a fallback: the verifier fails open, and the research agent falls back to direct retrieval if it errors. That let me deploy fast without betting the whole system on one change, and if something regressed, I could flip it off with a config change instead of a redeploy. For a Forward Deployed role that's the difference between shipping a customer pilot in a week versus a month.

10. **"A customer can't articulate what they want. What do you do?"**

> I anchor on their workflow and one measurable success criterion, then build a thin vertical slice in days, not a platform. For the genealogy project that slice was "answer this one research question with citations." For procurement it would be "cut this one approval cycle from X hours to Y." I demo on their data, never canned data, and I rehearse the failure paths — if the embedding service is slow or the LLM errors, the demo visibly retries and recovers. Customers buy outcomes and resilience, not feature lists, and a working slice inside their system does more discovery than ten requirements meetings.

11. **"Why Lio, and why Forward Deployed?"**

> Because this role is where building meets delivery. I've built the full stack — Python, React, LLMs, a multi-agent workflow, enterprise integration with audit and replication — and the part I enjoy most is where it lands with a real customer and changes their actual workflow. Procurement is a perfect fit for the patterns I've already shipped: grounded retrieval over messy enterprise data, agents with budgets and human approval, and the auditability that regulated industries demand. And joining the first U.S. Forward Deployed team means helping build the playbook, not just following one.

12. **"What's the biggest lesson you'd bring?"**

> Cost and reliability are features, not afterthoughts. I found the 2.2-second embedding overhead and the thinking-mode budget bug only because I instrumented first — and every fix then shipped with a before-and-after number. At Lio's scale, where customers manage billions in spend, "the AI bill is visible and bounded" is a selling point to the CFO, and "the agent never commits without human approval" is a selling point to legal. Those aren't operations details — they're the product.

13. **"Why did you choose a SQL database over NoSQL for this project, and when would NoSQL have been the right call?"**

> Genealogy data is deeply relational, not document-shaped. A document owns chunks, each chunk owns footnotes, and person records link to each other through relationship and related-to fields — so nearly every query is a join, and I get foreign-key integrity, transactions, and cascade deletes for free. More importantly, PostgreSQL is where the specialized search lives: pgvector stores the 768-dim embeddings, and now the `tsvector` columns plus GIN index for hybrid retrieval sit in the same database. Going NoSQL would have forced a second system just for vectors, or given up SQL joins for metadata filtering — at this scale, one system wins. The same Postgres also gives me database-trigger audit trails and logical replication for disaster recovery, which is exactly what an enterprise customer expects from a system of record.
> Where NoSQL would have been the right call: if ingestion were a firehose of heterogeneous, schema-less documents with no join patterns, document storage — MongoDB-style — would fit better; if family-tree traversal became the core product at great depth, a graph database like Neo4j would beat recursive SQL; if the archive grew past roughly five million vectors, I'd split to a dedicated vector database like Qdrant or Milvus and keep Postgres as the source of truth; and for high-velocity analytics on query history, something like Cassandra. My rule: SQL when the data is relational and auditability matters, NoSQL when scale or access patterns break the relational model — and that split point is measurable, not ideological.

**Questions to ask them (closing 3–5 minutes):**
- What does the first 90 days look like for this U.S. FDE — one anchor customer or several?
- How are innovation-partner engagements scoped, and who owns the success criteria?
- What's the hardest integration you've hit with a customer's ERP, and how did the team solve it?
- How do you decide between building a capability into the core platform vs. as a one-off customer deployment?
