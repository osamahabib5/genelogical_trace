# AI Solutions Architect — Second-Round Interview Prep (Sr. AI Solutions Architect)

Second-round questions are deeper, scenario-driven, and whiteboard-heavy. These sample answers go one level below the first-round prep: trade-offs with numbers, failure stories, and customer scenarios — all grounded in the Genealogy RAG platform and the companion admin panel.

**Anchor facts you can cite anywhere:**
- Full RAG stack: FastAPI + React, Supabase PostgreSQL + pgvector (768-dim), DeepSeek LLM with Groq fallback, local Ollama `nomic-embed-text` embeddings.
- Per-query event log (`rag_summary.json`): per-step timings, token usage, cache hit/miss split, USD cost with DeepSeek peak/off-peak pricing, reasoning mode.
- Measured numbers: ~2.2s fixed overhead per Ollama embedding call; upload embedding dropped from ~294s to <60s via batching (`EMBED_BATCH_SIZE`); LLM generation 2–45s depending on reasoning effort (default `low`).
- Admin panel: JWT + RBAC (admin/moderator/viewer), database-trigger audit trail, Azure PostgreSQL logical replication to a backup server, Vercel serverless.
- Agent orchestration (implemented): LangGraph research agent in `agent_orchestration.py`, exposed at `POST /api/queries/research` — classify → retrieve → generate → verify → approve, with token budget, citation verifier, human-in-the-loop resume, and automatic fallback to direct RAG.

---

## 1. "Walk me through one query, end to end, and defend the latency and cost at every step."

> A query hits `/api/queries/ask`. Step one: embed it with local Ollama — historically 2–4s on CPU, dominated by a fixed ~2.2s per-request overhead, which is why I benchmarked batch sizes and made them configurable. Step two: retrieval — pgvector cosine search over chunks plus person records, ~0.1–0.9s. Step three: the LLM call — anywhere from 2s to 45s depending on the reasoning effort my classifier picks (`low` for factoid questions, `high` for comparisons, `max` for multi-step research). Step four: I log every step, token count, and dollar cost to a JSONL event log.
> The trade-offs I defend: (1) local embeddings — privacy and zero cost, at the price of CPU latency; acceptable because retrieval is the cheap part. (2) reasoning classification — it converts latency/cost from a fixed tax into a per-question decision, so "who is Joshua Perkins" doesn't pay for a 40-second thinking session. (3) honesty over coverage — off-topic queries skip retrieval entirely rather than waste tokens on irrelevant context.

## 2. "Your retrieval is pure vector search. Where does it fail, and how would you fix it?"

> Three failure classes, and I can show each in my logs: (1) **Exact-name misses** — "J. Perkins" vs "Joshua Perkins"; embeddings are fuzzy, so exact spellings and abbreviations suffer. (2) **Cross-chunk answers** — a fact split across two 500-char chunks retrieves one but not the other. (3) **Ambiguous pronouns** — "his mother" retrieves nothing relevant.
> Fixes in order of cost: hybrid retrieval (BM25 + vector with reciprocal rank fusion — pgvector is in Postgres, so I can add `tsvector` or OpenSearch without changing the pipeline); a cross-encoder re-ranker over top-50 candidates; query rewriting by the LLM before embedding; and entity linking so a detected name forces a metadata-filtered search. I'd measure each with a golden dataset and keep the change that wins on recall@k without hurting p95 latency.

## 3. "How would you prove this system is actually good — with numbers?"

> Four layers. **Retrieval:** golden set of ~50–100 questions with known-relevant chunks; measure hit-rate@k, MRR, and recall@k. **Generation:** faithfulness (does the answer reflect the retrieved context), citation precision (does each footnote actually support the claim), answer relevance — scored with LLM-as-judge and sampled human review by a domain expert. **Operations:** per-step latency percentiles, token usage, and USD cost per query from my event log — including peak vs off-peak and cache hit/miss splits. **Business:** answer rate and cost per research session. The key design decision: I instrumented *before* optimizing, which is how I found the 2.2s embedding overhead and the thinking-mode cost problem — so I could prove each fix with before/after numbers, not vibes.

## 4. "Design the multi-agent research workflow you'd build on this platform."

