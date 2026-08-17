# PROJECT_STRUCTURE.md

Detailed Project Structure and Components

## Directory Overview

```
genealogy_traceline/
│
├── 📁 app/
│   ├── 📁 backend/                          # FastAPI Backend Application
│   │   ├── requirements.txt                 # Python dependencies
│   │   ├── main.py                          # FastAPI application entry point
│   │   ├── config.py                        # Configuration & settings (reads .env)
│   │   ├── database.py                      # SQLAlchemy models & setup
│   │   ├── document_processor.py            # PDF/DOCX/TXT processing
│   │   ├── embedding_service.py             # Embeddings (Ollama default / OpenAI / Azure Foundry)
│   │   ├── retrieval_service.py             # Vector similarity search
│   │   ├── llm_service.py                   # LLM response generation (DeepSeek / Groq)
│   │   ├── agent_service.py                 # Agentic document processing
│   │   ├── extract_entities.py              # Standalone entity extraction script
│   │   ├── uploads/                         # Local uploads (created at runtime)
│   │   └── 📁 routes/
│   │       ├── __init__.py
│   │       ├── documents.py                 # Document management endpoints
│   │       └── queries.py                   # Genealogical query endpoints
│   │
│   ├── 📁 frontend/                         # React Frontend Application
│   │   ├── package.json                     # Node.js dependencies
│   │   ├── 📁 public/
│   │   │   └── index.html                   # HTML entry point
│   │   └── 📁 src/
│   │       ├── index.js                     # React entry point
│   │       ├── index.css                    # Global styles
│   │       ├── App.js                       # Main app component
│   │       ├── App.css                      # App styles
│   │       └── 📁 components/
│   │           ├── Chatbot.js               # Chat interface
│   │           ├── Chatbot.css
│   │           ├── DocumentUpload.js        # File upload component
│   │           ├── DocumentUpload.css
│   │           ├── DocumentList.js          # Document management
│   │           ├── DocumentList.css
│   │           ├── FamilyTree.js            # Family tree search
│   │           └── FamilyTree.css
│   │
│   └── 📁 database/
│       ├── init.sql                         # SQL schema reference
│       └── supabase_setup.sql               # Supabase PostgreSQL setup script
│
├── 📁 sources/                              # Sample source documents
│   ├── 2022_Journal_SOFAFEA.docx
│   └── SOFAFEA APP_v_04302021.pdf
│
├── 📁 uploads/                              # User uploaded documents (created at runtime)
│
├── 📁 venv/                                 # Python virtual environment (created locally)
│
├── .env.example                             # Environment variables template
├── .env                                     # Environment variables (local, git-ignored)
├── .gitignore                               # Git ignore patterns
│
├── README.md                                # Main documentation
├── QUICK_START.md                           # 5-minute quick start guide
├── DEVELOPMENT.md                           # Development setup guide
├── PROJECT_STRUCTURE.md                     # This file
│
├── api_client.py                            # Python API client helper
└── test_agent.py                            # Agent test helper
```

## Component Details

### Backend Architecture

#### Main Components:
1. **main.py** - FastAPI application
   - Health check endpoints
   - CORS middleware configuration
   - Route registration
   - Lifespan management

2. **database.py** - SQLAlchemy models
   - Document model
   - DocumentChunk model  
   - AncestryData model
   - QueryHistory model
   - Database session management

3. **document_processor.py** - Document handling
   - PDF text extraction
   - DOCX processing
   - Text chunking (500 char chunks with 50 char overlap)
   - Genealogical entity extraction
   - Keyword pattern matching

4. **embedding_service.py** - Vector embeddings
   - OpenAI embeddings integration (default; Ollama/Azure Foundry alternates)
   - Batch embedding generation
   - Embedding dimension: 768 (Ollama, default) / 1536 (OpenAI)

5. **retrieval_service.py** - Semantic search
   - Cosine similarity search using pgvector
   - Person name search
   - Connected ancestry search
   - Document filtering

6. **llm_service.py** - Language model interaction
   - DeepSeek API integration (primary; OpenAI-compatible endpoint)
   - Groq API fallback (secondary)
   - Context-aware response generation
   - System prompt management
   - Source citation

7. **routes/documents.py** - Document endpoints
   - POST /upload - Upload document
   - GET /list - List documents
   - GET /{id} - Get details
   - DELETE /{id} - Delete document

8. **routes/queries.py** - Query endpoints
   - POST /search - Genealogical search
   - POST /ask - Chatbot query
   - GET /person/{name} - Person search
   - GET /family/{name} - Family tree
   - GET /documents/{type} - Filter documents
   - GET /history - Query history

### Frontend Architecture

#### Page Components:
1. **App.js** - Main application
   - Tab-based navigation
   - Component routing
   - Document loading

2. **Chatbot.js** - Chat interface
   - Message display
   - Real-time streaming
   - Source attribution
   - Typing indicator

3. **DocumentUpload.js** - File upload
   - Drag-and-drop support
   - File type validation
   - Size checking
   - Progress tracking

