# AI Solutions Architect — Interview Prep (Genealogy RAG Project)

Questions and sample answers built around the **Genealogy Ancestry Chatbot** project in this repo. Answers are written first-person and grounded in what was actually implemented, so they can be backed up with code, logs, and metrics.

**The project in one paragraph:** an AI-powered genealogy assistant — FastAPI backend + React frontend, Supabase (PostgreSQL + pgvector) as the vector database, DeepSeek as the primary LLM with a Groq fallback, and local Ollama `nomic-embed-text` for embeddings. It ingests historical documents (PDF/DOCX/TXT/JSON), chunks and embeds them, retrieves the most relevant passages, and answers natural-language ancestry questions with footnoted citations. It also includes an optional LangChain-based agentic document-processing pipeline, full per-step observability, and token-level cost tracking.

**Companion project — secure admin panel:** a separate FastAPI + React admin panel over the same genealogy database, deployed on **Vercel** with **Azure PostgreSQL** and **Azure Blob Storage**, featuring JWT authentication, role-based access control (admin / moderator / viewer), database-level audit triggers, and dynamic schema-driven CRUD.

---

## Domain Coverage Self-Assessment (job asks for ≥3 of: AI infrastructure, AI platforms, agentic AI, RAG, MLOps)

**The three to claim:**

- **RAG (strongest):** full pipeline built end-to-end — ingestion, chunking, embeddings, pgvector retrieval, grounded generation with citations — plus per-step instrumentation and evaluation thinking.
- **Agentic AI (real, implemented):** a LangChain tool-calling agent (`agent_service.py`) with quality-assessment, cleaning, and database-storage tools, plus a LangGraph multi-step research agent (`agent_orchestration.py`, `/api/queries/research`) — classify → retrieve → generate → verify → approve, with token budgets, citation verification, human-in-the-loop resume, and automatic fallback.
- **AI infrastructure (involvement at the serving/data tier):** local model serving on Ollama with per-request overhead analysis and batch-size benchmarking, embedding retry/fail-loudly safeguards, Azure PostgreSQL + Blob Storage, connection pooling, and logical-replication DR.

**Supporting (mention as breadth, not a core domain):**

- **AI platforms:** integrated multiple providers behind one abstraction — DeepSeek, OpenAI-compatible APIs, Ollama, and an Azure Foundry path.

**Honest gap:**

- **MLOps:** have observability/cost-tracking/benchmarking, but no model training, registry, or CI/CD for models — do not claim it as one of the three.

**Interview one-liner:** *"RAG is my strongest domain — I've built and instrumented a full pipeline end-to-end. Second is agentic AI: I implemented a tool-calling LangChain agent for document processing. Third is AI infrastructure at the application level: model serving on local infrastructure, batch-performance engineering, and cloud data infrastructure including replication and DR."*

---

## 1. "Walk me through the solution you built."

> I built a retrieval-augmented generation (RAG) platform for genealogical research. Documents are uploaded through a React UI to a FastAPI backend, which extracts text, chunks it into 1,000-character pieces with 100-character overlap, and generates 768-dimension embeddings using a local Ollama model. Chunks and embeddings go into Supabase PostgreSQL with pgvector. When a user asks a question, I embed the query, run a vector similarity search across document chunks and extracted person records, assemble the top results into a prompt, and have DeepSeek answer strictly from that context with citations. The whole pipeline is instrumented: every step is timed, token usage and dollar cost are logged per query, and I added safeguards like retry-and-fail-loudly on embedding failures, prompt-injection defenses, and a post-generation verifier that enforces the honesty rule.

---

## 2. "Explain your RAG pipeline end-to-end and the design decisions behind each stage."

> **Ingestion:** I support PDF, DOCX, TXT, and JSON. DOCX files get special handling — footnotes are extracted and linked to the chunks they belong to, which matters for a research product where citations are the core value. Chunk size (1000 chars / 100 overlap) balances context richness against retrieval precision. I also built heading-aware semantic chunking behind a `SEMANTIC_CHUNKING` flag and A/B tested it with my eval harness: precision rose 0.68 → 0.79, but recall fell 0.48 → 0.32 and rubric score 1.29 → 1.14, so I kept the fixed window — the harness proved overlap wasn't the problem.
> **Embedding:** Local Ollama `nomic-embed-text` (768-dim) keeps data private and costs zero. The abstraction layer (`EmbeddingService`) lets the same pipeline run against OpenAI or Azure Foundry if a customer needs a managed model — but the vector dimension must stay consistent with the schema.
> **Retrieval:** pgvector cosine similarity, top-8 chunks plus top-5 extracted person records, combined with a lightweight keyword filter extracted from the query (capitalized names) to nudge retrieval toward named entities.
> **Generation:** DeepSeek with thinking mode. I added a rule-based classifier that maps each query to a reasoning effort — `low` for factoid questions, `high` for comparisons, `max` for multi-step research questions — defaulting to `low`. This directly trades cost and latency against answer depth per query.
> **Guardrails:** retrieved text is wrapped in escaped `<retrieved_document>` delimiters and the system prompt treats tag contents strictly as data, so a document can't smuggle instructions into the prompt. After generation, `answer_verifier.py` runs a second LLM pass that audits the draft against the retrieved context and replaces unsupported answers with an honest refusal. Off-topic queries (greetings, "what's my name") skip retrieval entirely and return no sources.

