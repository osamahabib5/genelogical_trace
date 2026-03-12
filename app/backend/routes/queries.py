"""
API routes for genealogical queries and retrieval
"""

import logging
import time
from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session
from typing import List, Optional
from pydantic import BaseModel

from database import SessionLocal, QueryHistory
from embedding_service import embedding_service
from retrieval_service import RetrievalService
from llm_service import llm_service
from document_processor import DocumentProcessor

logger = logging.getLogger(__name__)
router = APIRouter()


class AskRequest(BaseModel):
    query: str
    include_context: bool = True


class SearchRequest(BaseModel):
    query: str
    include_documents: bool = True
    include_ancestry_data: bool = True


def get_db():
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()


@router.post("/search")
async def search_ancestry(
    request: SearchRequest,
    db: Session = Depends(get_db)
):
    query = request.query
    include_documents = request.include_documents
    include_ancestry_data = request.include_ancestry_data

    try:
        query_embedding = embedding_service.embed_text(query)
        results = {
            "query": query,
            "document_chunks": [],
            "ancestry_records": [],
            "entities": {}
        }
        if include_documents:
            results["document_chunks"] = RetrievalService.search_similar_chunks(db, query_embedding)
        if include_ancestry_data:
            results["ancestry_records"] = RetrievalService.search_ancestry_data(db, query_embedding)
        results["entities"] = DocumentProcessor.extract_genealogical_entities(query)
        try:
            db.add(QueryHistory(query_text=query, results=results))
            db.commit()
        except Exception as e:
            logger.warning(f"Could not save query history: {e}")
        return results
    except Exception as e:
        logger.error(f"Error searching ancestry: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/ask")
async def ask_chatbot(
    request: AskRequest,
    db: Session = Depends(get_db)
):
    query = request.query
    include_context = request.include_context

    try:
        start_time = time.time()
        context = []

        query_embedding = embedding_service.embed_text(query)

        if include_context:
            document_chunks = RetrievalService.search_similar_chunks(db, query_embedding, top_k=3)
            ancestry_records = RetrievalService.search_ancestry_data(db, query_embedding, top_k=3)
            context.extend(document_chunks)
            context.extend(ancestry_records)

        logger.info(f"Query: '{query}' — context sources found: {len(context)}")
        response = llm_service.generate_response(query, context)

        elapsed = round(time.time() - start_time, 2)
        logger.info(f"Query answered in {elapsed}s")

        # Enrich sources with estimated page numbers
        # chunk_number / 3 gives approximate page (assuming ~3 chunks per page)
        enriched_sources = []
        for src in context[:3]:
            enriched = dict(src)
            if 'chunk_number' in enriched:
                enriched['page_number'] = (enriched['chunk_number'] // 3) + 1
            enriched_sources.append(enriched)

        try:
            db.add(QueryHistory(
                query_text=query,
                results={"response": response, "context_count": len(context), "response_time": elapsed}
            ))
            db.commit()
        except Exception as e:
            logger.warning(f"Could not save query history: {e}")

        return {
            "query": query,
            "response": response,
            "context_sources": len(context),
            "response_time_seconds": elapsed,
            "sources": enriched_sources
        }

    except Exception as e:
        logger.error(f"Error in chatbot query: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/person/{name}")
async def search_person(name: str, db: Session = Depends(get_db)):
    try:
        records = RetrievalService.search_by_person_name(db, name)
        return {"person": name, "records_found": len(records), "records": records}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/family/{person_name}")
async def search_family_tree(person_name: str, db: Session = Depends(get_db)):
    try:
        connected_records = RetrievalService.search_connected_ancestry(db, person_name)
        return {"anchor_person": person_name, "connected_records": len(connected_records), "family_tree": connected_records}
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/documents/{doc_type}")
async def get_documents_by_type(doc_type: str, db: Session = Depends(get_db)):
    try:
        if doc_type.lower() not in ['journal', 'application']:
            raise HTTPException(status_code=400, detail="Invalid document type. Use 'journal' or 'application'")
        documents = RetrievalService.get_documents_by_type(db, doc_type.lower())
        return {"document_type": doc_type, "count": len(documents), "documents": documents}
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/history")
async def get_query_history(skip: int = 0, limit: int = 10, db: Session = Depends(get_db)):
    try:
        query_records = db.query(QueryHistory).order_by(QueryHistory.query_date.desc()).offset(skip).limit(limit).all()
        return {
            "total": len(query_records),
            "queries": [
                {"id": q.id, "query": q.query_text, "date": q.query_date.isoformat() if q.query_date else None, "relevance_score": q.relevance_score}
                for q in query_records
            ]
        }
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))
