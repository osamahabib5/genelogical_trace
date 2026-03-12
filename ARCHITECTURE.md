# Architecture Overview

This document provides a high‑level description of the main components and data flow for the Genealogy Ancestry Chatbot application. It complements the README by focusing on how the pieces fit together rather than how to use them.

---

## 1. System Components

### 1.1 Backend API (FastAPI)
- **Location:** `app/backend/`
- **Entry point:** `main.py` - configures FastAPI, mounts routers and database dependency.
- **Routes:**
  - `routes/documents.py` handles document upload, listing, retrieval and deletion.
  - `routes/queries.py` handles search, chat (`/ask`), person/family lookups and history.
- **Services:**
  - `document_processor.py` handles ingestion, text extraction, chunking and entity extraction.
  - `embedding_service.py` wraps the OpenAI (or alternative) embeddings API.
  - `retrieval_service.py` provides vector similarity searches against pgvector tables plus specialized ancestry queries.
  - `llm_service.py` is responsible for generating chatbot responses using the selected language model.
- **Database models:**
  - Defined in `database.py` (e.g. `Document`, `Chunk`, `AncestryRecord`, `QueryHistory`).
  - Database connection via SQLAlchemy and a `SessionLocal` factory.

### 1.2 Database
- **PostgreSQL** with the **pgvector** extension for storing numerical embeddings.
- **Schema:** created by running `database/init.sql` or automatically when the backend starts.
- **Tables:** Documents, DocumentChunks, AncestryRecords, QueryHistory, etc.
- Embeddings are stored as vector columns so that similarity queries (cosine distance) can be run inside SQL.

### 1.3 AI/ML Services
- **Embeddings provider:** OpenAI (or locally hosted model) used by `embedding_service`.
- **LLM provider:** By default the system is configured to use a locally‑hosted open source model via **Ollama** (e.g. `llama3.1`), though OpenAI's Chat API can be selected instead.  The `llm_service` wraps calls to either provider.
- **Genealogical entity extraction:** A lightweight NLP routine in `DocumentProcessor` that pulls names, dates, relationships, locations, etc. from text using regex or simple heuristics.

### 1.4 Frontend (React)
- **Location:** `app/frontend/src/`
- **Main components:**
  - `Chatbot.js` – conversational UI, calls `/api/queries/ask` and displays sources.
  - `DocumentUpload.js` – file selection and upload form hitting `/api/documents/upload`.
  - `DocumentList.js` – lists uploaded documents with filters.
  - `FamilyTree.js` – fetches family connections via `/api/queries/family/{name}`.
- **Bundled** inside a Docker container; served on port 3000 in development.

### 1.5 Docker & Deployment
- **docker-compose.yml** orchestrates three services:
  1. **postgres** – database with volume for persistence.
  2. **backend** – FastAPI server built from `app/backend/Dockerfile`.
  3. **frontend** – React app built from `app/frontend/Dockerfile`.
- **Environment variables** are specified in `.env` and forwarded to both backend and frontend where needed.
- `docker-compose.dev.yml` contains overrides for local development (e.g., mounting source code volumes, enabling hot reload).

## 2. Data Flow

1. **Document ingestion:**
   - User uploads a file via frontend or curl.
   - Backend route `POST /api/documents/upload` uses `DocumentProcessor` to extract text, break it into chunks, compute embeddings, and insert both the text and vectors into the database. Genealogical entities are also extracted and stored as `AncestryRecord` entries.

2. **Semantic search and chatbot queries:**
   - When a query is received (`/search` or `/ask`), the backend obtains an embedding for the query text.
   - `RetrievalService` executes vector similarity queries on the `document_chunks` and/or ancestry tables to find top‑k matches.
   - For `/ask` endpoints, the top results are packaged as context and passed to `llm_service.generate_response()`, which composes a prompt and posts it to the LLM. The resulting response and context count are returned to the frontend.
   - All queries are optionally logged in `QueryHistory`.

3. **Family/person lookups:**
   - Requests to `/person/{name}` and `/family/{name}` trigger specialized database queries that use indexed ancestry data to locate matching records or connected family members.

4. **Frontend rendering:**
   - Results from API calls are presented in a user‑friendly manner: chat messages with sources, lists of documents, or tree visualizations built from returned records.

## 3. Extensibility Points

- **Adding new document types:** Extend `document_processor` to recognize additional file formats and update the database model.
- **Switching AI providers:** The `embedding_service` and `llm_service` are thin wrappers around provider SDKs; implementing new provider clients is straightforward.
- **Scaling:** Replace the single PostgreSQL instance with a managed cloud database; scale the backend and frontend containers in Kubernetes or another orchestrator.

## 4. Development Workflow

1. Edit code in `app/backend` or `app/frontend`.
2. Rebuild images using `docker-compose build` (or rely on bind mounts with `docker-compose up --build` in dev mode).
3. Run tests (if added) within the backend container or via frontend's npm scripts.

---

This overview should help contributors and operators understand the high‑level architecture and how the core components interact. For usage examples and detailed setup instructions, refer back to `README.md`.