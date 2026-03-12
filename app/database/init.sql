-- Create pgvector extension
CREATE EXTENSION IF NOT EXISTS vector;

-- Documents table for storing genealogical documents
CREATE TABLE IF NOT EXISTS documents (
    id SERIAL PRIMARY KEY,
    title VARCHAR(255) NOT NULL,
    document_type VARCHAR(50) NOT NULL, -- 'journal' or 'application'
    file_name VARCHAR(255) NOT NULL,
    content TEXT,
    upload_date TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    uploaded_by VARCHAR(255),
    doc_metadata JSONB DEFAULT '{}'
);

-- Document chunks table for storing processed text chunks
CREATE TABLE IF NOT EXISTS document_chunks (
    id SERIAL PRIMARY KEY,
    document_id INTEGER NOT NULL REFERENCES documents(id) ON DELETE CASCADE,
    chunk_text TEXT NOT NULL,
    chunk_number INTEGER,
    embedding vector(768) -- OpenAI embedding dimension
);

-- Ancestry information table for structured genealogical data
CREATE TABLE IF NOT EXISTS ancestry_data (
    id SERIAL PRIMARY KEY,
    document_id INTEGER NOT NULL REFERENCES documents(id) ON DELETE CASCADE,
    person_name VARCHAR(255),
    birth_date VARCHAR(50),
    birth_location VARCHAR(255),
    death_date VARCHAR(50),
    death_location VARCHAR(255),
    occupation VARCHAR(255),
    relation_type VARCHAR(100),
    related_to VARCHAR(255),
    raw_text TEXT,
    embedding vector(768),
    extraction_date TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

-- Query history table
CREATE TABLE IF NOT EXISTS query_history (
    id SERIAL PRIMARY KEY,
    query_text TEXT NOT NULL,
    results JSONB,
    query_date TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    relevance_score FLOAT
);

-- Create indexes for better performance
CREATE INDEX idx_documents_type ON documents(document_type);
CREATE INDEX idx_documents_upload_date ON documents(upload_date);
CREATE INDEX idx_chunks_document_id ON document_chunks(document_id);
CREATE INDEX idx_chunks_embedding ON document_chunks USING ivfflat(embedding vector_cosine_ops) WITH (lists = 100);
CREATE INDEX idx_ancestry_document_id ON ancestry_data(document_id);
CREATE INDEX idx_ancestry_embedding ON ancestry_data USING ivfflat(embedding vector_cosine_ops) WITH (lists = 100);
CREATE INDEX idx_ancestry_person_name ON ancestry_data(person_name);
CREATE INDEX idx_ancestry_relation ON ancestry_data(relation_type);

-- Create a view for recent ancestry queries
CREATE OR REPLACE VIEW recent_ancestry_queries AS
SELECT 
    q.query_text,
    q.query_date,
    ARRAY_AGG(DISTINCT a.person_name) as mentioned_people
FROM query_history q
LEFT JOIN ancestry_data a ON q.id = q.id
GROUP BY q.query_text, q.query_date
ORDER BY q.query_date DESC
LIMIT 50;
