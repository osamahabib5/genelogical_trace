# Senior Manager, AI Solutions Architect — Salesforce Interview Prep
## Based on the Genealogy Ancestry Chatbot (SOFAFEA) Project

> **Role:** Senior Manager, AI Solutions Architect — Monetization Team  
> **Company:** Salesforce  
> **Date Prepared:** June 29, 2026  

---

## Project Context Recap

The **Genealogy Ancestry Chatbot (SOFAFEA)** is a full-stack, Dockerized AI application for tracing African American genealogical ancestry through historical documents. It features:

- **RAG Pipeline**: Document ingestion → chunking → embedding → vector storage → semantic search → LLM-generated answers with source citations
- **Multi-Provider LLM Abstraction**: Single interface across OpenAI, Groq, Ollama (local), and Azure Foundry
- **Agentic Document Processing**: LangChain-based agent that assesses data quality, cleans/normalizes genealogical records, extracts entities, and stores structured data
- **Footnote Intelligence**: Parses Word XML (`footnotes.xml` / `document.xml`) to link citations to text chunks
- **Dual-Write Database**: Local PostgreSQL + Azure PostgreSQL with synchronized writes
- **Containerized Deployment**: Docker Compose (dev), Azure Container Apps (production), Azure Container Registry
- **Frontend**: React SPA with chatbot, document upload, family tree visualization

---

## Interview Questions & Model Answers

---

### Section 1: Technical Architecture & Platform Decisions

---

#### Q1: "Walk me through how you designed the technical architecture for this agentic system. What were your key integration patterns and platform choices, and what tradeoffs did you make?"

**Model Answer:**

The architecture follows a **layered RAG + agent augmentation** pattern with clear separation of concerns:

**Layer 1 — Ingestion & Processing Pipeline:**
Documents (PDF, DOCX, TXT, JSON) enter through a FastAPI endpoint. The `DocumentProcessor` handles format-specific extraction — notably, for DOCX files I parse the raw Word XML (`word/footnotes.xml` and `word/document.xml`) to capture footnote references that standard libraries miss. This was a deliberate "build" decision because off-the-shelf DOCX parsers don't expose the `w:footnoteReference` elements needed to link citations to text.

**Layer 2 — Embedding & Vector Storage:**
I chose **pgvector** over dedicated vector databases (Pinecone, Weaviate, Milvus) for three reasons:
1. **Operational simplicity** — one less service to manage, deploy, and monitor
2. **Transactional consistency** — embeddings live in the same database as structured ancestry records, so we can do hybrid SQL + vector queries in a single transaction
3. **Cost** — no additional SaaS spend; PostgreSQL is already in the stack

The tradeoff is that pgvector's IVF-Flat indexing is less performant at massive scale (>10M vectors) compared to purpose-built vector DBs. For this use case (thousands to low millions of chunks), it's the right call.

**Layer 3 — Retrieval (Hybrid Search):**
The retrieval service uses a **two-phase approach**: first, regex-based keyword extraction identifies proper nouns (names, places) from the user query; if a keyword is found, we run a filtered vector search (`WHERE chunk_text ILIKE '%keyword%' ORDER BY embedding <=>`). If no keyword matches, we fall back to pure vector similarity. This hybrid approach significantly improves recall for genealogical name searches compared to pure semantic search.

**Layer 4 — LLM Generation with Multi-Provider Abstraction:**
The `LLMService` implements a **provider-agnostic interface** (`_call_openai`, `_call_groq`, `_call_ollama`, `_call_azure_foundry`) behind a single `generate_response()` method. This was critical because different deployment contexts need different providers — local dev uses Ollama (free, offline), production on Azure uses Azure Foundry (compliance, data residency), and Groq serves as a fast fallback.

**The key architectural insight**: I treated the LLM as a *commodity layer* — the system prompt, context assembly, and retrieval logic are the durable IP; the model provider is swappable configuration. This is exactly the kind of "platform-agnostic architecture" needed when making build-vs-buy and Agentforce-vs-custom decisions at Salesforce.

**Pattern I would carry forward to Salesforce:**
For the Monetization team's agent workflow, I'd apply the same **abstraction pattern** — design the agent orchestration layer to be platform-agnostic, with connectors to Agentforce, Slack APIs, Snowflake, and Claude, so the "connective tissue" isn't locked to any single vendor.

---

#### Q2: "This project supports four different LLM providers. When would you choose Agentforce over a custom-built agent, or vice versa? What's your framework for that decision?"