---

## 3. "How do you evaluate whether this RAG system is working? What metrics do you track?"

> I'd evaluate in four layers:
> - **Retrieval quality:** I built `rag_evaluation.py`, which runs a 23-question golden eval set (SOFAFEA journal questions with gold answers) through the real pipeline and measures context precision/recall, context entity recall, faithfulness, answer relevancy, and rubric score vs. the gold answer — logged per question to `rag_evaluation_results.json`. The remaining piece is a CI job that fails the build when these regress.
> - **Generation quality:** faithfulness (does the answer match the retrieved context, not hallucinate), citation accuracy (do footnote references actually support the claim), and answer relevance. LLM-as-judge plus spot human review by a domain expert.
> - **Operational metrics:** per-step latency from `rag_summary.json` (embed, retrieval, LLM), end-to-end p50/p95, token usage, and USD cost per query — including peak vs. off-peak DeepSeek pricing and prompt-cache hit/miss splits.
> - **Business metrics:** user satisfaction, query answer rate, and cost per successful research session.
> This observability came from the start — I instrumented the pipeline before optimizing it, which is how I found that a single Ollama embedding call carried ~2.2 seconds of fixed overhead and that 50 sequential record-embedding calls were wasting ~2 minutes per upload.

---

## 4. "What were the most impactful performance optimizations you made, and how did you prove them?"

> - **Batched embeddings:** person records were embedded one API call at a time (50 calls); I batched them into 2 requests, and raised the document-chunk batch size from 32 to a configurable `EMBED_BATCH_SIZE` (default 128). Upload embedding time dropped from ~294s to under a minute.
> - **I built a benchmark harness** (`test_embedding_batches_size.py`) that uploads the same document with batch sizes 128/256/512/1024, captures per-step timings from the event log, and deletes each test artifact — so the trade-off curve is measured, not guessed.
> - **Failure handling:** batches retry once, then raise instead of silently storing zero-vectors — protecting the vector index from silent corruption.
> - **Small-talk short-circuit:** greetings skip embedding and retrieval entirely.
> Lesson I'd state: measure first, batch second, and make every optimization reversible via config.

---

## 5. "What improvements would you make with more time?"

> - **Hybrid retrieval:** add BM25/lexical search (e.g., pgvector + PostgreSQL full-text, or OpenSearch) and fuse scores with reciprocal rank fusion; my keyword filter is a crude approximation of this.
> - **Re-ranking:** a cross-encoder re-ranker on top-50 candidates to lift precision on hard queries.
> - **Query expansion/rewriting:** use the LLM to rewrite ambiguous queries and detect the person/event being asked about before embedding.
> - **Async ingestion:** move upload processing to a task queue (Celery/RQ or a queue in Postgres) so large uploads don't block the API worker; store progress and let the user query documents that are already indexed.
> - **Evaluation harness:** partially built — `rag_evaluation.py` runs the 23-question SOFAFEA eval set end-to-end with LLM-judged retrieval and generation metrics; what's left is the CI gate that blocks merges on metric regressions.
> - **Caching:** Redis for embeddings and frequent answers; LLM response cache with semantic dedup.
> - **Better entity extraction:** replace regex with an NER model (spaCy or an LLM extraction pass) and build an explicit family-relationship graph (Neo4j) instead of pairwise `related_to` rows.

---

## 6. "What security measures have you actually implemented?"

I can answer from two production-style systems I built:

### 6a. RBAC, authentication, and least privilege (Genealogy Admin Panel)

> - **JWT authentication** — HMAC-SHA256 signed tokens (10-hour expiry) issued after password verification against a `users_information` table, with an env-var bootstrap admin for first boot.
> - **Three roles — admin / moderator / viewer** — enforced per-endpoint by a FastAPI dependency (`require_role`): viewers are read-only and only see tables listed in `TARGET_TABLES`; moderators and admins can create/update/delete; admin-only tables (`users_information`, `linked_documents`) are hidden from everyone else.
> - **First-login password reset** — temporary credentials force a password change before anything else.
> - **Data exposure controls** — database IDs are never exposed; the frontend shows sequential IDs instead, and dynamic schema discovery only reveals tables the role is allowed to see.
> - Weaknesses I'd volunteer and fix: prototype stores passwords without hashing and trusts the role in the JWT — a hardened version would use bcrypt/argon2, re-check roles server-side per request, add login rate-limiting/lockout, and integrate an identity provider (OIDC/SSO).

### 6b. Audit logging — database triggers, not app code (Genealogy Admin Panel)

> - Every INSERT/UPDATE/DELETE on every table writes to `audit.logged_actions` via **PostgreSQL triggers** (SECURITY DEFINER), capturing who (`changed_by`), when (`changed_at`), which table and row, full old/new JSONB snapshots, and the list of columns that actually changed.
> - The authenticated username flows into the database session via `SET LOCAL audit.username`, so the trigger knows *who* made the change — and because the trigger lives at the database layer, even direct SQL edits are logged (with `changed_by = NULL`).
> - I chose triggers deliberately: application logging can fail silently or be bypassed; a trigger is tamper-proof and adds zero per-statement application overhead.
> - The audit view groups multi-table updates from a single user action into one consolidated entry.