> I built it — `agent_orchestration.py`, a LangGraph state machine exposed as `POST /api/queries/research`. The graph is `classify → retrieve → generate → verify → approve`, reusing the existing services rather than duplicating them: `rule_based_classify` picks the reasoning effort (default `high`), `embedding_service` + `RetrievalService` gather context (top-8 chunks + top-5 person records), `generate_response_with_usage` drafts the answer, and a second LLM pass — the **verifier** — checks every footnote citation against the retrieved context and reports unsupported ones. The **approve** node is a human-in-the-loop gate: with `REQUIRE_HUMAN_APPROVAL=true` the run pauses via LangGraph's `interrupt()` and resumes through `POST /research/{thread_id}/approve` with `approve|revise`, looping rejected drafts back to `generate`. Two guardrails are enforced in code, not prose: a cumulative token budget per run (`AGENT_TOKEN_BUDGET`) that caps runaway agent loops, and an automatic fallback — if the agent errors, the endpoint drops to the direct RAG path so the caller always gets an answer. Runs are checkpointed by `thread_id`, and every node logs its timings and tool calls into `rag_summary.json`, so an agent run is as auditable as a plain query.

## 5. Whiteboard: "A state archive wants this for 1M+ records, multiple research groups, strict privacy. Design it."

> **Tenancy:** row-level `tenant_id` on documents, chunks, and person records with PostgreSQL RLS as the enforcement boundary; pgvector queries filtered by tenant metadata, not separate vector stores per tenant at this scale. **Scale:** Postgres is fine for metadata and a few million vectors; beyond ~5M vectors I'd benchmark a dedicated vector store (Qdrant/Milvus) and split — Postgres for truth, vector store for recall. **Ingestion:** async task queue with backpressure; batched embeddings (my `EMBED_BATCH_SIZE` work applies directly). **Privacy:** local embeddings by default so records never leave the tenant's trust boundary; on-prem GPU inference for tenants that prohibit cloud LLMs; encryption at rest, TLS, audit trail on every read and write. **Cost governance:** per-tenant token/cost budgets with alerts, because "unlimited AI" is the scariest phrase in a government budget. **Availability:** stateless API replicas, multi-AZ Postgres with PITR, RPO/RTO agreed per tenant tier.

## 6. Whiteboard: "Same customer, but air-gapped on-prem. No cloud at all."

> First decision: measure before buying. Benchmark required tokens/sec at p95 for the expected question volume, then size GPUs. For a modest archive: 1–2 GPUs with MIG slices for deterministic multi-tenant isolation (vGPU for bursty dev use, passthrough only for fine-tuning). Fabric: fat-tree topology; RoCE unless the budget can justify InfiniBand (I'd ask whether they're *training* models — IB pays off at training scale, RoCE is usually the right default). Storage: fast NVMe-backed shared filesystem for models and vector indices, object storage for document originals. Serving: vLLM or Triton for LLM inference, Kubernetes with Helm and operators, images from an on-prem registry (Quay) with scanning. Observability: Prometheus/Grafana inside the enclave. The narratives that win here: derived data is rebuildable (keep source documents as the system of record), and every component must support offline updates and an offline model path.

## 7. "You track cost per query. How would you cut the AI bill 10×?"

> Five levers, most already proven in this project: (1) **Route by difficulty** — my reasoning classifier sends "hi" and "who is X" to `low` effort; a small/fast model for simple queries and the big model only for research questions. (2) **Prompt-cache discipline** — I log cache hit/miss tokens because DeepSeek bills them at different rates; keeping the system prompt and shared context stable turns a big slice of input tokens into cheap cache hits. (3) **Batch where possible** — embeddings are already batched (the 294s → <60s fix); batch LLM calls for offline tasks like entity extraction. (4) **Off-peak scheduling** — DeepSeek charges 2× during 01:00–04:00 and 06:00–10:00 UTC; heavy batch jobs run off-peak. (5) **Caching** — semantic-dedup cache for repeated answers; Redis for hot embeddings. I'd also add a daily spend dashboard and per-query cost alerts, because the first cost optimization is making cost visible — which this system already does.

## 8. "How do you secure a RAG system? Attack it for me."

> The structural attack is prompt injection — RAG pastes untrusted document text into a prompt, so the document *is* the attack surface. Defenses, in layers: treat retrieved text strictly as data, delimit it explicitly, and instruct the model to ignore directives found inside; validate and sandbox uploads (extension + magic bytes + scanning); keep the system prompt outside the retrievable data plane; and make the model's honesty rule ("say not-in-documents rather than invent") a guardrail that a verifier agent enforces. Around that: RBAC and SSO from my admin panel, a tamper-proof database-level audit trail, rate limiting, secrets in a manager, and TLS everywhere. The line I'd deliver: for RAG, security isn't a perimeter — it's prompt construction plus auditability.