**Model Answer:**

The decision framework I use has four dimensions:

| Dimension | Choose Agentforce When... | Choose Custom When... |
|-----------|--------------------------|----------------------|
| **Time to Value** | Need working agent in days, not weeks | Have runway to build and iterate |
| **Integration Surface** | Primary integrations are Salesforce-native (CRM, Slack, Tableau) | Need deep integration with non-Salesforce systems (Snowflake, custom APIs, legacy databases) |
| **Customization Depth** | Standard RAG + tool-use patterns suffice | Need custom retrieval logic (like our footnote-linked chunking), specialized chunking, or domain-specific evaluation metrics |
| **Governance & Compliance** | Salesforce's built-in trust layer, audit trails, and Einstein Trust Layer meet requirements | Need bespoke data handling (e.g., on-premise embeddings, air-gapped deployment) |

**From this project specifically:**
I chose a custom architecture because:
1. We needed **footnote-level citation tracing** — linking each LLM response back to specific document citations — which requires custom chunk-level metadata that off-the-shelf RAG systems don't handle
2. The **hybrid keyword + vector retrieval** pattern was domain-specific (proper name extraction from genealogical queries)
3. We needed **offline/local inference** via Ollama for sensitive historical documents

**For the Salesforce Monetization team:**
I'd likely recommend a **hybrid model** — use Agentforce for standard pricing/packaging Q&A workflows (fast time-to-value, Salesforce-native), and build custom agents for specialized workflows like deal desk analytics that need Snowflake integration and custom evaluation. The key is designing the orchestration layer so both can coexist and hand off tasks.

---

### Section 2: Multi-Agent Orchestration

---

#### Q3: "This project has a LangChain-based agent for document processing. How would you evolve this into a multi-agent system, and what orchestration patterns would you use?"

**Model Answer:**

The current `GenealogyAgent` is a single agent with three tools (data cleaner, quality assessor, database storage). Evolving to multi-agent, I'd decompose into:

**Proposed Agent Architecture:**

```
┌─────────────────────────────────────────────────────────┐
│                   Orchestrator Agent                      │
│  (Routes tasks, maintains shared context, manages state) │
└──────┬──────────┬──────────┬──────────┬─────────────────┘
       │          │          │          │
       ▼          ▼          ▼          ▼
┌──────────┐ ┌──────────┐ ┌──────────┐ ┌──────────────────┐
│Ingestion │ │ Extraction│ │Validation│ │  Response Agent   │
│  Agent   │ │  Agent    │ │  Agent   │ │                   │
│          │ │           │ │          │ │ (Chatbot-facing)  │
│Parses    │ │NER +      │ │Cross-ref │ │                   │
│DOCX/PDF  │ │Relation   │ │data,     │ │ Context assembly  │
│Extracts  │ │extraction │ │flags gaps│ │ + LLM generation  │
│footnotes │ │           │ │          │ │                   │
└──────────┘ └──────────┘ └──────────┘ └──────────────────┘
```

**Orchestration Pattern: Supervisor-Worker with Shared Context Bus**

1. **Orchestrator Agent** receives the document, assesses it, and routes to specialized agents
2. **Shared Context** passes between agents via a structured state object (not raw text) — this is critical for maintaining provenance
3. **Handoff Protocol**: Each agent declares its output schema, and the orchestrator validates before passing to the next agent
4. **Human-in-the-Loop Gates**: The Validation Agent flags low-confidence extractions for human review before they enter the database

**Why this pattern over alternatives:**
- **Supervisor-Worker** (rather than fully decentralized peer-to-peer) because document processing is inherently sequential — you can't validate before extracting
- **Shared context bus** (rather than message passing) because genealogical data has complex relational dependencies that need to be visible across agents
- I specifically chose **NOT** to use a purely reactive/event-driven pattern because the workflow is deterministic (ingest → extract → validate → store), not event-driven

**For Salesforce Monetization:**
I see the same pattern applying to pricing workflows — an Orchestrator routes deals to specialized agents (discounting analysis, competitive pricing, contract review), with a shared deal context that accumulates findings.

---

#### Q4: "How do agents share context and hand off tasks in this architecture? What's your approach to context window management?"

**Model Answer:**

In the current project, context sharing is implicit — the agent's `agent_scratchpad` in LangChain accumulates intermediate steps. For a production multi-agent system, I'd implement:

