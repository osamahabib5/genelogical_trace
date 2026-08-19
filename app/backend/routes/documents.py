"""
API routes for document management
"""

import os
import json
import logging
from pathlib import Path
from fastapi import APIRouter, UploadFile, File, Depends, HTTPException
from sqlalchemy.orm import Session
from typing import Any, Dict, Optional
import uuid

from database import SessionLocal, Document, DocumentChunk, AncestryData, DocumentFootnote, AzureSessionLocal
from document_processor import DocumentProcessor
from embedding_service import embedding_service
from config import settings
from rag_logging import rag_event_context, log_rag_event, step_timer

logger = logging.getLogger(__name__)
router = APIRouter()


def get_db():
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()


def _store_chunks_and_footnotes(db, document_id, chunks, embeddings, chunk_footnote_map):
    """Store embedded chunks and link extracted footnotes to their chunks."""
    chunk_objs = []
    for i, (chunk, emb) in enumerate(zip(chunks, embeddings)):
        chunk_obj = DocumentChunk(
            document_id=document_id,
            chunk_text=chunk,
            chunk_number=i,
            embedding=emb
        )
        db.add(chunk_obj)
        chunk_objs.append(chunk_obj)
    db.flush()

    fn_count = 0
    for chunk_idx, fn_list in (chunk_footnote_map or {}).items():
        if chunk_idx < len(chunk_objs):
            for fn in fn_list:
                db.add(DocumentFootnote(
                    document_id=document_id,
                    chunk_id=chunk_objs[chunk_idx].id,
                    footnote_number=str(fn.get("number", "")),
                    footnote_text=(fn.get("text") or "")[:2000]
                ))
                fn_count += 1

    logger.info(f"[direct:{document_id}] stored {len(chunk_objs)} chunks and {fn_count} footnotes")


async def _process_direct(
    file_path: str,
    document: Document,
    db: Session,
    event: Optional[Dict[str, Any]] = None,
):
    """
    Deterministic pipeline: extract -> chunk -> embed (Ollama) -> store ->
    regex entity extraction. No LLM calls.

    If `event` is provided (a rag_event_context record), each phase is timed
    with step_timer() so per-step durations end up in the upload log.
    """
    document_id = document.id
    event = event or {"steps_taken": []}

    logger.info(f"[direct:{document_id}] Step 1/6: extracting text from {Path(file_path).name}")
    with step_timer(event, "extract text"):
        full_text, chunks = DocumentProcessor.process_document(file_path)

    chunk_footnote_map = {}
    if file_path.lower().endswith(".docx"):
        try:
            with step_timer(event, "extract footnotes (docx)"):
                footnotes = DocumentProcessor.extract_footnotes_from_docx(file_path)
                clean_text, chunks, chunk_footnote_map = DocumentProcessor.build_text_and_chunk_footnote_map(
                    file_path, footnotes
                )
            if clean_text:
                full_text = clean_text
            logger.info(f"[direct:{document_id}] extracted {len(footnotes)} footnotes from DOCX")
        except Exception as exc:
            logger.warning(f"[direct:{document_id}] footnote extraction skipped: {exc}")

    logger.info(f"[direct:{document_id}] Step 2/6: text={len(full_text)} chars, {len(chunks)} chunks")

    logger.info(f"[direct:{document_id}] Step 3/6: embedding {len(chunks)} chunks via '{settings.embedding_provider}'")
    with step_timer(event, "embed chunks"):
        # Larger batches reduce the number of HTTP requests to Ollama,
        # where each request carries ~2s of fixed overhead on this machine.
        # Tune via EMBED_BATCH_SIZE in .env.
        embeddings = embedding_service.embed_texts(chunks, batch_size=settings.embed_batch_size)

    logger.info(f"[direct:{document_id}] Step 4/6: storing chunks + footnotes")
    with step_timer(event, "store chunks + footnotes"):
        _store_chunks_and_footnotes(db, document_id, chunks, embeddings, chunk_footnote_map)

    logger.info(f"[direct:{document_id}] Step 5/6: regex entity extraction")
    with step_timer(event, "extract person records"):
        records = DocumentProcessor.extract_person_records(full_text)
    logger.info(f"[direct:{document_id}] extracted {len(records)} person records")

    stored = 0
    with step_timer(event, "embed + store ancestry records"):
        person_records = records[:50]
        raw_texts = [json.dumps(rec) for rec in person_records]
        # Embed all person records in one batched request instead of one
        # HTTP call per record (each call costs ~2s of fixed overhead).
        # Batch size is configurable via EMBED_BATCH_SIZE in .env.
        record_embeddings = embedding_service.embed_texts(raw_texts, batch_size=settings.embed_batch_size)
        for rec, raw, emb in zip(person_records, raw_texts, record_embeddings):
            db.add(AncestryData(
                document_id=document_id,
                person_name=rec.get("person_name"),
                birth_date=rec.get("birth_date"),
                birth_location=rec.get("birth_location"),
                death_date=rec.get("death_date"),
                death_location=rec.get("death_location"),
                occupation=rec.get("occupation"),
                relation_type=rec.get("relation_type"),
                related_to=rec.get("related_to"),
                raw_text=raw,
                embedding=emb
            ))
            stored += 1

    document.content = full_text[:1000000]
    document.doc_metadata.update({
        "status": "completed",
        "processing_method": "direct_pipeline",
        "chunk_count": len(chunks),
        "footnote_count": sum(len(v) for v in chunk_footnote_map.values()),
        "person_records": stored,
    })
    db.commit()
    logger.info(f"[direct:{document_id}] Step 6/6: done — {stored} ancestry records stored")

    return {
        "success": True,
        "document_id": document_id,
        "filename": document.file_name,
        "title": document.title,
        "document_type": document.document_type,
        "processing_method": "direct_pipeline",
        "chunks": len(chunks),
        "person_records": stored,
        "message": "Document uploaded and processed via direct pipeline (regex + Ollama embeddings)"
    }


