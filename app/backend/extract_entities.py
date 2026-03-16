"""
extract_entities.py

Run this script to populate the ancestry_data table by scanning all document
chunks and extracting structured person records using the LLM.

Usage:
    docker exec -it genealogy_traceline-backend-1 python3 /app/extract_entities.py
"""

import sys
import os
import json
import logging
from time import time
import requests
import re
from sqlalchemy.orm import sessionmaker
from sqlalchemy import create_engine

# Add app directory to path
sys.path.insert(0, '/app')

from config import settings
from database import Base, Document, DocumentChunk, AncestryData
from embedding_service import embedding_service

logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(message)s')
logger = logging.getLogger(__name__)

engine = create_engine(settings.database_url)
SessionLocal = sessionmaker(bind=engine)


EXTRACTION_PROMPT = """You are a genealogy data extractor. Read the following text from a historical document and extract information about any people mentioned.

For each person found, output a JSON array. Each entry should have these fields (use null if unknown):
- person_name: full name as written
- birth_date: birth year or date (string)
- birth_location: place of birth
- death_date: death year or date (string)  
- death_location: place of death
- occupation: job or role
- relation_type: their role e.g. "patriarch", "soldier", "ancestor", "spouse", "child"
- related_to: name of person they are related to if mentioned

Only include real people with at least a name. Do not include places or organizations.
Return ONLY a valid JSON array, no other text, no markdown.

Text:
{text}"""


def extract_people_from_chunk(chunk_text: str) -> list:
    """Use LLM to extract person records from a chunk of text."""
    prompt = EXTRACTION_PROMPT.format(text=chunk_text[:800])

    try:
        if settings.llm_provider == "groq":
            from groq import Groq
            client = Groq(api_key=settings.groq_api_key)
            response = client.chat.completions.create(
                model=settings.groq_model,
                messages=[{"role": "user", "content": prompt}],
                max_tokens=800,
                temperature=0.0
            )
            raw = response.choices[0].message.content.strip()

        elif settings.llm_provider == "openai":
            from openai import OpenAI
            client = OpenAI(api_key=settings.openai_api_key)
            response = client.chat.completions.create(
                model=settings.openai_model,
                messages=[{"role": "user", "content": prompt}],
                max_tokens=800,
                temperature=0.0
            )
            raw = response.choices[0].message.content.strip()

        else:
            # Ollama
            response = requests.post(
                f"{settings.ollama_base_url}/api/chat",
                json={
                    "model": settings.ollama_chat_model,
                    "messages": [{"role": "user", "content": prompt}],
                    "stream": False,
                    "options": {"temperature": 0, "num_predict": 800}
                },
                timeout=120
            )
            response.raise_for_status()
            raw = response.json()["message"]["content"].strip()

        # Clean markdown fences if present
        raw = re.sub(r'```json|```', '', raw).strip()

        # Parse JSON
        people = json.loads(raw)
        if isinstance(people, list):
            return people
        return []

    except json.JSONDecodeError as e:
        logger.debug(f"JSON parse error: {e} | raw: {raw[:100]}")
        return []
    except Exception as e:
        logger.error(f"LLM extraction error: {e}")
        return []


