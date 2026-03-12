# Quick Reference Guide

## 🚀 Getting Started (5 minutes)

### 1. Start the Application
```bash
# Linux/Mac
./start.sh

# Windows
start.bat

# Or manually
docker-compose up -d
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

**Max file size: 50MB**

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

## 🐳 Docker Commands

### Start/Stop
```bash
docker-compose up -d        # Start all services
docker-compose down         # Stop all services
docker-compose down -v      # Stop and remove volumes
```

### View Logs
```bash
docker-compose logs backend   # Backend logs
docker-compose logs postgres  # Database logs
docker-compose logs frontend  # Frontend logs
docker-compose logs -f        # Follow logs in real-time
```

### Access Services
```bash
# API Documentation
http://localhost:8000/docs

# Frontend Application
http://localhost:3000

# PostgreSQL
host: localhost:5432
user: genealogy_user
password: genealogy_password
db: genealogy_db
```

---

## 🔧 Configuration

### Environment Variables (.env)
```env
# Required
OPENAI_API_KEY=sk-your-key-here

# Database
POSTGRES_USER=genealogy_user
POSTGRES_PASSWORD=genealogy_password
POSTGRES_DB=genealogy_db

# API
ALLOWED_ORIGINS=http://localhost:3000,http://localhost:8000
```

---

## 📊 Database Access

### Connect to PostgreSQL
```bash
docker-compose exec postgres psql -U genealogy_user -d genealogy_db
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
```bash
# Check Docker
docker ps

# Check logs
docker-compose logs

# Rebuild
docker-compose up -d --build
```

### API errors
1. Check `.env` has OPENAI_API_KEY set
2. Verify OpenAI account has API access
3. Check API key hasn't expired

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
- 🤖 [OpenAI API Keys](https://platform.openai.com/api-keys)
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

Check logs for detailed error messages:
```bash
docker-compose logs -f
```

Common issues are documented in [DEVELOPMENT.md](DEVELOPMENT.md#common-issues-and-solutions)

---

Last Updated: 2026-03-11