### 6c. Cloud environment experience

> - **Serverless deployment on Vercel** (FastAPI behind an `/api` rewrite, React frontend served from the CDN, 10-second function budget) — which forced me to think about cold starts and connection reuse.
> - **Azure PostgreSQL** with a `psycopg2` threaded connection pool (min 2 / max 20) and clean-rollback-on-return discipline, so the next consumer of a pooled connection always gets a fresh transaction.
> - **Azure Blob Storage** for document attachments linked back to records.
> - Supporting cloud/data tooling I also wrote: Azure DLS2 export, free-tier cost checks, incremental loads, and a scripted backup database.

### 6d. Security in the RAG chatbot — implemented vs. roadmap

> **Implemented:**
> - **Prompt-injection defense:** every retrieved chunk is wrapped in `<retrieved_document>` tags and angle brackets in the content are HTML-escaped, so a document cannot inject its own closing tag or fake instructions; the system prompt's SECURITY RULES treat tag contents strictly as data, and a runtime assertion rejects caller-supplied prompts carrying the data-plane delimiters.
> - **Verifier-enforced honesty rule:** `answer_verifier.py` runs a second LLM pass after every `/ask` (gated by `VERIFY_ANSWERS=true`) and replaces drafts with unsupported claims — hallucination or obeyed injected instructions — with an honest refusal. Verdict, reason, tokens, and cost land in `rag_summary.json` (~2s and ~$0.0027 per query measured).
> - **Upload safety:** extension whitelist *plus* magic-byte checks (PDF `%PDF-`, DOCX `PK`, UTF-8 for TXT/JSON), empty-file rejection, size cap, UUID-prefixed filenames.
> **Roadmap:**
> - **AuthN/AuthZ:** the chatbot API is unauthenticated today — apply the same JWT + role model as the admin panel, plus Supabase RLS.
> - **Upload hardening:** sandboxed parsing and malware scanning.
> - **Secrets:** move keys from `.env` to a secret manager with rotation.
> - **Privacy:** encryption at rest, TLS in transit, retention/deletion policies, PII redaction in logs.
> - **API hardening:** rate limiting and CORS tightening (`main.py` currently allows all origins).
> - **Supply chain:** pinned dependencies, image scanning, locked-down CI/CD.

### 6e. Real-time data replication to a backup database (Azure PostgreSQL)

> - **Architecture:** the production database runs on Azure Database for PostgreSQL Flexible Server. I set up **native PostgreSQL logical replication** to continuously stream changes to a second (backup) Azure PostgreSQL instance using the publication/subscription model.
> - **On the primary:** `CREATE PUBLICATION archive_pub FOR TABLE locations, usct_connecticut, family_members, book_of_negroes` — table-level filtering so only the data that matters ships. I later added `users_information` and `audit.logged_actions` to the publication so the RBAC state and the audit trail survive in the backup too.
> - **On the backup:** `CREATE SUBSCRIPTION archive_sub CONNECTION 'host=…azure.com sslmode=require user=replicator_user' PUBLICATION archive_pub` — a dedicated least-privilege replication user, SSL enforced end-to-end.
> - **Why logical replication:** on a managed PaaS you don't get physical streaming replication as a customer; logical replication is the standard way to keep a filtered, read-capable copy continuously in sync — and it lets me replicate a *subset* of tables rather than the whole server.
> - **The gotchas I actually hit and can speak to:**
>   - Logical replication copies **row data, not schema** — the backup needed tables, primary keys, and foreign keys re-created separately, so I generated `ALTER TABLE … ADD CONSTRAINT` statements from the source catalog.
>   - **Replication slots are dangerous when unattended** — if the subscriber falls behind or dies, WAL accumulates and can fill the source disk. I monitored lag with `pg_wal_lsn_diff(pg_current_wal_lsn(), confirmed_flush_lsn)` and cleaned up a stale slot before re-syncing.
>   - Apply errors surface in `pg_stat_subscription` (worker state + `last_error`), and `ALTER SUBSCRIPTION … REFRESH PUBLICATION` re-syncs table membership after schema changes.
>   - I validated the pipe end-to-end — row-count checks between source and backup, plus a deliberate test insert to confirm changes flowed before trusting it.
> - This complements managed PITR backups and Azure Function-based incremental exports — three layers of recoverability, each covering a different failure mode.

---

## 7. "What agentic AI patterns could you add to this platform, and why?"

> - **Router agent:** classifies each query (factoid vs. comparison vs. multi-hop vs. off-topic) and routes it — I already do a rule-based version for reasoning effort; an LLM router generalizes it and can also pick retrieval strategies.
> - **Research agent (ReAct with tools):** tools = `search_documents`, `get_footnotes`, `get_person_records`, `query_history`. The agent iterates: search → read → refine query → search again, then synthesizes an answer. Good for "trace the Perkins family across three documents" questions.
> - **Citation-verifier agent:** implemented — `answer_verifier.py` audits every `/ask` answer against the retrieved context and forces an honest refusal on unsupported claims, and the LangGraph research agent's `verify` node audits footnote citations with a human-in-the-loop gate.
> - **Document-intake agent:** already partially built — a LangChain agent with tools for quality assessment, cleaning/normalization, and database storage, so unstructured uploads self-normalize into person records.
> - **Human-in-the-loop researcher copilot:** the agent proposes the answer, shows its evidence chain, and asks the researcher to confirm uncertain links before writing them into the family tree.
> I'd also implement **guardrails as tools** (allowed-topic checks) and **fallback routing** (DeepSeek → Groq on failure/rate-limit, with a circuit breaker).