async def _process_with_agent(
    file_path: str,
    document: Document,
    db: Session,
    event: Optional[Dict[str, Any]] = None,
):
    """Optional DeepSeek-powered agentic cleaning (USE_AGENT_PROCESSING=true)."""
    from agent_service import genealogy_agent  # lazy import: only for agent mode

    document_id = document.id
    logger.info(f"Starting agent processing for document {document_id}")
    event = event or {"steps_taken": []}
    with step_timer(event, "agent processing"):
        agent_result = await genealogy_agent.process_document(file_path, document_id)

    if not agent_result["success"]:
        document.doc_metadata["status"] = "failed"
        document.doc_metadata["agent_error"] = agent_result.get("error", "Unknown error")
        db.commit()
        raise HTTPException(
            status_code=500,
            detail=f"Agent processing failed: {agent_result.get('error', 'Unknown error')}"
        )

    document.doc_metadata.update({
        "status": "completed",
        "agent_output": agent_result.get("agent_output", ""),
        "processed_content_preview": agent_result.get("processed_content", ""),
    })
    db.commit()
    logger.info(f"Agent processing completed for document {document_id}")

    return {
        "success": True,
        "document_id": document_id,
        "filename": document.file_name,
        "title": document.title,
        "document_type": document.document_type,
        "processing_method": "agentic_ai",
        "agent_status": "completed",
        "message": "Document uploaded and processed by AI agent successfully"
    }


