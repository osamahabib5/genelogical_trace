"""
API routes for document management
"""

import os
import logging
from fastapi import APIRouter, UploadFile, File, Depends, HTTPException
from sqlalchemy.orm import Session
from typing import Optional
import uuid
from datetime import datetime

from database import SessionLocal, Document, DocumentChunk, AncestryData
from document_processor import DocumentProcessor
from embedding_service import embedding_service
from config import settings

logger = logging.getLogger(__name__)
router = APIRouter()


def get_db():
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()


@router.post("/upload")
async def upload_document(
    file: UploadFile = File(...),
    document_type: str = "journal",
    db: Session = Depends(get_db)
):
    """
    Upload a document (PDF, DOCX, TXT, JSON)
    Embeddings are generated synchronously to guarantee they exist after upload.
    """
    try:
        # Validate file type
        file_ext = os.path.splitext(file.filename)[1].lower()
        if file_ext not in {'.pdf', '.docx', '.txt', '.json'}:
            raise HTTPException(status_code=400, detail=f"Unsupported file type: {file_ext}")

        # Create uploads directory if not exists
        os.makedirs(settings.upload_directory, exist_ok=True)

        # Save file with unique name
        unique_filename = f"{uuid.uuid4()}_{file.filename}"
        file_path = os.path.join(settings.upload_directory, unique_filename)

        # Write file
        with open(file_path, "wb") as f:
            content = await file.read()
            f.write(content)

        # Check file size
        if len(content) > settings.max_upload_size:
            os.remove(file_path)
            raise HTTPException(status_code=413, detail="File too large")

        # Process document — extract text and chunks
        try:
            full_text, chunks = DocumentProcessor.process_document(file_path)
        except Exception as e:
            os.remove(file_path)
            raise HTTPException(status_code=400, detail=f"Error processing file: {str(e)}")

        logger.info(f"Extracted {len(chunks)} chunks from {file.filename}")

        # Create document record
        document = Document(
            title=file.filename,
            document_type=document_type.lower(),
            file_name=unique_filename,
            content=full_text[:10000],
            doc_metadata={
                "original_filename": file.filename,
                "file_size": len(content),
                "chunk_count": len(chunks)
            }
        )
        db.add(document)
        db.flush()  # Get document ID
        document_id = document.id
        logger.info(f"Created document record with ID {document_id}")

        # ── Generate embeddings and save chunks SYNCHRONOUSLY ──
        success_count = 0
        error_count = 0

        for idx, chunk_text in enumerate(chunks):
            try:
                # Generate embedding for this chunk
                embedding = embedding_service.embed_text(chunk_text)

                doc_chunk = DocumentChunk(
                    document_id=document_id,
                    chunk_text=chunk_text,
                    chunk_number=idx,
                    embedding=embedding
                )
                db.add(doc_chunk)
                success_count += 1

                # Commit every 50 chunks to avoid memory buildup
                if idx % 50 == 0:
                    db.flush()
                    logger.info(f"Processed {idx}/{len(chunks)} chunks...")

            except Exception as e:
                logger.error(f"Error embedding chunk {idx}: {e}")
                error_count += 1
                continue

        # ── Extract genealogical entities and save ──
        try:
            entities = DocumentProcessor.extract_genealogical_entities(full_text)
            full_embedding = embedding_service.embed_text(full_text[:1000])

            for person_name in entities.get('names', [])[:10]:
                ancestry_record = AncestryData(
                    document_id=document_id,
                    person_name=person_name,
                    raw_text=full_text[:500],
                    embedding=full_embedding
                )
                db.add(ancestry_record)
        except Exception as e:
            logger.warning(f"Entity extraction failed (non-critical): {e}")

        # Final commit
        db.commit()
        logger.info(f"Document {document_id} fully processed. "
                    f"Chunks: {success_count} success, {error_count} errors.")

        return {
            "success": True,
            "document_id": document_id,
            "filename": unique_filename,
            "title": file.filename,
            "document_type": document_type,
            "chunks": success_count,
            "embedding_errors": error_count,
            "message": "Document uploaded and embeddings generated successfully"
        }

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
    """List uploaded documents"""
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
    """Get document details"""
    try:
        document = db.query(Document).filter(Document.id == document_id).first()

        if not document:
            raise HTTPException(status_code=404, detail="Document not found")

        return {
            "id": document.id,
            "title": document.title,
            "type": document.document_type,
            "filename": document.file_name,
            "upload_date": document.upload_date.isoformat() if document.upload_date else None,
            "content_preview": document.content[:500] if document.content else None,
            "chunks": len(document.chunks),
            "ancestry_records": len(document.ancestry_data),
            "metadata": document.doc_metadata
        }
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error getting document: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.delete("/{document_id}")
async def delete_document(document_id: int, db: Session = Depends(get_db)):
    """Delete a document and its associated data"""
    try:
        document = db.query(Document).filter(Document.id == document_id).first()

        if not document:
            raise HTTPException(status_code=404, detail="Document not found")

        # Delete associated file
        file_path = os.path.join(settings.upload_directory, document.file_name)
        if os.path.exists(file_path):
            os.remove(file_path)

        # Delete from database (cascades to chunks and ancestry data)
        db.delete(document)
        db.commit()

        return {"success": True, "message": "Document deleted successfully"}
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error deleting document: {e}")
        raise HTTPException(status_code=500, detail=str(e))