### LangChain vs LangGraph — which fits this project?

- **LangChain** — a framework of building blocks for LLM applications: model wrappers, prompt templates, retrievers, vector-store integrations, and tools. Its classic `AgentExecutor` runs a single agent loop (thought → action → observation) until the task is done. *In this project: my `agent_service.py` uses exactly this — three tools (quality assessment, data cleaning, database storage) under an `AgentExecutor` for document intake.*
- **LangGraph** — a graph-based orchestration library built on top of LangChain, where agent workflows are modeled as explicit **nodes and edges** (a state machine). It adds state persistence/checkpointing, streaming, retries, branching, multi-agent coordination, and human-in-the-loop interrupts.
- **Recommendation:** LangChain is sufficient for the simple, single-agent intake job I already built — and it remains the right place to define tools and components. But the roadmap for this platform is inherently multi-step and multi-agent — router → research agent (search → read → refine) → citation verifier → optional human approval — with state carried between steps and a human in the loop before family-tree writes. That is precisely LangGraph's sweet spot: explicit control flow, resumable checkpoints, and approval interrupts. So: **keep LangChain for tools/components, adopt LangGraph to orchestrate the research and verification workflows** — also the maintained direction of the ecosystem now that `AgentExecutor` is considered legacy.

---

## 8. "How would you scale this to production?"

> - **Ingest:** async workers with backpressure; batch embeddings; keep embeddings warm (model resident in memory).
> - **Serving:** multiple Uvicorn workers behind a reverse proxy/load balancer; containerize backend and frontend; deploy on Kubernetes with Helm charts and operator-managed state.
> - **Data tier:** Supabase works for small scale; for larger workloads move pgvector to a self-managed or dedicated instance with HNSW indexes, or split into Postgres (metadata) + a purpose-built vector store (Qdrant/Milvus) — chosen by recall/latency benchmarks, not fashion.
> - **Observability:** Prometheus + Grafana for RED metrics; the existing JSONL event log feeds structured logs; trace every query with a correlation ID across embed → retrieve → LLM.
> - **High availability & DR:** database replication + point-in-time recovery; define RPO (e.g., ≤5 min) and RTO (e.g., ≤1 h) and verify with restore drills.
> - **Cost control:** keep per-query cost logging (peak/off-peak aware) and set spend budgets/alerts; consider a small model for routing/simple queries and the big model only for hard ones.

---

## 9. "Where would GPUs matter in this architecture, and which GPU options would you choose?"

> - **Embeddings:** 137M-parameter embedding models run fine on CPU for moderate throughput, but batch-heavy ingestion benefits from a single GPU (vGPU partition or MIG slice) to keep tail latency down.
> - **Inference:** we currently call a hosted LLM (DeepSeek), so no local GPU is required. For on-prem/air-gapped customers I'd size GPUs by required tokens/sec at p95: run a benchmark, then choose vGPU (flexible sharing), MIG (hard partitioning for predictable multi-tenant slices), or full GPU passthrough (max throughput, e.g., for fine-tuning).
> - **Training/fine-tuning:** only if a customer needs domain adaptation — LoRA/QLoRA on an 8xH100 fat-tree cluster with RoCE interconnect and high-speed shared storage; but I'd first exhaust prompt engineering, RAG, and few-shot approaches.
> I'd articulate this as: **start with hosted inference, plan for GPU-backed local inference only when data sovereignty or cost modeling demands it.**

---

## 10. "How do you handle document or query relevance failures — when the system answers 'not in the documents'?"

> Two separate problems: retrieval recall and answer honesty. I'd log the best similarity score per query (already done) and set a threshold below which the system either refuses to cite sources or asks a clarifying question. Off-topic/small-talk queries are detected up front and skip retrieval. For genuine misses, I'd evaluate whether it's a chunking issue (information split across chunks), an embedding miss (name spelled differently), or a query issue (ambiguous pronoun), and fix with hybrid search, query rewriting, or entity linking respectively. Honesty is a feature here — the model is instructed to say when information is absent rather than hallucinate, and a citation-verifier agent would enforce it.

---

## 11. "How would you support the Pre-Sales team on an RFP for an AI solution like this?"

> I'd start by extracting the *real* requirements from the RFP: data types and volumes, latency and availability SLAs, data-sovereignty constraints, integration points, and success criteria. Then map them to a solution skeleton: architecture diagram, component choices with justifications, sizing (compute/storage), security/compliance matrix, phased delivery plan, and assumptions/risks register. For an SOW I'd define deliverables, acceptance criteria, and operational support model. Before the proposal goes out I'd build a rapid prototype on the customer's sample data and record a demo — a working prototype beats a slide deck. Finally I'd present a technical demo walk-through: upload a real document, ask a hard question, show the citations and the cost/latency dashboard.

---

## 12. "What does your day-one observability plan look like for a RAG system?"