## 9. "What's your actual disaster-recovery story, with real numbers?"

> The admin panel's production database on Azure PostgreSQL streams changes continuously to a second Azure server via native logical replication — publication on the primary, subscription on the backup, SSL and a dedicated least-privilege replication user. That's a near-zero-RPO data story. I monitor lag with `pg_wal_lsn_diff(pg_current_wal_lsn(), confirmed_flush_lsn)` and validate with row-count checks plus deliberate test inserts. The lessons I hit: logical replication ships row data, **not schema** — keys and constraints had to be rebuilt on the target; and an unattended replication slot accumulates WAL and can fill the source disk, so slot hygiene is operational, not optional. RTO is covered by redeployable stateless services plus PITR. And I'd only quote RPO/RTO numbers after a real restore drill.

## 10. "What does your production observability dashboard look like for this system?"

> Four tiles. **Latency:** p50/p95 per stage (embed, retrieval, LLM) from the event log — the p95 is almost always the LLM step, which is why reasoning classification exists. **Cost:** tokens and USD per day, split cache hit/miss and peak/off-peak, with a budget alert. **Quality:** best retrieval similarity distribution per query, and a weekly golden-dataset eval job so quality regressions surface as a dashboard trend. **Reliability:** embedding failure rate and LLM error rate with provider fallback events. Underneath: structured logs with correlation IDs and traces across embed → search → LLM. My `rag_summary.json` is the lightweight prototype of this; production goes Prometheus + Grafana + OpenTelemetry.

## 11. "Kubernetes: how exactly would you run this platform?"

> Helm chart with three components: a stateless API Deployment behind an ingress with TLS, HPA on request latency; an ingestion worker Deployment that drains a queue (Redis or a Postgres-backed queue) with backpressure; and Redis as a cache. State stays out of the cluster where possible — Postgres is managed. Images in Quay, signed and scanned in CI. Networking: NetworkPolicies so only the API talks to the DB and workers talk to the queue. Storage: PVCs only for ephemeral uploads before they move to object storage — never as the system of record. GPU note: if we ever self-host inference, the serving pods request GPU slices via device plugin with node labels per MIG profile, and I'd right-size requests/limits from the per-step timing data I already collect.

## 12. "Pick the storage for this archive and defend it."

> Document originals → **object storage** (Azure Blob): immutable, cheap, versioned, and they're the source of truth from which embeddings can be rebuilt. Database → managed block storage behind Azure PostgreSQL: IOPS and latency matter, and managed PaaS removes undifferentiated ops. For an on-prem version: Postgres on **SAN** for the write-heavy OLTP side, shared file storage (NFS) for uploads if simplicity wins, and I'd mention vSAN only in a VMware hyperconverged estate. Backups: daily snapshots + PITR, with retention matched to RPO/RTO and tested restores.

## 13. Customer objection: "Our data is too sensitive for cloud LLMs. What do you propose?"

> "Then the data never leaves your control." Architecture: local embedding models (my default is already local Ollama), and self-hosted open-weight LLMs via vLLM on your GPU estate — with vGPU/MIG partitioning per tenant. The pipeline, vector store, and logs all stay on-prem; observability via Prometheus/Grafana in-enclave. I'd frame the trade-off honestly: you trade the latest hosted model quality and zero-ops for sovereignty and compliance — and I can show the cost/latency delta with a benchmark. This is exactly the on-prem story a Solutions Architect is hired to design, not dodge.

## 14. "How do you build a 30-minute demo that wins the deal?"

> Reverse the usual mistake of showing features. I start from the customer's problem: load a *real* document from their world (for this project, a SOFAFEA journal), ask a hard research question — "Who was Joshua 'Old Jock' Perkins and where was he born?" — and show the cited answer land with footnotes. Then the three trust moments: the per-query cost and latency dashboard (financial transparency), an honest "not in the documents" refusal (trust), and the audit trail (governance). I always demo on their data, never canned data; and I rehearse the failure paths — if Ollama is slow or the LLM errors, the demo should visibly retry and recover, because prospects buy resilience, not slides.