4. **DocumentList.js** - Document management
   - Document filtering
   - Type-based sorting
   - Deletion capability
   - Metadata display

5. **FamilyTree.js** - Family search
   - Person search
   - Connected records display
   - Relationship visualization
   - Family card layout

### Database Schema

#### Documents Table
- Primary genealogical content storage
- Supports journals and applications
- Full text + metadata

#### Document_Chunks Table
- Vector embeddings for semantic search
- Overlapping chunks for context
- pgvector embeddings (768 dims with nomic-embed-text)
- IVFFlat index for fast search

#### Ancestry_Data Table
- Extracted genealogical information
- Person names, dates, locations
- Family relationships
- Vector embeddings for similarity search

#### Query_History Table
- Audit trail of queries
- Result caching potential
- Relevance scoring

### API Flow

```
User Input (Web UI)
       ↓
Frontend (React)
       ↓
API Endpoint (FastAPI)
       ↓
Service Layer:
  - document_processor.py (extract text)
  - embedding_service.py (generate vectors)
  - retrieval_service.py (search similar)
  - llm_service.py (generate response)
       ↓
Database (Supabase PostgreSQL + pgvector)
       ↓
Response JSON
       ↓
Frontend Display
```

### Data Flow for Document Upload

```
1. User selects file → Frontend validates
2. POST /documents/upload → Backend receives
3. Save to disk → database record created
4. Background task:
   - Extract text (document_processor)
   - Generate embeddings (embedding_service)
   - Store chunks + vectors (database)
   - Extract entities (genealogical data)
   - Store in ancestry_data table
5. User can query immediately (or after background tasks complete)
```

### Data Flow for Query

```
1. User submits query → Frontend sends text
2. POST /queries/ask → Backend processes
3. Generate query embedding (embedding_service)
4. Vector similarity search (retrieval_service)
5. Context retrieval from database
6. LLM generates response (llm_service)
7. Save to query_history
8. Return response + sources → Display in UI
```

## Technology Stack

### Backend
- **Framework**: FastAPI 0.104
- **Server**: Uvicorn
- **Database**: Supabase (managed PostgreSQL) + pgvector
- **ORM**: SQLAlchemy
- **Embeddings**: Ollama `nomic-embed-text` (default) / OpenAI / Azure Foundry
- **Language Model**: DeepSeek (primary) / Groq (secondary)
- **Document Processing**: python-docx, pypdf, pytesseract

### Frontend
- **Library**: React 18
- **Styling**: CSS3
- **HTTP Client**: Axios
- **Markdown**: react-markdown

### Infrastructure
- **Runtime**: Python virtual environment (`venv`) + Node.js (npm) — no Docker
- **Database**: Supabase cloud PostgreSQL with the pgvector extension
- **Environment**: `.env` file (pydantic-settings)

## Local Storage

- `app/backend/uploads/` - Uploaded documents storage
- `venv/` - Python virtual environment (local, git-ignored)
- Database persistence is handled by Supabase (cloud), so no local data volume is needed.

## Network Configuration

- **Backend**: `http://localhost:8000`
- **Frontend**: `http://localhost:3000` (proxies API calls to the backend via `REACT_APP_API_URL`)
- **Supabase PostgreSQL**: remote host from `DATABASE_URL` in `.env`

## Ports

- **5432** - PostgreSQL
- **8000** - Backend API
- **3000** - Frontend React app

## Environment Variables

See `.env.example` for all available options:
- Database credentials
- OpenAI API key
- CORS settings
- Model parameters
- File upload limits

## Development vs Production

### Development
- Hot reload enabled
- Debug mode on
- localhost URLs
- Single replicas

### Production
- Optimized builds (`npm run build`)
- Logging configured
- HTTPS URLs
- Multiple Uvicorn workers behind a reverse proxy
- Database backups (handled by Supabase)

## Configuration Files

1. **config.py** - Settings management via pydantic
2. **.env** - Runtime environment variables (Supabase, DeepSeek, Groq, OpenAI)
3. **database/supabase_setup.sql** - Supabase schema, indexes, and extension setup
4. **requirements.txt** - Python dependencies
5. **package.json** - Node.js dependencies

## Security Considerations

- Database credentials in .env (git-ignored)
- CORS configuration
- File type validation
- File size limits (configurable via `max_upload_size`, default 1000MB)
- API authentication ready (not implemented)
- Parameterized SQL queries

## Performance Optimizations

- Vector indexes (IVFFlat)
- Connection pooling
- Batch embedding requests
- Chunked document processing
- Frontend code splitting ready
- CSS minification for production

## Future Enhancements

1. Authentication & authorization
2. Multi-user support
3. Graph database for relationships
4. Advanced NLP with spaCy
5. Redis caching layer
6. Celery task queue
7. Webhook integrations
8. Export functionality
9. Advanced filtering
10. Real-time collaboration

---

For more details, refer to specific documentation files:
- README.md - Complete feature guide
- DEVELOPMENT.md - Development setup
- QUICK_START.md - Getting started