> Three layers: **metrics** (latency per stage, retrieval quality proxies, throughput, cost per query) in Prometheus/Grafana; **logs** with correlation IDs across stages (my `rag_summary.json` is a lightweight version of this); **traces** (OpenTelemetry) across embed → vector search → LLM call. Alerts on p95 latency, embedding failure rate, LLM error rate, and daily spend. Plus an offline evaluation job that re-runs the golden dataset weekly so quality regressions show up as dashboards, not customer complaints.

---

## 13. "How do you decide between building on a platform vs. custom components?"

> Rule of thumb: buy the undifferentiated infrastructure (hosted Postgres/pgvector, managed vector stores, LLM APIs), build the differentiated layer (the genealogy domain logic, entity extraction, citation linking, evaluation harness). In this project that meant Supabase for the database, DeepSeek/Ollama for models, and custom code for the pipeline, agent tools, and observability. I'd revisit when scale or data-sovereignty changes the economics — e.g., switching to self-hosted vLLM when inference spend crosses a threshold.

---

## 14. "How do you design for high availability and disaster recovery in this stack?"

> Define RPO/RTO with the customer first. Then: multi-AZ database with streaming replication and PITR backups (Supabase provides this), automated restore testing, stateless API containers behind load balancers so failure of one replica is invisible, and reproducible infrastructure via Terraform + CI/CD so recovery is a deploy, not a procedure. I've implemented a concrete version of this: on the admin-panel project I set up PostgreSQL logical replication from the Azure primary to a backup server (publication/subscription with replication-lag monitoring), so a second copy stays continuously in sync — my near-zero-RPO answer for data. For the vector index, HNSW builds are fast, so recreation from source documents is a viable recovery path. I'd also keep the document originals in durable object storage — the source of truth — since embeddings are derived data that can be rebuilt.

---

## 15. "What container/Kubernetes experience do you bring?"

> I'd package the backend and frontend as Docker images with explicit non-root users and health checks; use Helm for releases; manage images through a registry with signing and scanning; run on Kubernetes with HPA for the stateless API tier, separate workers for ingestion, and StatefulSets only where needed (queues/caches). Networking: ingress with TLS termination, MetalLB/load-balancer for on-prem, and network policies limiting pod-to-pod traffic. Storage: PVCs for uploads, backed by vSAN/NFS or object storage depending on the platform. I'd also wire Prometheus/Grafana dashboards and set resource requests/limits informed by the per-step timing data I already collect.

---

## Quick-hit question bank (prepare 1–2 sentence answers)

- Why 768-dim embeddings? (Ollama `nomic-embed-text` default; schema pinned to it; OpenAI 1536-dim supported via config.)
- Why cosine similarity? (Standard for embeddings; matches pgvector cosine ops index.)
- What is prompt caching and why do you log it? (DeepSeek caches repeated prompt prefixes; hit/miss tokens are billed differently, so I log both and compute cost accordingly.)
- Peak vs. off-peak pricing? (DeepSeek charges 2× during 01:00–04:00 and 06:00–10:00 UTC; my cost estimator uses the current bucket.)
- How do you prevent hallucination? (Ground in retrieved context only, force citations, honesty instruction, and enforce it with `answer_verifier.py` — a second LLM pass that replaces unsupported answers with a refusal.)
- How do you defend against prompt injection? (Retrieved text is delimited and escaped, treated strictly as data, prompts stay in code with a data-plane assertion, and the verifier catches the model if it obeys injected instructions.)
- Fixed vs semantic chunking? (A/B tested with my harness: semantic raised precision 0.68→0.79 but cut recall 0.48→0.32 and rubric 1.29→1.14 — kept fixed 1000/100 as default; the flag stays for precision-sensitive corpora.)
- Retrieval latency? (Indexed pgvector cosine search returns in hundreds of milliseconds; embedding the query dominates the pre-LLM time.)
- What happens if Ollama is down? (Embedding batches retry once then raise — upload fails loudly; queries fall back to zero-vector embedding and the LLM answers without context rather than crashing the app.)
- vGPU vs MIG vs passthrough? (Flexibility vs. partitioning vs. max throughput; chosen per workload isolation and SLA.)
- Why not a graph database now? (Pairwise relations suffice at this scale; Neo4j is on the roadmap for multi-hop family queries.)
- How do you demo this? (Upload a real journal, ask "Who was Joshua 'Old Jock' Perkins?", show the cited answer plus the logged cost/latency.)