**1. Structured Context Objects (not raw text):**
```python
class AgentContext:
    document_id: str
    extraction_state: Dict  # What's been extracted so far
    confidence_scores: Dict  # Per-entity confidence
    pending_validations: List  # Items needing human review
    agent_trace: List[AgentAction]  # Audit trail of which agent did what
```

This is critical because raw text context bloats the context window and loses structure. At Salesforce scale, I'd store this in a session store (Redis or similar) with the agent only receiving the relevant subset.

**2. Context Window Budgeting:**
For each agent call, I budget the context window:
- 30% system prompt (identity, rules, output schema)
- 50% relevant context (retrieved chunks, extracted entities)
- 20% conversation history + scratchpad

This is enforced programmatically — the retrieval service never returns more chunks than fit in the budgeted window.

**3. Handoff Protocol:**
When Agent A hands off to Agent B:
- Agent A writes a **structured handoff record** with: what was done, confidence, unresolved questions, and recommended next actions
- The Orchestrator validates the handoff (schema check, completeness check)
- Agent B receives the handoff + its own specialized system prompt

**From this project's lessons:**
The `DocumentProcessor.build_text_and_chunk_footnote_map()` function actually implements a primitive version of this — it builds a structured mapping (`chunk_footnote_map`) that the retrieval service later enriches with footnote data. This separation of *extraction* from *enrichment* is exactly the pattern I'd formalize into agent handoffs.

---

### Section 3: Agent Identity, Context Files & Session Design

---

#### Q5: "The job description emphasizes 'LLM context file design as a craft.' How did you design the system prompt and agent identity files in this project, and how would you make them durable across sessions?"

**Model Answer:**

This is an area where I have strong opinions. The system prompt in `llm_service.py` embodies several principles I consider essential:

**Current System Prompt Analysis:**

```
You are an expert genealogist specializing in African American ancestry research.

CRITICAL INSTRUCTIONS:
1. You MUST answer based ONLY on the context provided...
2. If the context mentions a person, family, or event — use that information...
3. Do NOT say you cannot find information if it appears anywhere...
7. Be specific — include names, dates, locations, and family relationships...
```

**What this does well:**
- **Role grounding**: "expert genealogist" frames the persona, not "helpful AI assistant"
- **Constraint-first design**: Rules 1-7 are specific behavioral constraints, not vague suggestions
- **Hallucination guardrails**: Rules 1, 3, and 6 explicitly prevent the most common RAG failure modes (ignoring context, claiming ignorance, fabricating sources)
- **Output formatting**: "Start your answer immediately without preamble" eliminates the verbose pleasantries that waste tokens

**What I'd evolve for production durability:**

**1. Layered Context Architecture:**
```
┌─────────────────────────────────────┐
│ Layer 1: Immutable Identity          │  ← Never changes
│ "You are an expert genealogist..."   │
├─────────────────────────────────────┤
│ Layer 2: Session Configuration       │  ← Set per deployment
│ Provider, model, temperature, max_tokens│
├─────────────────────────────────────┤
│ Layer 3: Workflow-Specific Rules     │  ← Varies by task
│ Citation format, response length, etc. │
├─────────────────────────────────────┤
│ Layer 4: Dynamic Context             │  ← Per-query
│ Retrieved chunks, conversation history│
└─────────────────────────────────────┘
```

**2. Identity File Design (for Salesforce agents):**

I'd structure agent identity files as version-controlled YAML:

```yaml
agent:
  id: monetization-pricing-agent
  version: 2.3.0
  owner: monetization-team
  
identity:
  role: "Senior Pricing Analyst for Salesforce"
  expertise: ["list pricing", "discounting strategy", "contract terms"]
  tone: "precise, data-driven, consultative"
  constraints:
    - "Never quote a price without citing the source SKU or Price Book entry"
    - "Flag deals below 40% discount for manager review"
    - "Reference the current fiscal quarter's promotion when applicable"

session_startup:
  - action: load_price_book
    params: {fiscal_period: current}
  - action: load_team_deal_history
    params: {lookback_days: 90}
  - action: check_active_promotions

memory:
  type: persistent_summary
  ttl_sessions: 10
  fields: [deal_size, discount_range, product_family, outcome]

skills:
  - name: competitive_pricing_lookup
    tool: snowflake_query
    description: "Query competitive pricing benchmarks from Snowflake"
  - name: discount_approval_routing
    tool: slack_workflow
    description: "Route discount approvals to the right approver via Slack"
```