@router.post("/upload")
async def upload_document(
    file: UploadFile = File(...),
    document_type: str = "journal",
    db: Session = Depends(get_db)
):
    """
    Upload a document.

    Default: direct pipeline (regex entities + Ollama embeddings, no LLM calls).
    Set USE_AGENT_PROCESSING=true in .env for the DeepSeek agent instead.
    """
    try:
        with rag_event_context("file_upload", file_name=file.filename) as event:
            file_ext = os.path.splitext(file.filename)[1].lower()
            if file_ext not in {'.pdf', '.docx', '.txt', '.json'}:
                raise HTTPException(status_code=400, detail=f"Unsupported file type: {file_ext}")

            os.makedirs(settings.upload_directory, exist_ok=True)

            unique_filename = f"{uuid.uuid4()}_{file.filename}"
            file_path = os.path.join(settings.upload_directory, unique_filename)

            with step_timer(event, "save file to disk"):
                with open(file_path, "wb") as f:
                    content = await file.read()
                    f.write(content)

            if len(content) > settings.max_upload_size:
                os.remove(file_path)
                raise HTTPException(status_code=413, detail="File too large")

            # ── Create document record ──
            processing_method = "agentic_ai" if settings.use_agent_processing else "direct_pipeline"
            document = Document(
                title=file.filename,
                document_type=document_type.lower(),
                file_name=unique_filename,
                content=f"Processing ({processing_method})... Original file: {file.filename}",
                doc_metadata={
                    "original_filename": file.filename,
                    "file_size": len(content),
                    "processing_method": processing_method,
                    "status": "processing"
                }
            )
            with step_timer(event, "create document record"):
                db.add(document)
                db.flush()
                document_id = document.id
            logger.info(f"Created document record ID={document_id} ({processing_method})")

            if settings.use_agent_processing:
                result = await _process_with_agent(file_path, document, db, event=event)
                event["tools_called"].append("GenealogyAgent.process_document")
            else:
                result = await _process_direct(file_path, document, db, event=event)
                event["tools_called"].extend([
                    "DocumentProcessor.process_document",
                    "embedding_service.embed_texts",
                    "DocumentProcessor.extract_person_records",
                ])
            event["api_calls_made"].append(f"embedding ({settings.embedding_provider})")
            event["final_response"] = result.get("message", "upload processed")
            return result

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error uploading document: {e}")
        raise HTTPException(status_code=500, detail=f"Error uploading document: {str(e)}")


@router.get("/list")
async def list_documents(
    doc_type: Optional[str] = None,
    skip: int = 0,
    limit: int = 10,
    db: Session = Depends(get_db)
):
    try:
        query = db.query(Document)
        if doc_type:
            query = query.filter(Document.document_type == doc_type.lower())
        total = query.count()
        documents = query.order_by(Document.upload_date.desc()).offset(skip).limit(limit).all()
        return {
            "total": total,
            "documents": [
                {
                    "id": doc.id,
                    "title": doc.title,
                    "type": doc.document_type,
                    "filename": doc.file_name,
                    "upload_date": doc.upload_date.isoformat() if doc.upload_date else None,
                    "chunks": len(doc.chunks),
                    "footnotes": len(doc.footnotes),
                    "ancestors_found": len(doc.ancestry_data)
                }
                for doc in documents
            ]
        }
    except Exception as e:
        logger.error(f"Error listing documents: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/{document_id}")
async def get_document(document_id: int, db: Session = Depends(get_db)):
    try:
        document = db.query(Document).filter(Document.id == document_id).first()
        if not document:
            raise HTTPException(status_code=404, detail="Document not found")
        log_rag_event(
            "file_view",
            file_name=document.file_name,
            final_response=f"Viewed document {document_id}: {document.title}"
        )
        return {
            "id": document.id,
            "title": document.title,
            "type": document.document_type,
            "filename": document.file_name,
            "upload_date": document.upload_date.isoformat() if document.upload_date else None,
            "content_preview": document.content[:500] if document.content else None,
            "chunks": len(document.chunks),
            "footnotes": len(document.footnotes),
            "ancestry_records": len(document.ancestry_data),
            "metadata": document.doc_metadata
        }
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error getting document: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/{document_id}/footnotes")
async def get_document_footnotes(document_id: int, db: Session = Depends(get_db)):
    try:
        document = db.query(Document).filter(Document.id == document_id).first()
        if not document:
            raise HTTPException(status_code=404, detail="Document not found")
        return {
            "document_id": document_id,
            "title": document.title,
            "footnote_count": len(document.footnotes),
            "footnotes": [fn.to_dict() for fn in document.footnotes]
        }
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error getting footnotes: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.delete("/{document_id}")
async def delete_document(document_id: int, db: Session = Depends(get_db)):
    try:
        document = db.query(Document).filter(Document.id == document_id).first()
        if not document:
            raise HTTPException(status_code=404, detail="Document not found")
        file_path = os.path.join(settings.upload_directory, document.file_name)
        if os.path.exists(file_path):
            os.remove(file_path)
        db.delete(document)
        db.commit()
        log_rag_event(
            "file_delete",
            file_name=document.file_name,
            final_response=f"Deleted document {document_id}"
        )
        return {"success": True, "message": "Document deleted successfully"}
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error deleting document: {e}")
        raise HTTPException(status_code=500, detail=str(e))