def run_extraction(batch_size: int = 20, max_chunks: int = None):
    """
    Scan document chunks and populate ancestry_data with extracted persons.
    
    Args:
        batch_size: Process this many chunks between DB commits
        max_chunks: Limit total chunks processed (None = all)
    """
    db = SessionLocal()

    try:
        # Get all documents
        documents = db.query(Document).all()
        logger.info(f"Found {len(documents)} documents")

        # Clear existing ancestry data
        existing = db.query(AncestryData).count()
        if existing > 0:
            logger.info(f"Clearing {existing} existing ancestry records...")
            db.query(AncestryData).delete()
            db.commit()

        total_chunks = 0
        total_persons = 0
        skipped = 0

        for doc in documents:
            logger.info(f"\nProcessing: {doc.title} (ID={doc.id})")
            chunks = db.query(DocumentChunk).filter(
                DocumentChunk.document_id == doc.id
            ).order_by(DocumentChunk.chunk_number).all()

            logger.info(f"  {len(chunks)} chunks to process")

            batch_persons = []

            for i, chunk in enumerate(chunks):
                if max_chunks and total_chunks >= max_chunks:
                    logger.info(f"Reached max_chunks limit ({max_chunks})")
                    break

                # Skip chunks that are too short to contain person info
                if len(chunk.chunk_text.strip()) < 50:
                    skipped += 1
                    continue

                # Skip chunks that are unlikely to contain person names
                # (no capitalized words = probably headers/boilerplate)
                if not re.search(r'\b[A-Z][a-z]{2,}', chunk.chunk_text):
                    skipped += 1
                    continue

                # people = extract_people_from_chunk(chunk.chunk_text)
                people = extract_people_from_chunk(chunk.chunk_text)
                import time
                time.sleep(2)  # 2s delay = max 30 requests/minute = stays within free tier
                total_chunks += 1

                for person in people:
                    name = person.get('person_name', '').strip()
                    if not name or len(name) < 3:
                        continue

                    # Get embedding for this person's context
                    try:
                        embed_text = f"{name} {person.get('birth_location', '')} {person.get('occupation', '')}"
                        embedding = embedding_service.embed_text(embed_text)
                    except Exception:
                        embedding = None

                    # record = AncestryData(
                    #     document_id=doc.id,
                    #     person_name=name,
                    #     birth_date=person.get('birth_date'),
                    #     birth_location=person.get('birth_location'),
                    #     death_date=person.get('death_date'),
                    #     death_location=person.get('death_location'),
                    #     occupation=person.get('occupation'),
                    #     relation_type=person.get('relation_type'),
                    #     related_to=person.get('related_to'),
                    #     raw_text=chunk.chunk_text[:500],
                    #     embedding=embedding
                    # )
                    record = AncestryData(
                    document_id=doc.id,
                    person_name=name[:255],
                    birth_date=(person.get('birth_date') or '')[:50],
                    birth_location=(person.get('birth_location') or '')[:255],
                    death_date=(person.get('death_date') or '')[:50],
                    death_location=(person.get('death_location') or '')[:255],
                    occupation=(person.get('occupation') or '')[:255],
                    relation_type=(person.get('relation_type') or '')[:100],
                    related_to=(person.get('related_to') or '')[:255],
                    raw_text=chunk.chunk_text[:500],
                    embedding=embedding
                )
                    batch_persons.append(record)
                    total_persons += 1

                # Commit every batch_size chunks
                if (i + 1) % batch_size == 0:
                    if batch_persons:
                        for r in batch_persons:
                            db.add(r)
                        db.commit()
                        logger.info(
                            f"  Chunk {i+1}/{len(chunks)} — "
                            f"{total_persons} persons extracted so far"
                        )
                        batch_persons = []

            # Commit remaining records for this document
            if batch_persons:
                for r in batch_persons:
                    db.add(r)
                db.commit()

            logger.info(f"  Finished {doc.title}")

        logger.info(f"""
========================================
EXTRACTION COMPLETE
========================================
Chunks processed : {total_chunks}
Chunks skipped   : {skipped}
Persons extracted: {total_persons}
========================================
        """)

        # Show sample results
        sample = db.query(AncestryData).limit(10).all()
        logger.info("Sample extracted records:")
        for r in sample:
            logger.info(
                f"  {r.person_name} | "
                f"born: {r.birth_date or '?'} | "
                f"location: {r.birth_location or '?'} | "
                f"relation: {r.relation_type or '?'} | "
                f"doc: {r.document_id}"
            )

    except Exception as e:
        logger.error(f"Extraction failed: {e}")
        db.rollback()
        raise
    finally:
        db.close()


if __name__ == "__main__":
    import argparse
    parser = argparse.ArgumentParser(description='Extract person entities from document chunks')
    parser.add_argument('--max-chunks', type=int, default=None,
                        help='Max chunks to process (default: all)')
    parser.add_argument('--batch-size', type=int, default=20,
                        help='Commit every N chunks (default: 20)')
    args = parser.parse_args()

    logger.info("Starting entity extraction...")
    logger.info(f"LLM provider: {settings.llm_provider}")
    logger.info(f"Max chunks: {args.max_chunks or 'all'}")

    run_extraction(
        batch_size=args.batch_size,
        max_chunks=args.max_chunks
    )