**Why YAML-based identity files:**
- Version-controlled, diffable, reviewable in PRs
- Separates *who the agent is* from *how it's implemented*
- Non-engineers (product managers, domain experts) can propose changes to the identity/rules without touching code
- The `version` field enables A/B testing of identities against the same underlying tools

**3. Session Durability:**

For the genealogy project, sessions are currently ephemeral (no memory across queries). To make them durable, I'd add:

- **Session summary buffer**: After each query, the LLM generates a concise summary of what was discussed, which is prepended to the next query's context (like the `ConversationSummaryBufferMemory` pattern)
- **Persistent session store**: Redis-backed, with TTL per session
- **Cross-session identity**: The agent remembers the user's research focus (e.g., "tracing the Gowen family line") across sessions, not just within one

**This directly maps to the Salesforce role**: the job description says "author and maintain agent context files (identity files, session startup protocols, memory structures, and skill definitions) that govern how agents behave consistently across sessions, users, and evolving workflows." This is exactly the craft.

---

### Section 4: System Health, Monitoring & Reliability

---

#### Q6: "How would you approach monitoring and maintaining agent performance post-deployment? What metrics matter, and how do you detect degradation?"

**Model Answer:**

The current project has basic logging via Python's `logging` module and Docker health checks (`pg_isready`, `curl` to Ollama). For production-grade monitoring, I'd implement a multi-tier observability strategy:

**Tier 1 — System Health (Infrastructure):**
- **Heartbeat endpoint**: Already exists at `/health` — extend to check database connectivity, embedding service availability, and LLM provider reachability
- **Container health checks**: Docker health checks for postgres, ollama, backend, frontend
- **Resource monitoring**: CPU, memory, disk (especially for pgvector index size growth)

**Tier 2 — Pipeline Health (Data Flow):**
- **Ingestion success rate**: % of uploaded documents that complete processing without error
- **Embedding latency**: p50/p95/p99 time to generate embeddings per batch
- **Vector index freshness**: Time since last REINDEX on IVF-Flat indexes (they degrade as data grows)
- **Footnote extraction coverage**: % of footnotes in DOCX files successfully linked to chunks

**Tier 3 — Agent Quality (Output):**
This is the hardest and most important tier. For the genealogy chatbot:

| Metric | How to Measure | Target |
|--------|---------------|--------|
| **Context Relevance** | Cosine similarity between query embedding and top retrieved chunk embeddings | >0.75 for top-3 |
| **Citation Accuracy** | Manual review: does the LLM's claim actually appear in the cited source? | >90% |
| **Hallucination Rate** | % of responses containing names/dates/facts NOT in any retrieved context | <5% |
| **Answer Completeness** | Does the response use ALL available relevant context? | >80% context utilization |
| **Response Time** | p95 latency from query to response | <30s (already tracked in `response_time_seconds`) |

**Degradation Detection:**

1. **Drift monitoring on embeddings**: Periodically re-embed a fixed set of "golden queries" and check if the same chunks are retrieved. If retrieval changes significantly, the embedding model or index may have degraded.

2. **LLM output regression testing**: Maintain a suite of 50+ test queries with expected responses. Run nightly against the current model/provider configuration. Flag semantic drift (measured via embedding similarity of new vs. expected response).

3. **User feedback loop**: The chatbot UI should include thumbs-up/down on each response. Low-rated responses get flagged for manual review and become new test cases.

**For the Salesforce Monetization context:**
I'd add business-specific metrics:
- **Deal velocity impact**: Are sellers closing deals faster with agent assistance?
- **Pricing accuracy**: Are agent-recommended prices within acceptable bands of final approved prices?
- **Escalation rate**: How often does the agent need to escalate to a human?

---

#### Q7: "The job requires self-sufficiency — owning the full loop from design to production. Walk me through your deployment and debugging workflow for this project."

**Model Answer:**

**Deployment Architecture:**

The project has two deployment paths:

1. **Local/Dev**: `docker-compose.yml` — PostgreSQL + Ollama + Backend + Frontend, all on one machine
2. **Azure Production**: `docker-compose.azure.yml` — PostgreSQL (Azure DB) + Backend (Azure Container Apps) + Frontend (Azure Container Apps), images from Azure Container Registry