## 15. "Tell me about a time you were wrong or something failed in production."

> The thinking-mode bug: DeepSeek's reasoning tokens counted against a 300-token budget, so the model spent its entire budget thinking and returned an empty answer — the chatbot showed only sources. I'd shipped a feature (thinking mode) without checking its interaction with token limits. The fix had three parts: reserve enough budget for the final answer, retry without thinking mode if content is empty, and log the reasoning mode per query so it's visible. The lesson I carry: every new LLM feature needs a budget and an observable fallback — and my per-query logging is what made the failure diagnosable in the first place.

## 16. Rapid technical judgment (answer in 2–3 sentences each)

- **Fine-tuning vs RAG for genealogy?** RAG first: the archive changes constantly, answers must be citable, and RAG is cheaper to maintain; fine-tuning only for style/language specialization once RAG quality plateaus.
- **pgvector vs a dedicated vector store?** pgvector at this scale — one less system, transactional consistency with metadata, IVFFlat→HNSW when needed; re-evaluate past ~5M vectors or when filtering gets complex.
- **RoCE or InfiniBand for a customer?** RoCE by default — Ethernet economics and existing fabrics; InfiniBand when training large models where the fabric is the bottleneck.
- **When would you add a GPU to this system?** When either the customer demands on-prem inference or batch embedding volume makes CPU p95 unacceptable — then size by measured tokens/sec, not spec sheets.
- **How do you size a GPU cluster?** From workload benchmarks: tokens/sec at p95 for inference, model size + interconnect for training — never from the vendor's slide.
- **Why is your embedding model local?** Privacy and zero marginal cost; the abstraction layer lets a customer swap to OpenAI/Azure embeddings when they need multilingual quality and accept the data egress.
- **How do you prevent an agent loop from burning money?** I enforce a cumulative completion-token budget inside the generate/verify nodes (`AGENT_TOKEN_BUDGET`), the workflow is a fixed acyclic graph with one optional revision loop gated by human approval, and every node logs its tool calls and timings to `rag_summary.json` — all implemented in `agent_orchestration.py`.

---

## Scenario cheat-sheet (30-second story per persona)

- **CIO:** cost per query is visible and budgeted; data stays sovereign via local embeddings/on-prem inference.
- **Security lead:** RBAC, DB-trigger audit trail, prompt-injection defenses, TLS/SSO, least-privilege replication.
- **Data steward:** 30,311 records with a tamper-proof audit trail and real-time replicated backup.
- **Researcher:** cited, honest answers from the archive itself — no invented facts.
- **Developer/platform team:** instrumented pipeline, config-driven batch tuning, retry-and-fail-loudly, benchmark harness.

*Tip for round two: the interviewer is probing judgment under uncertainty. Every answer above follows one pattern — state the trade-off, give your decision, back it with a number from this project, and name what you'd measure next.*

---

## Metric Definitions (2–3 sentences each)

- **p50 and p99** — latency percentiles that summarize a response-time distribution: p50 (the median) is the value 50% of requests beat, representing the typical experience; p99 is the value 99% of requests beat, so only the worst 1% are slower — it captures the tail latency that the unluckiest users actually feel. SLAs are almost always written on p95/p99 rather than averages, because an average hides slow outliers while a single slow request can dominate a user's entire impression.
- **Reranker latency** — the time a cross-encoder model takes to score each retrieved candidate (query, chunk) pair in order to re-sort the top results for relevance. It is added latency that sits between retrieval and generation, which is why you only rerank a small candidate set (top-50, not top-500) and batch the scoring — the quality gain must justify the latency it adds to the pipeline.
- **Total response time** — the end-to-end wall-clock duration from the user submitting a query until the final answer is fully returned, i.e., embed + retrieval (+ optional rerank) + LLM generation combined. This is the number the user actually experiences — in my system it's the `duration_seconds` field logged per query in `rag_summary.json`, decomposed into per-step timings so the slowest stage can be identified.
- **Chunk hit rate** — in retrieval evaluation, the fraction of test queries for which the known-correct chunk appears within the top-k retrieved results (also called hit-rate@k); in my project, the best similarity score logged per query is its live proxy. It is the first number to measure in a golden-dataset evaluation, because if the right chunk is never retrieved, no amount of prompt engineering can produce a correct answer — retrieval recall is the ceiling for the whole pipeline.
