-- ============================================================
-- Genealogy Traceline — Supabase PostgreSQL Setup Script
--
-- Run ONCE in: Supabase Dashboard → SQL Editor → New query
--
-- Prerequisite: enable pgvector
--   Dashboard → Database → Extensions → search "vector" → Enable
--   (or run the CREATE EXTENSION below; it is idempotent)
-- ============================================================

-- ------------------------------------------------------------
-- 1. Enable pgvector for semantic / similarity search
-- ------------------------------------------------------------
CREATE EXTENSION IF NOT EXISTS vector;

-- ------------------------------------------------------------
-- 2. Tables
-- ------------------------------------------------------------

-- Documents table for storing genealogical documents
CREATE TABLE IF NOT EXISTS public.documents (
    id            SERIAL PRIMARY KEY,
    title         VARCHAR(255) NOT NULL,
    document_type VARCHAR(50)  NOT NULL,          -- 'journal' or 'application'
    file_name     VARCHAR(255) NOT NULL,
    content       TEXT,
    upload_date   TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    uploaded_by   VARCHAR(255),
    doc_metadata  JSONB DEFAULT '{}'
);

-- Document chunks table for storing processed text chunks
CREATE TABLE IF NOT EXISTS public.document_chunks (
    id           SERIAL PRIMARY KEY,
    document_id  INTEGER NOT NULL REFERENCES public.documents(id) ON DELETE CASCADE,
    chunk_text   TEXT NOT NULL,
    chunk_number INTEGER,
    -- IMPORTANT: dimension must match your embedding model.
    --   Ollama nomic-embed-text       -> 768 (default)
    --   OpenAI text-embedding-3-small -> 1536
    embedding    vector(768)
);

-- Ancestry information table for structured genealogical data
CREATE TABLE IF NOT EXISTS public.ancestry_data (
    id              SERIAL PRIMARY KEY,
    document_id     INTEGER NOT NULL REFERENCES public.documents(id) ON DELETE CASCADE,
    person_name     VARCHAR(255),
    birth_date      VARCHAR(50),
    birth_location  VARCHAR(255),
    death_date      VARCHAR(50),
    death_location  VARCHAR(255),
    occupation      VARCHAR(255),
    relation_type   VARCHAR(100),
    related_to      VARCHAR(255),
    raw_text        TEXT,
    embedding       vector(768),
    extraction_date TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

-- Document footnotes table
CREATE TABLE IF NOT EXISTS public.document_footnotes (
    id              SERIAL PRIMARY KEY,
    document_id     INTEGER NOT NULL REFERENCES public.documents(id) ON DELETE CASCADE,
    chunk_id        INTEGER REFERENCES public.document_chunks(id) ON DELETE CASCADE,
    footnote_number VARCHAR(20),
    footnote_text   TEXT,
    page_number     INTEGER
);

-- Query history table
CREATE TABLE IF NOT EXISTS public.query_history (
    id              SERIAL PRIMARY KEY,
    query_text      TEXT NOT NULL,
    results         JSONB,
    query_date      TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    relevance_score FLOAT
);

-- ------------------------------------------------------------
-- 3. Indexes
-- ------------------------------------------------------------
CREATE INDEX IF NOT EXISTS idx_documents_type        ON public.documents(document_type);
CREATE INDEX IF NOT EXISTS idx_documents_upload_date ON public.documents(upload_date);
CREATE INDEX IF NOT EXISTS idx_chunks_document_id    ON public.document_chunks(document_id);
CREATE INDEX IF NOT EXISTS idx_ancestry_document_id  ON public.ancestry_data(document_id);
CREATE INDEX IF NOT EXISTS idx_ancestry_person_name  ON public.ancestry_data(person_name);
CREATE INDEX IF NOT EXISTS idx_ancestry_relation     ON public.ancestry_data(relation_type);
CREATE INDEX IF NOT EXISTS idx_footnotes_document    ON public.document_footnotes(document_id);
CREATE INDEX IF NOT EXISTS idx_footnotes_chunk       ON public.document_footnotes(chunk_id);

-- Vector similarity indexes (pgvector).
-- NOTE: IVFFlat works best once some data exists; run these after your
-- first upload, or re-run them as the data grows.
CREATE INDEX IF NOT EXISTS idx_chunks_embedding ON public.document_chunks
  USING ivfflat (embedding vector_cosine_ops) WITH (lists = 100);
CREATE INDEX IF NOT EXISTS idx_ancestry_embedding ON public.ancestry_data
  USING ivfflat (embedding vector_cosine_ops) WITH (lists = 100);

-- Alternative for larger collections: HNSW (pgvector >= 0.5 on Supabase)
-- CREATE INDEX idx_chunks_embedding ON public.document_chunks
--   USING hnsw (embedding vector_cosine_ops);

-- ------------------------------------------------------------
-- 4. Helper view
-- ------------------------------------------------------------
CREATE OR REPLACE VIEW public.recent_ancestry_queries AS
SELECT
    q.id,
    q.query_text,
    q.query_date,
    q.relevance_score
FROM public.query_history q
ORDER BY q.query_date DESC;

-- ------------------------------------------------------------
-- 5. Reset (run only if you need a clean slate)
-- ------------------------------------------------------------
-- DROP VIEW IF EXISTS public.recent_ancestry_queries CASCADE;
-- DROP TABLE IF EXISTS public.query_history CASCADE;
-- DROP TABLE IF EXISTS public.document_footnotes CASCADE;
-- DROP TABLE IF EXISTS public.ancestry_data CASCADE;
-- DROP TABLE IF EXISTS public.document_chunks CASCADE;
-- DROP TABLE IF EXISTS public.documents CASCADE;