- Why DB triggers for audit instead of app logging? (Tamper-proof, captures direct SQL changes, zero per-statement app overhead; app logging can fail silently.)
- How does the username reach the audit trigger? (`SET LOCAL audit.username` on the pooled connection per request; trigger reads it via `current_setting`.)
- Where is RBAC enforced? (Per-endpoint FastAPI dependency `require_role(admin, moderator)` — defense in depth: UI hides buttons, API returns 403, DB is the last line.)
- What roles exist and what can viewers see? (admin/moderator/viewer; viewers read-only and limited to `TARGET_TABLES`; admin-only tables hidden from others.)
- How do pooled connections stay clean? (Rollback on return to the pool so the next consumer never inherits a transaction.)
- Vercel serverless constraints and how I handled them? (10s function budget, cold starts — keep DB pool small, static assets on CDN, single `/api` rewrite.)
- Azure services used? (PostgreSQL, Blob Storage; plus DLS2 export and backup scripts.)
- How do you replicate data to a backup DB in Azure PostgreSQL? (Logical replication: publication on the primary with a filtered table list, subscription on the backup via a least-privilege user + SSL, lag monitored through the replication slot's WAL diff; schema/PKs/FKs re-created on the target since logical replication ships row data only.)
- How would you harden the admin panel? (Hash passwords, server-side role re-check, rate limiting + lockout, OIDC/SSO, audit-log retention and alerting on anomalies.)

---

*Tip: for each "what did you build" answer, have the code path ready to show — `routes/queries.py` (ask flow), `llm_service.py` (provider + classifier + delimiters), `answer_verifier.py` (honesty verifier), `agent_orchestration.py` (LangGraph), `rag_logging.py` (observability), `embedding_service.py` (batching + retry), `rag_evaluation.py` (eval harness), `test_embedding_batches_size.py` (benchmarking), and for security show the admin panel's `auth.py` (JWT + role guards), `database.py` (audit context), and the audit trigger SQL in `audit_logs_implementation.md`.*

---

## Skills Glossary (from the job description — definitions + project examples)

- **Machine learning** — systems that learn patterns from data instead of being explicitly programmed, improving with experience as they see more examples; **deep learning** is ML using many-layered **neural networks** that automatically learn hierarchical features from raw input (text, images, audio); **foundation models** are huge pre-trained models (GPT-class) trained on broad internet-scale data and adapted to many applications via prompting or fine-tuning.
  - *Project example:* my chatbot's answers come from the DeepSeek foundation model; embeddings come from a neural embedding model (`nomic-embed-text`); and I planned a neural NER model to replace regex entity extraction.
  - *General example:* a spam filter (classic ML), a CNN recognizing faces (deep learning), and GPT-4 powering dozens of products (foundation model).

- **Training** — teaching a model by iterating over data and updating its internal weights to minimize prediction error; **fine-tuning** — further training a foundation model on a smaller domain dataset to specialize it for a narrow task; **inference** — running a trained model to produce predictions, usually inside a low-latency serving pipeline; **feature engineering** — selecting, transforming, and creating the input signals a model learns from, which often matters more than the model choice itself.
  - *Project example:* I do no training — inference is via API calls to DeepSeek/Ollama; my feature engineering is the chunking strategy, footnote linking, and entity extraction that determine what the retriever and LLM see.
  - *General example:* fine-tuning Llama on legal contracts to answer contract questions, vs. just calling ChatGPT (inference), and turning raw dates into "days since birth" (feature engineering).

- **GPU vs CPU** — GPUs do massively parallel math (ideal for AI matrix operations) across thousands of small cores, while CPUs handle general/sequential work; **Spine-leaf / fat-tree** are datacenter network topologies that give equal, scalable bandwidth between GPU nodes so no single link becomes a bottleneck; **RoCE** runs RDMA over Ethernet (cheaper, compatible with existing fabrics) while **InfiniBand** is lossless with the lowest latency; **High-speed shared storage** gives every GPU one namespace to read the same dataset; **GPU-to-GPU / GPU-to-storage** bandwidth (NVLink, RDMA) often determines real training speed more than raw compute.
  - *Project example:* my embeddings run on CPU today; I measured ~2.2s of per-request overhead and benchmarked batch sizes 128–1024. For an on-prem customer I'd benchmark tokens/sec and size a GPU cluster (fat-tree + RoCE) from the measured p95.
  - *General example:* an 8×H100 training cluster uses InfiniBand for GPU-to-GPU communication and a shared NVMe-oF filesystem so all GPUs read the same dataset.

- **Scalability** — growing to handle more load without redesigning the system (scale out with more replicas, scale up with bigger hardware); **availability** — the system is up and usable when needed, often expressed as a percentage (99.9%); **fault tolerance** — it keeps working when individual components fail, through redundancy and failover; **reliability** — it behaves correctly over sustained operation; **consistency** — all nodes observe the same data state, the classic tension point in distributed systems (CAP theorem).
  - *Project example:* I'd scale my stateless FastAPI replicas horizontally behind a load balancer, rely on PostgreSQL replication for availability, and keep strict consistency for genealogy records (no eventual-consistency shortcuts on data integrity).
  - *General example:* a web shop scaled to Black Friday traffic (scalability) that keeps serving when one server dies (fault tolerance) and shows the same order status everywhere (consistency).

- **Containers** — isolated app packages built from Docker images that bundle the code and all dependencies so it runs identically anywhere; **container networking** — how containers reach each other and the outside world via bridge/overlay networks, published ports, and service discovery; **storage volumes** — persistent disks mounted into containers so data survives container restarts and recreations.
  - *Project example:* my production plan packages backend/frontend as images with non-root users and health checks, with uploads mounted on a persistent volume rather than the ephemeral container filesystem.
  - *General example:* `docker run -v pgdata:/var/lib/postgresql/data postgres` — the volume keeps the database after the container is deleted.

- **Unix / Linux / Windows** — the OS families you administer day-to-day; Linux dominates servers, containers, and AI infrastructure thanks to its stability, scripting power, and open ecosystem; Unix (macOS, BSD) shares that lineage and tooling; Windows dominates enterprise clients and Active Directory, and still hosts a large share of on-prem corporate infrastructure.
  - *Project example:* I develop on Windows (running Ollama locally), deploy to Linux-based serverless (Vercel) and Azure PaaS, and keep all tooling cross-platform in Python.
  - *General example:* SSH into Linux servers for log triage; manage Windows endpoints via AD group policy.

- **Kubernetes** — container orchestration (scheduling, scaling, self-healing, load balancing) that runs workloads across a cluster of machines; **Helm** — the package manager for K8s applications (charts) that templates, versions, and installs complete stacks; **operators** — controllers that encode operational knowledge to run stateful apps automatically (backups, failover, upgrades); **container registries** (e.g., Quay) — repositories that store, version, sign, and distribute images.
  - *Project example:* my production plan is a Helm-deployed API tier with horizontal pod autoscaling and images in Quay with signing/scanning; today Vercel's platform fills that role.
  - *General example:* the Postgres operator automatically fails over replicas; `helm install myapp ./chart` deploys a full stack.

- **Observability** — knowing a system's internal state from the outside, built on the three pillars of metrics, logs, and traces; **Prometheus** scrapes and stores time-series metrics and answers queries like p95 latency and error rates; **Grafana** visualizes and alerts on them with dashboards; **logging** records structured events for debugging, forensics, and audit trails.
  - *Project example:* my `rag_summary.json` records per-step timings, token usage, and cost per query — a lightweight observability layer I'd promote to Prometheus/Grafana with p95 alerts; the admin panel adds DB-trigger audit logs.
  - *General example:* an SRE alert "p95 latency > 2s for 5 minutes" in Grafana, backed by Prometheus counters.

- **vGPU** — slice one physical GPU into virtual shares for many VMs (flexible sharing with soft isolation); **pass-through** — dedicate a whole GPU to one VM for maximum performance; **MIG** — NVIDIA's Multi-Instance GPU partitioning a single GPU into hard-isolated slices at the hardware level; container-based GPU orchestration schedules GPUs to containers via device plugins and node labels, so pods can request fractional or whole accelerators.
  - *Project example:* my embeddings run on CPU; for an on-prem multi-tenant deployment I'd choose MIG for guaranteed slices per tenant, vGPU for bursty dev workloads, and pass-through for single high-throughput training jobs.
  - *General example:* a VMware farm shares one A100 across 7 VMs via vGPU; an inference service gets an isolated MIG slice on an H100.

- **TensorFlow / PyTorch** — the two dominant deep-learning frameworks (PyTorch: research-friendly with dynamic graphs; TensorFlow: production/serving heritage and mature deployment tooling); **RAPIDS** — NVIDIA's GPU-accelerated data-science libraries (cuDF, cuML) that mirror pandas/scikit-learn APIs while running orders of magnitude faster on GPUs.
  - *Project example:* `nomic-embed-text` runs under Ollama's PyTorch-based runtime; RAPIDS would accelerate large-scale data preparation if the pipeline moved to GPU servers.
  - *General example:* researchers prototype in PyTorch, export to ONNX for TensorFlow Serving; cuDF loads a 100GB CSV in seconds on GPU.

- **Python / Jupyter / Ansible / Terraform / Git / CI-CD** — Python is the AI lingua franca; Jupyter for interactive experimentation and prototyping; Ansible for agentless configuration automation across server fleets; Terraform for declarative infrastructure-as-code across clouds; Git for distributed version control; CI/CD pipelines automate build → test → deploy so every change is verified before release.
  - *Project example:* my entire backend and the batch-size benchmark harness are Python under Git, run via the venv; Terraform + CI/CD are my stated path for reproducible production deploys.
  - *General example:* `terraform apply` provisions a VPC, Ansible installs agents on servers, GitHub Actions builds and tests on every push.

- **Hypervisors** (e.g., ESXi) — software that runs and manages multiple VMs on one physical host, partitioning CPU/memory/storage between them, with management suites like vCenter for clusters, HA, live migration (vMotion), and centralized policy management across many hosts.
  - *Project example:* an on-prem customer's GPU estate is typically vCenter-managed ESXi hosts, where I'd carve vGPU/MIG profiles per tenant before installing the AI stack.
  - *General example:* vCenter live-migrates a running VM between ESXi hosts with zero downtime.

- **vSAN** — VMware software-defined storage that pools the local disks of multiple hosts into shared, resilient datastores (the foundation of hyperconverged infrastructure); **VMFS** — VMware's block filesystem used to format shared storage so multiple VMs can use it; **NFS** — shared file storage over the network, simple and universal for file-based workloads and cross-platform access.
  - *Project example:* for on-prem deployments I'd store uploads on NFS for simplicity or vSAN for VM-adjacent performance; in the cloud I use Azure Blob instead.
  - *General example:* a 3-node vSAN cluster gives VMs resilient local-speed storage without a SAN appliance.

- **SQL** — relational, structured, ACID databases (PostgreSQL) that enforce schemas and support complex joins and transactions; **NoSQL** — schemaless document/key-value/graph stores for scale and flexibility (MongoDB, Redis, Neo4j), trading some consistency guarantees for horizontal scalability; **caching** — fast in-memory layers that protect slower backends by serving hot data at microsecond latency.
  - *Project example:* my metadata and vectors live in PostgreSQL + pgvector; Redis is the planned cache for embeddings and frequent answers; Neo4j is the roadmap for family-relationship graphs.
  - *General example:* user profiles in MongoDB (NoSQL), session tokens in Redis (cache), orders in PostgreSQL (SQL).

- **SAN** — block storage over a dedicated network (highest IOPS, lowest latency, for databases and VMs that need raw disk semantics); **NAS** — shared file storage over Ethernet (simple, collaborative, file-level access); **Object** — massive-scale API storage (S3/Azure Blob) for unstructured data and backups, where you trade POSIX filesystem semantics for unlimited scale.
  - *Project example:* I keep document originals in Azure Blob (object), run Postgres on managed block-backed storage, and would pick SAN only for IOPS-critical on-prem databases.
  - *General example:* Oracle on FC SAN, department shares on NAS, logs and backups in S3.

- **Backup / snapshot / replication / RPO / RTO** — backups are periodic copies kept separately for recovery; snapshots are instant point-in-time copies of a volume or VM (cheap, but usually on the same storage); replication streams changes continuously to a secondary location for near-zero data loss; **RPO** is the acceptable data loss (time), **RTO** the acceptable downtime — together they dictate which of these strategies you deploy and how often you test them.
  - *Project example:* I implemented PostgreSQL logical replication from the Azure primary to a backup server (near-zero RPO) with WAL-lag monitoring, and I'd verify RTO with actual restore drills rather than trusting datasheets.
  - *General example:* nightly VM snapshots give RPO of 24h; async replication to a DR site gives RPO of seconds but needs a tested failover runbook.

- **VLAN / subnetting / DNS / L2-L3 / routing / load balancing / HA** — VLANs segment networks logically on shared physical hardware for isolation; subnetting divides IP space into routable blocks; DNS resolves names to addresses; L2 switches by MAC within a network, L3 routes by IP between networks; routing protocols (OSPF/BGP) let routers discover and share paths; load balancers (F5, NGINX, MetalLB) distribute traffic across backends; HA/failover keeps service alive when a node or link fails.
  - *Project example:* my API sits behind Vercel's load balancer with DNS-based routing; for on-prem I'd front multiple replicas with MetalLB/NGINX and segment tenants with VLANs.
  - *General example:* a BGP-routed datacenter fabric (L3), each app in its own VLAN, F5 balancing traffic with an HA pair.

- **Firewalls / NAT / VPN / RBAC / TLS / PKI** — firewalls filter traffic by policy between network zones; NAT maps private to public IPs so many devices share one public address; VPN tunnels encrypt remote links over untrusted networks; RBAC grants access by role rather than per individual, simplifying permission management; TLS encrypts data in transit and authenticates the server; PKI + certificates form the trust infrastructure that issues, signs, and revokes digital identities so parties can verify each other.
  - *Project example:* my admin panel enforces RBAC (admin/moderator/viewer) at the API layer, serves over HTTPS/TLS, and restricts origins via CORS — a working mini-stack of exactly these controls.
  - *General example:* a home router NATs private IPs to the internet; employees connect over VPN; a browser trusts a site's certificate chain back to a public CA.

---

## Glossary — the five domains, expanded

- **AI infrastructure** — the compute, storage, and networking layer that AI workloads run on: GPUs/CPUs, high-speed interconnects (RoCE/InfiniBand), shared storage, cluster topologies, and the software that manages them. *Example: I ran local model serving on Ollama, measured its per-request overhead (~2.2s) and batch-size trade-offs with a benchmark harness, added retry/fail-loudly safeguards, and built the data tier on Azure PostgreSQL + Blob with logical replication for DR.*
- **AI platforms** — end-to-end software environments (model serving, vector stores, orchestration, monitoring, model APIs) that let teams build and ship AI applications without assembling every component from scratch. *Example: I integrated DeepSeek, OpenAI-compatible APIs, Ollama, and an Azure Foundry path behind one `EmbeddingService`/`LLMService` abstraction, and used Supabase/pgvector and LangChain as platform building blocks.*
- **Agentic AI** — AI systems that don't just answer — they reason, plan, choose tools, act, and observe results iteratively toward a goal (e.g., ReAct loops), often with guardrails and human oversight. *Example: my LangChain `AgentExecutor` runs a document-intake agent with three tools (quality assessment, data cleaning, database storage), and my rule-based query classifier is an early router pattern that could become an LLM router.*
- **RAG (Retrieval-Augmented Generation)** — grounding an LLM's answer in fresh, retrieved data (e.g., document chunks from a vector database) so it answers accurately and citable instead of relying on training memory. *Example: my chatbot chunks and embeds historical documents into pgvector, retrieves top-8 chunks + top-5 person records per query, and has DeepSeek answer only from that context with footnote citations.*
- **MLOps** — the DevOps discipline for machine learning: automating and governing the model lifecycle — data pipelines, training, evaluation, deployment, monitoring, and retraining. *Example: I have the monitoring half — per-step latency, token usage, and cost logging per query, plus a benchmark harness — but no model training/registry/CI-CD for models yet, which I state honestly as the gap.*
