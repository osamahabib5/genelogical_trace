# Development Guide for Genealogy Ancestry Chatbot

## Setting Up Development Environment

### Backend Development

1. **Create Python virtual environment:**
   ```bash
   cd app/backend
   python -m venv venv
   source venv/bin/activate  # On Windows: venv\Scripts\activate
   pip install -r requirements.txt
   ```

2. **Configure the database:**
   - Create a [Supabase](https://supabase.com/) project and copy its connection string (Session pooler, port `5432`) into `.env` as `DATABASE_URL`.
   - Enable the pgvector extension and run `database/supabase_setup.sql` once in the Supabase SQL Editor.

3. **Run backend locally:**
   ```bash
   uvicorn main:app --reload
   ```

4. **Test API:**
   ```bash
   curl http://localhost:8000/health
   curl http://localhost:8000/docs  # Swagger UI
   ```

### Frontend Development

1. **Install dependencies:**
   ```bash
   cd app/frontend
   npm install
   ```

2. **Run frontend locally:**
   ```bash
   REACT_APP_API_URL=http://localhost:8000 npm start
   ```

3. **Build for production:**
   ```bash
   npm run build
   ```

## Enhanced Features to Implement

### 1. Advanced Document Processing

```python
# Add OCR support for scanned documents
from pytesseract import pytesseract
```

### 2. Improved Entity Extraction

```python
# Use spaCy for better NER
import spacy
nlp = spacy.load("en_core_web_sm")
```

### 3. Graph Database Integration

Store family relationships in Neo4j for better genealogical analysis:

```python
from neo4j import GraphDatabase
```

### 4. Batch Document Processing

Handle large document collections:

```python
# Use Celery for async task processing
from celery import Celery
```

### 5. Cache Layer

Add Redis for faster queries:

```python
from redis import Redis
```

## API Testing Examples

### Upload Document
```bash
curl -F "file=@/path/to/document.pdf" \
     -F "document_type=journal" \
     http://localhost:8000/api/documents/upload
```

### Search Genealogy
```bash
curl -X POST -H "Content-Type: application/json" \
     -d '{"query":"African American soldiers"}' \
     http://localhost:8000/api/queries/search
```

### Ask Chatbot
```bash
curl -X POST -H "Content-Type: application/json" \
     -d '{"query":"Who was John Smith?"}' \
     http://localhost:8000/api/queries/ask
```

## Database Queries for Testing

### Connect to Database

Use the **Supabase SQL Editor** (Dashboard → SQL Editor), or connect with `psql` using your connection string:

```bash
psql "postgresql://postgres.<PROJECT_REF>:<DB_PASSWORD>@aws-0-<REGION>.pooler.supabase.com:5432/postgres"
```

### Useful Queries
```sql
-- List all documents
SELECT * FROM documents;

-- Find all people by name
SELECT * FROM ancestry_data WHERE person_name ILIKE '%Smith%';

-- Vector similarity search
SELECT * FROM document_chunks 
ORDER BY embedding <=> '[vector values]'::vector 
LIMIT 5;

-- Get family relationships
SELECT person_name, relation_type, related_to 
FROM ancestry_data 
WHERE person_name ILIKE '%Smith%';
```

## Deployment Considerations

### Production Checklist

- [ ] Use a strong Supabase database password (and rotate it)
- [ ] Set strong DeepSeek/Groq/OpenAI API keys
- [ ] Update CORS origins
- [ ] Enable HTTPS
- [ ] Set up monitoring and logging
- [ ] Configure database backups (Supabase handles these by default)
- [ ] Optimize vector indexes
- [ ] Scale to multiple Uvicorn workers

### Environment Variables for Production

```env
DATABASE_URL=postgresql://postgres.<PROJECT_REF>:<DB_PASSWORD>@aws-0-<REGION>.pooler.supabase.com:5432/postgres
LLM_PROVIDER=deepseek
DEEPSEEK_API_KEY=sk-prod-key-here
DEEPSEEK_MODEL=deepseek-v4-pro
GROQ_API_KEY=your-groq-api-key
EMBEDDING_PROVIDER=ollama
OLLAMA_BASE_URL=http://localhost:11434
OLLAMA_EMBED_MODEL=nomic-embed-text
ALLOWED_ORIGINS=https://yourdomain.com
ENVIRONMENT=production
LOG_LEVEL=INFO
```

### Production Deployment (venv)

No Docker is required. To run in production:

1. Build the frontend: `cd app/frontend && npm run build` and serve `build/` with a static host (Nginx, CDN, etc.).
2. Run the backend with multiple workers behind a reverse proxy:
   ```bash
   cd app/backend
   uvicorn main:app --host 0.0.0.0 --port 8000 --workers 4
   ```
3. Keep the Supabase database connection in `DATABASE_URL` and rotate the database password regularly.

## Performance Optimization

### Database Indexing

```sql
-- Create additional indexes for common queries
CREATE INDEX idx_person_relation ON ancestry_data(person_name, relation_type);
CREATE INDEX idx_birth_location ON ancestry_data(birth_location);
```

### Query Optimization

```python
# Use batch requests for embeddings
embeddings = embedding_service.embed_texts(texts)  # More efficient than individual calls

# Use database connection pooling
engine = create_engine(DB_URL, pool_size=20, max_overflow=0)
```

## Testing

### Unit Tests Example

```python
# tests/test_document_processor.py
import pytest
from document_processor import DocumentProcessor

def test_text_chunking():
    text = "Sample text " * 100
    chunks = DocumentProcessor._chunk_text(text)
    assert len(chunks) > 0
```

### Integration Tests

```python
# tests/test_api.py
def test_document_upload(client):
    response = client.post("/api/documents/upload", data={...})
    assert response.status_code == 200
```

## Debugging

### Enable SQL Query Logging

```python
# In config.py
engine = create_engine(DB_URL, echo=True)  # Log all SQL queries
```

### Check Embeddings Quality

```python
# Verify embedding service
embedding_service = EmbeddingService()
test_embedding = embedding_service.embed_text("test")
print(len(test_embedding))  # 768 for Ollama (default), 1536 for OpenAI
```

### Monitor API Performance

```bash
# Using curl with timing
curl -w "@curl-format.txt" -o /dev/null -s http://localhost:8000/health
```

## Common Issues and Solutions

### Issue: "Vector dimension mismatch"
**Solution:** Ensure `embedding_dimension` in `config.py` matches the embedding provider (768 for Ollama, 1536 for OpenAI) and that the `vector(...)` column types in Supabase match.

### Issue: "Connection pool exhausted"
**Solution:** Increase `pool_size` in `create_engine()` call

### Issue: "Slow vector search"
**Solution:** Rebuild IVFFlat indexes or increase `lists` parameter in REINDEX command

## Contact & Support

For development questions or issues, refer to the main README.md or contact the development team.