**CI/CD Pipeline (What I'd add for production):**

```
Git Push → GitHub Actions
  ├── Build & Test (backend unit tests, frontend lint)
  ├── Build Docker Images (backend, frontend)
  ├── Push to Azure Container Registry
  ├── Deploy to Staging (Container Apps staging slot)
  ├── Smoke Tests (hit /health, /api/queries/ask with test query)
  └── Swap Staging → Production
```

**Deployment Commands (from the actual deploy scripts):**
```bash
# Build & push
docker build -t genealogyacr.azurecr.io/genealogy-backend:latest .
docker push genealogyacr.azurecr.io/genealogy-backend:latest

# Deploy
az containerapp update --name genealogy-backend --resource-group genealogy-rg \
  --image genealogyacr.azurecr.io/genealogy-backend:latest
```

**Debugging Workflow (Real examples from this project):**

1. **"LLM returns empty or nonsense responses"**:
   - Check: `docker-compose logs backend | grep "LLM service"`
   - Verify provider config: Is `LLM_PROVIDER` set correctly in `.env`?
   - Check context assembly: Is `_build_context_string` producing non-empty context?
   - Test provider directly: `curl http://localhost:11434/api/chat` for Ollama

2. **"Embeddings dimension mismatch"**:
   - The `config.py` constructor dynamically sets `embedding_dimension` based on provider (1536 for OpenAI/Azure Foundry, 768 for Groq/Ollama)
   - The `init.sql` hardcodes `vector(1536)` — this creates a mismatch when using Ollama
   - Fix: Either make init.sql dynamic or always create `vector(1536)` and pad smaller embeddings

3. **"Footnotes not linked to chunks"**:
   - Check: Are we using the XML parser (`extract_paragraphs_with_footnote_refs`) or falling back?
   - Verify: `lxml` is installed in the Docker image
   - Debug: Check `chunk_footnote_map` output in logs

**Self-Sufficiency Pattern:**
The key to self-sufficiency is **observability built into the code from day one**. Every service logs its provider, batch sizes, response times, and errors at the right level. The `docker-compose logs` command becomes your first debugging tool, not an afterthought.

---

### Section 5: Evaluation, Testing & Quality Standards

---

#### Q8: "How do you set standards for how agents are built, tested, and evaluated? What does 'quality' mean for an AI agent system?"

**Model Answer:**

I think about agent quality across four pillars:

**Pillar 1 — Functional Correctness ("Does it work?")**

| Test Type | What It Validates | Example from This Project |
|-----------|-------------------|--------------------------|
| Unit tests | Individual components | `DocumentProcessor._chunk_text` produces correct overlap |
| Integration tests | Service interactions | Upload a known PDF → verify chunks + embeddings in DB |
| Contract tests | API schema compliance | POST `/api/queries/ask` response matches `AskResponse` schema |
| E2E tests | Full user journeys | Upload document → ask question → verify citation in response |

**Pillar 2 — Retrieval Quality ("Does it find the right information?")**

I use retrieval-specific metrics:
- **Recall@K**: For a set of test queries with known relevant chunks, what % of relevant chunks appear in top-K results?
- **MRR (Mean Reciprocal Rank)**: How high is the first relevant chunk ranked?
- **Keyword filter effectiveness**: What % of name queries benefit from the keyword pre-filter?

**Pillar 3 — Generation Quality ("Is the answer correct and well-formed?")**

- **Faithfulness**: Is every factual claim in the response supported by retrieved context? (This is the anti-hallucination metric)
- **Citation precision**: Are footnote references correctly mapped to claims?
- **Completeness**: Does the response cover all relevant information in the context?

**Pillar 4 — Operational Quality ("Is it reliable in production?")**

- **Availability**: Uptime % of the `/health` endpoint
- **Latency**: p95 response time under load
- **Error rate**: % of queries returning 5xx errors
- **Cost per query**: Tokens consumed × provider pricing

**Evaluation Infrastructure I'd build at Salesforce:**

```python
# Example evaluation harness (conceptual)
class AgentEvaluator:
    def __init__(self, test_suite: List[TestCase]):
        self.test_suite = test_suite
    
    def evaluate_retrieval(self, agent, test_case) -> RetrievalMetrics:
        """Measure recall, precision, MRR"""
        ...
    
    def evaluate_generation(self, agent, test_case) -> GenerationMetrics:
        """Use LLM-as-judge to score faithfulness, completeness"""
        ...
    
    def regression_test(self, agent_v1, agent_v2) -> RegressionReport:
        """Flag cases where v2 performs worse than v1"""
        ...
```

**Quality Gates for Deployment:**
- Canary deployment: 5% of traffic → monitor for 1 hour → 25% → 100%
- Automated rollback if error rate >2% or p95 latency >2x baseline
- Weekly manual review of 20 random responses by a domain expert

---

### Section 6: "Connective Tissue" — Wiring Systems Together

---

#### Q9: "The role is about the 'connective tissue' — how agents, APIs, workflows, and enterprise platforms are wired together. How does this project demonstrate that capability, and how would you apply it at Salesforce?"

**Model Answer:**

This project demonstrates connective tissue design in several concrete ways:

**1. Multi-Provider LLM Abstraction (The Adapter Pattern at Scale):**

The `LLMService` and `EmbeddingService` are real examples of wiring heterogeneous systems together through a unified interface. Every provider (OpenAI, Groq, Ollama, Azure Foundry) has a different SDK, different auth pattern, different error handling — but the rest of the codebase doesn't care. This is exactly the pattern needed to wire Agentforce, Claude, Snowflake, and Slack together.

**2. Dual-Write Database Pattern:**

The `routes/documents.py` and `routes/queries.py` implement dual writes to local PostgreSQL AND Azure PostgreSQL. This is connective tissue between on-premise and cloud. The pattern:

```python
# Local write
db.add(document)
db.flush()

# Azure write (if configured)
if azure_db:
    azure_document = Document(...)
    azure_db.add(azure_document)
    azure_db.flush()
```

At Salesforce, this same pattern would apply to writing deal data to both Salesforce CRM and Snowflake for analytics.

**3. Docker Compose as Integration Manifest:**

The `docker-compose.yml` is more than deployment config — it's a **declarative integration manifest** that defines:
- Which services exist (postgres, ollama, backend, frontend)
- How they discover each other (DNS via Docker network: `http://ollama:11434`)
- Dependencies and startup order (`depends_on` with health checks)
- Shared volumes and networks

At Salesforce, the equivalent would be defining how the Monetization agent connects to Slack (for user interaction), Snowflake (for data), Agentforce (for orchestration), and CRM (for deal context) — all declared in a single integration spec.

**4. Applying This at Salesforce — The "Connective Tissue" Architecture:**

```
┌────────────────────────────────────────────────────────────┐
│                   Monetization Agent Layer                  │
│  ┌──────────┐  ┌──────────┐  ┌──────────┐  ┌────────────┐ │
│  │ Pricing  │  │Discounting│  │Contract  │  │ Competitive│ │
│  │  Agent   │  │  Agent    │  │  Agent   │  │Intel Agent │ │
│  └────┬─────┘  └────┬─────┘  └────┬─────┘  └─────┬──────┘ │
│       │             │             │               │         │
├───────┴─────────────┴─────────────┴───────────────┴─────────┤
│              Integration Fabric (Connective Tissue)          │
│  ┌──────────┐  ┌──────────┐  ┌──────────┐  ┌────────────┐  │
│  │Agentforce│  │  Slack   │  │Snowflake │  │   Claude    │  │
│  │ Adapter  │  │ Adapter  │  │ Adapter  │  │  Adapter    │  │
│  └────┬─────┘  └────┬─────┘  └────┬─────┘  └─────┬──────┘  │
│       │             │             │               │         │
├───────┴─────────────┴─────────────┴───────────────┴─────────┤
│                   Data & Platform Layer                       │
│  ┌──────────┐  ┌──────────┐  ┌──────────┐  ┌────────────┐  │
│  │   CRM    │  │  Slack   │  │Snowflake │  │   Claude    │  │
│  │(Pricing) │  │(Messages)│  │(Analytics)│  │  (Models)  │  │
│  └──────────┘  └──────────┘  └──────────┘  └────────────┘  │
└─────────────────────────────────────────────────────────────┘
```

Each "Adapter" is a thin wrapper (like our `LLMService` provider methods) that normalizes the interface. The agents never know which platform they're talking to.

---

### Section 7: Domain Fluency — Monetization & Business Translation

---

#### Q10: "How do you translate between business strategy and engineering? Give me an example from this project where you had to think in both systems and business terms."

**Model Answer:**

This project sits at exactly that intersection. Here are three examples:

**Example 1: Footnote Extraction — A Business Requirement Disguised as a Technical Problem**

The **business need**: Genealogists using this tool need to cite original sources in their research. Without citations, the AI responses are interesting but not *usable* for serious genealogy work.

The **technical challenge**: Standard DOCX libraries (`python-docx`) don't expose footnote references because they're stored in separate XML files inside the ZIP archive. Most document processing pipelines silently drop footnotes.

The **solution at the intersection**: I built a custom XML parser (`extract_paragraphs_with_footnote_refs`) that reads `word/document.xml` to find `w:footnoteReference` elements and `word/footnotes.xml` to resolve the citation text. Then I built a chunk-to-footnote mapping so that when the chatbot cites a source, it can say "per [footnote 6], Accomack County records show..." — making the AI output *citation-grade* rather than *conversational*.

**Business translation**: The feature went from "chatbot answers ancestry questions" (vague) to "chatbot provides citation-backed genealogical evidence" (specific, valuable, differentiable).

**Example 2: Multi-Provider LLM — A Business Continuity Decision**

The **business need**: The organization using this tool has varying deployment contexts — some users need offline/local processing (privacy), others want cloud speed.

The **technical decision**: Instead of picking one provider, I built a provider abstraction that lets you switch between Ollama (local/free), Groq (fast/cheap), OpenAI (high quality), and Azure Foundry (enterprise compliance) by changing one environment variable.

The **business framing**: This isn't over-engineering — it's **vendor risk mitigation**. If OpenAI changes pricing, we switch to Groq. If internet is unavailable, Ollama works offline. The architecture ensures the tool is never held hostage by a single provider.

**Example 3: Agentic Processing — Automating What Humans Shouldn't Do**

The **business need**: Manually extracting names, dates, and relationships from hundreds of pages of historical documents is tedious, error-prone, and doesn't scale.

The **technical implementation**: The `GenealogyAgent` automates the pipeline: quality assessment → data cleaning → entity extraction → database storage. It uses LangChain tools to give the LLM structured actions it can take.

The **business translation**: This turns a *document library* into a *queryable knowledge base*. The value prop shifts from "store your documents" to "interrogate your history."

**At Salesforce, this translation skill applies directly**: When a seller asks "what discount should I offer on this deal?", the technical answer involves RAG retrieval, Snowflake queries, and LLM generation — but the *business answer* is "help sellers close deals faster with data-driven pricing recommendations." I speak both languages.

---

### Section 8: System Design & Scaling

---

#### Q11: "This project uses pgvector for vector storage. At Salesforce scale, how would you evolve this architecture? What changes when you go from hundreds of documents to millions?"

**Model Answer:**

The current architecture works well at the "thousands of documents" scale, but enterprise scale requires several evolutions:

**1. Vector Index Evolution:**

Current: IVF-Flat with `lists = 100`. At scale:
- **HNSW indexes** replace IVF-Flat for better recall-at-speed tradeoff
- **Partitioning** by document collection/tenant so queries only scan relevant partitions
- **Quantization** (PQ or scalar) to reduce index memory footprint

**2. Embedding Pipeline:**

Current: Synchronous embedding in the upload request path. At scale:
- **Async queue** (Celery/Redis or Azure Service Bus): Upload returns immediately, processing happens async
- **Batch embedding**: Already implemented (`embed_texts` with batch_size=32), but would scale to larger batches with a dedicated embedding worker pool
- **Embedding cache**: If the same text is embedded multiple times (common with overlapping chunks), cache the embedding

**3. Retrieval Optimization:**

Current: Single-stage vector search. At scale:
- **Two-stage retrieval**: Fast coarse retrieval (sparse/BM25) → fine re-ranking (cross-encoder)
- **Query routing**: Different retrieval strategies for different query types (person search vs. date search vs. location search)
- **Result caching**: Common queries (popular ancestors) get cached responses

**4. Multi-Tenancy:**

Current: Single database, no tenant isolation. At Salesforce scale:
- **Row-level security** or schema-per-tenant
- **Embedding namespace separation**: Each org's embeddings isolated
- **Quota management**: Per-tenant rate limiting, storage quotas

**5. LLM Serving:**

Current: Single provider with timeout-based error handling. At scale:
- **Load-balanced provider pool**: Multiple provider instances with circuit breakers
- **Provider routing**: Route simple queries to fast/cheap models, complex queries to powerful models
- **Response streaming**: Already in mind (the Chatbot component has a typing indicator, but the backend doesn't stream yet)

**Scaling Strategy Timeline:**

| Phase | Scale | Architecture Change |
|-------|-------|-------------------|
| Current | <1K documents | Single-node pgvector, sync processing |
| Phase 1 | 1K-100K | Async ingestion, HNSW indexes, Redis cache |
| Phase 2 | 100K-1M | Read replicas, two-stage retrieval, embedding cache |
| Phase 3 | 1M+ | Sharded pgvector, dedicated embedding service, CDN for frontend |

---

### Section 8: Additional Behavioral Questions

---

#### Q12: "Tell me about a time you had to debug a production issue in an AI system without outside engineering help. What was your process?"

**Model Answer:**

While building this project, I encountered a subtle bug that exemplifies the kind of self-sufficient debugging this role requires:

**The Symptom**: When using Ollama as the LLM provider with the `nomic-embed-text` embedding model, vector similarity searches returned zero results even though documents had been uploaded successfully.

**Debugging Process:**

1. **Check the obvious**: Were embeddings actually generated? → Yes, the `embedding_service` logs showed successful generation
2. **Check dimensions**: The `init.sql` created `vector(1536)` columns, but `nomic-embed-text` produces 768-dimensional embeddings. The database was silently failing to store them.
3. **Root cause**: `config.py` dynamically sets `embedding_dimension = 768` for non-OpenAI providers, but the SQL schema was hardcoded to 1536.
4. **Fix**: Modified the `Settings.__init__` to set dimensions based on provider, and added dimension validation before storing embeddings.

**What this taught me:**
- **Schema-config coupling** is a common failure point in AI systems where model outputs change dimensions
- **Silent failures are worse than loud ones** — the database should have rejected dimension mismatches, not quietly stored nulls
- **Always validate embedding dimensions** against the database schema at startup, not just at write time

**For Salesforce**: This same pattern applies to agent context files — if an agent's expected input schema drifts from what the upstream system provides, the failure should be caught at the integration boundary, not silently produce wrong answers.

---

#### Q13: "How do you approach the 'build vs. buy' decision for AI platform components? Give a specific example from this project."

**Model Answer:**

**Decision: Build custom DOCX footnote extraction vs. use an existing library**

**"Buy" options evaluated:**
- `python-docx` footnotes API: Doesn't exist — footnotes are not exposed
- `mammoth` DOCX-to-HTML converter: Converts footnotes to endnotes, loses positional context
- Commercial document AI APIs (AWS Textract, Azure Document Intelligence): Handle PDFs well but don't parse DOCX footnote *references* with positional accuracy

**"Build" decision factors:**

| Factor | Score (1-5) | Reasoning |
|--------|-------------|-----------|
| Uniqueness of need | 5 | No off-the-shelf solution does footnote-to-chunk linking |
| Build complexity | 3 | DOCX is ZIP+XML — parsable with lxml, about 100 lines of code |
| Maintenance burden | 2 | The Word XML schema is stable; won't need frequent updates |
| Strategic value | 4 | Citation-grade output is the core differentiator of the product |

**Score: Build (14/20)**

This is exactly the kind of decision the Salesforce role requires — when the integration point between systems (in this case, between document structure and retrieval context) is unique enough that no off-the-shelf connector exists, you build it. The key is knowing *when* that threshold is crossed.

**For Salesforce Monetization**: The equivalent decision would be "use Agentforce's built-in RAG vs. build a custom retrieval pipeline that queries both Snowflake and CRM." The answer depends on how unique the data integration pattern is.

---

## Quick Reference: Project-to-Role Skill Mapping

| Salesforce Job Requirement | How This Project Demonstrates It |
|---------------------------|----------------------------------|
| Define technical architecture for agent portfolio | Multi-provider LLM abstraction, layered RAG architecture |
| Multi-agent orchestration patterns | LangChain agent with supervisor-worker pattern, shared context design |
| "Connective tissue" between agents, APIs, platforms | Provider adapters, dual-write DB, Docker integration manifest |
| Standards for building, testing, evaluating agents | Retrieval metrics (recall@K), generation quality metrics, regression testing |
| Agent performance monitoring & iteration | Response time tracking, error logging, degradataion detection framework |
| Platform calls (build vs. buy) | Build-vs-buy framework applied to footnote extraction, vector DB choice |
| Agent identity & context file design | Layered context architecture, YAML-based identity files, session memory design |
| System health & reliability | Docker health checks, multi-tier monitoring, graceful degradation |
| Deployment lifecycle ownership | Docker Compose → Azure Container Apps, CI/CD pipeline design |
| Python proficiency & Linux comfort | Full FastAPI backend, Docker, bash deployment scripts |
| Translation between business & engineering | Feature framing (citation-grade output, vendor risk mitigation, automation ROI) |

---

*This document was prepared by thoroughly analyzing the full codebase of the genealogy_traceline project, including all backend services, frontend components, database schema, Docker configuration, and deployment scripts.*
