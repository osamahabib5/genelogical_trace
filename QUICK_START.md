# Quick Reference Guide

## 🚀 Getting Started (5 minutes)

### 1. Start the Application
```bash
# 1. Create and activate the virtual environment
python -m venv venv
venv\Scripts\activate        # Windows
source venv/bin/activate     # macOS / Linux

# 2. Install backend dependencies
pip install -r app/backend/requirements.txt

# 3. Copy and edit .env (Supabase DATABASE_URL + DeepSeek key)
cp .env.example .env

# 4. Run database/supabase_setup.sql once in the Supabase SQL Editor

# 5. Start the backend (terminal 1)
cd app/backend
uvicorn main:app --reload

# 6. Start the frontend (terminal 2)
cd app/frontend
npm install
npm start
```

### 2. Open in Browser
Visit: **http://localhost:3000**

### 3. Upload a Document
1. Click "📤 Upload" tab
2. Select document type (Journal or Application)
3. Choose PDF/DOCX/TXT/JSON file
4. Click "Upload Document"

### 4. Chat with AI
1. Click "💬 Chat" tab
2. Ask questions about ancestry
3. Get AI-powered responses with sources

---

## 📝 Supported Document Formats

| Format | Extension | Example |
|--------|-----------|---------|
| PDF | `.pdf` | 2022_Journal_SOFAFEA.pdf |
| Word | `.docx` | application.docx |
| Text | `.txt` | data.txt |
| JSON | `.json` | structured_data.json |

**Max file size: configured via `max_upload_size` in `config.py` (default 1000MB)**

---

## 💬 Example Queries for Chatbot

### Person Search
- "Who is John Smith?"
- "What do you know about Mary Johnson?"
- "Find all records mentioning the Williams family"

### Genealogical Relationships
- "Who were John Smith's parents?"
- "Find all children of Mary Johnson"
- "Show me the family tree for the Brown family"

### Historical Information
- "What occupations are mentioned in the documents?"
- "List all birth dates between 1850 and 1900"
- "Who were soldiers in the Civil War?"

### Location-Based
- "Find all people born in Georgia"
- "Who lived in New York during the 1800s?"
- "Show migration patterns in the records"

---

## 🔍 API Endpoints Quick Reference

### Document Management
```bash
# Upload
POST /api/documents/upload

# List all
GET /api/documents/list

# Get details
GET /api/documents/{id}

# Delete
DELETE /api/documents/{id}
```

### Genealogical Search
```bash
# Search
POST /api/queries/search

# Chat
POST /api/queries/ask

# Person
GET /api/queries/person/{name}

# Family tree
GET /api/queries/family/{name}

# History
GET /api/queries/history
```

---

## �️ Local Services

### Start/Stop
```bash
# Backend (in app/backend)
uvicorn main:app --reload      # start (Ctrl+C to stop)

# Frontend (in app/frontend)
npm start                      # start (Ctrl+C to stop)
```

### View Logs
- Backend logs print to the terminal running Uvicorn.
- Frontend logs print to the terminal running `npm start`.
- Database queries can be inspected in the Supabase dashboard.

### Access Services
```bash
# API Documentation
http://localhost:8000/docs

# Frontend Application
http://localhost:3000

# Supabase PostgreSQL
Connect via the DATABASE_URL in .env, or use the Supabase SQL Editor.
```

---

## 🔧 Configuration

### Environment Variables (.env)
```env
# Supabase PostgreSQL
DATABASE_URL=postgresql://postgres.<PROJECT_REF>:<DB_PASSWORD>@aws-0-<REGION>.pooler.supabase.com:5432/postgres

# LLM: deepseek (primary) or groq (secondary)
LLM_PROVIDER=deepseek
DEEPSEEK_API_KEY=sk-your-deepseek-api-key
DEEPSEEK_MODEL=deepseek-v4-pro
GROQ_API_KEY=your-groq-api-key
GROQ_MODEL=llama-3.1-8b-instant

# Embeddings (local Ollama by default)
EMBEDDING_PROVIDER=ollama
OLLAMA_BASE_URL=http://localhost:11434
OLLAMA_EMBED_MODEL=nomic-embed-text
# OPENAI_API_KEY=sk-your-openai-api-key   # optional for 1536-dim OpenAI embeddings

# API
ALLOWED_ORIGINS=http://localhost:3000,http://localhost:8000
```

---

## 📊 Database Access

### Connect to Supabase PostgreSQL
Use the Supabase SQL Editor (Dashboard → SQL Editor), or `psql` with your connection string:

```bash
psql "postgresql://postgres.<PROJECT_REF>:<DB_PASSWORD>@aws-0-<REGION>.pooler.supabase.com:5432/postgres"
```

### Useful Queries
```sql
-- View all documents
SELECT id, title, document_type, upload_date FROM documents;

-- Find person records
SELECT * FROM ancestry_data WHERE person_name ILIKE '%Smith%';

-- Count records
SELECT COUNT(*) FROM ancestry_data;

-- Get family relationships
SELECT person_name, relation_type, related_to 
FROM ancestry_data 
WHERE person_name IS NOT NULL;
```

---

## ⚠️ Troubleshooting

### Services won't start
- Backend: check the Uvicorn terminal output for errors; verify `.env` exists with a valid `DATABASE_URL` and `DEEPSEEK_API_KEY`.
- Frontend: run `npm install` inside `app/frontend` first.
- Database: confirm the Supabase project is active and `database/supabase_setup.sql` has been run.

### API errors
1. Check `.env` has `DEEPSEEK_API_KEY` (or `GROQ_API_KEY`) set
2. Verify the model name in `DEEPSEEK_MODEL` / `GROQ_MODEL`
3. Check the API key hasn't expired and the account has credits

### Slow performance
- Wait for document processing to complete (check uploads/)
- Rebuilding indexes may help:
  ```sql
  REINDEX INDEX idx_chunks_embedding;
  ```

---

## 🔗 Useful Links

- 📚 [Full Documentation](README.md)
- 👨‍💻 [Development Guide](DEVELOPMENT.md)
- 🤖 [DeepSeek Platform](https://platform.deepseek.com/)
- ⚡ [Groq Console](https://console.groq.com/)
- 🤖 [OpenAI API Keys](https://platform.openai.com/api-keys)
- 🟢 [Supabase Documentation](https://supabase.com/docs)
- 🐘 [PostgreSQL Documentation](https://www.postgresql.org/docs/)
- 🚀 [FastAPI Documentation](https://fastapi.tiangolo.com/)
- ⚛️ [React Documentation](https://react.dev/)

---

## 📱 Mobile Access

The app is responsive! Access from any device on your network:

```
http://<your-computer-ip>:3000
```

Replace `<your-computer-ip>` with your machine's IP address (e.g., 192.168.1.100)

---

## 💡 Pro Tips

1. **Batch Upload**: Upload all documents at once, then ask questions
2. **Specific Queries**: More specific queries yield better results
3. **Person Names**: Use full names from documents for better matches
4. **Filter Documents**: Use the "Documents" tab to see what's been processed
5. **Query History**: Check "Query History" to see previous searches

---

## 🆘 Getting Help

Check the Uvicorn terminal output and Supabase dashboard for detailed error messages.

Common issues are documented in [DEVELOPMENT.md](DEVELOPMENT.md#common-issues-and-solutions)

---

Last Updated: 2026-08-16
