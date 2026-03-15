"""
Service for retrieving relevant genealogical information using vector similarity search
"""

import logging
from typing import List, Dict, Optional
from sqlalchemy.orm import Session
from sqlalchemy import text
from database import DocumentChunk, AncestryData, Document, DocumentFootnote
from config import settings

logger = logging.getLogger(__name__)


class RetrievalService:

    @staticmethod
    def search_similar_chunks(
        db: Session,
        embedding: List[float],
        top_k: int = 8,
        keyword: Optional[str] = None
    ) -> List[Dict]:
        """
        Search for document chunks similar to the given embedding.
        If keyword provided, filter to chunks containing that keyword first.
        Enriches results with footnote citations.
        """
        try:
            embedding_str = "[" + ",".join(str(x) for x in embedding) + "]"

            if keyword:
                sql = text("""
                    SELECT
                        dc.id,
                        dc.chunk_text,
                        d.title,
                        d.document_type,
                        dc.chunk_number,
                        dc.document_id,
                        1 - (dc.embedding <=> CAST(:embedding AS vector)) AS similarity
                    FROM document_chunks dc
                    JOIN documents d ON dc.document_id = d.id
                    WHERE dc.embedding IS NOT NULL
                    AND dc.chunk_text ILIKE :keyword
                    ORDER BY dc.embedding <=> CAST(:embedding AS vector)
                    LIMIT :top_k
                """)
                rows = db.execute(sql, {
                    "embedding": embedding_str,
                    "keyword": f"%{keyword}%",
                    "top_k": top_k
                }).fetchall()

                if rows:
                    logger.info(f"Keyword '{keyword}' matched {len(rows)} chunks")
                    return RetrievalService._enrich_with_footnotes(db, rows)
                else:
                    logger.info(f"Keyword '{keyword}' matched no chunks, falling back to vector search")

            # Standard vector search
            sql = text("""
                SELECT
                    dc.id,
                    dc.chunk_text,
                    d.title,
                    d.document_type,
                    dc.chunk_number,
                    dc.document_id,
                    1 - (dc.embedding <=> CAST(:embedding AS vector)) AS similarity
                FROM document_chunks dc
                JOIN documents d ON dc.document_id = d.id
                WHERE dc.embedding IS NOT NULL
                ORDER BY dc.embedding <=> CAST(:embedding AS vector)
                LIMIT :top_k
            """)

            rows = db.execute(sql, {
                "embedding": embedding_str,
                "top_k": top_k
            }).fetchall()

            logger.info(f"Vector search returned {len(rows)} chunks")
            return RetrievalService._enrich_with_footnotes(db, rows)

        except Exception as e:
            logger.error(f"Error searching similar chunks: {e}")
            return []

    @staticmethod
    def _enrich_with_footnotes(db: Session, rows) -> List[Dict]:
        """
        Take raw query rows and enrich each chunk with its linked footnotes.
        """
        results = []
        for row in rows:
            chunk_id = row[0]
            chunk_number = row[4]

            # Fetch footnotes linked to this chunk
            footnotes = db.query(DocumentFootnote).filter(
                DocumentFootnote.chunk_id == chunk_id
            ).all()

            footnote_list = [
                {
                    "number": fn.footnote_number,
                    "citation": fn.footnote_text
                }
                for fn in footnotes
            ]

            results.append({
                "chunk_id": chunk_id,
                "text": row[1],
                "document_title": row[2],
                "document_type": row[3],
                "chunk_number": chunk_number,
                "page_number": (chunk_number // 3) + 1,
                "similarity_score": float(row[6]) if row[6] is not None else 0.0,
                "footnotes": footnote_list
            })

        return results

    @staticmethod
    def search_ancestry_data(db: Session, embedding: List[float], top_k: int = 5) -> List[Dict]:
        try:
            embedding_str = "[" + ",".join(str(x) for x in embedding) + "]"

            sql = text("""
                SELECT id, person_name, birth_date, birth_location,
                       death_date, death_location, occupation,
                       relation_type, related_to, raw_text
                FROM ancestry_data
                WHERE embedding IS NOT NULL
                ORDER BY embedding <=> CAST(:embedding AS vector)
                LIMIT :top_k
            """)

            results = db.execute(sql, {
                "embedding": embedding_str,
                "top_k": top_k
            }).fetchall()

            return [
                {
                    "id": row[0],
                    "person_name": row[1],
                    "birth_date": row[2],
                    "birth_location": row[3],
                    "death_date": row[4],
                    "death_location": row[5],
                    "occupation": row[6],
                    "relation_type": row[7],
                    "related_to": row[8],
                    "raw_text": row[9]
                }
                for row in results
            ]

        except Exception as e:
            logger.error(f"Error searching ancestry data: {e}")
            return []

    @staticmethod
    def search_by_person_name(db: Session, name: str) -> List[Dict]:
        try:
            records = db.query(AncestryData).filter(
                AncestryData.person_name.ilike(f"%{name}%")
            ).all()
            return [record.to_dict() for record in records]
        except Exception as e:
            logger.error(f"Error searching by person name: {e}")
            return []

    @staticmethod
    def search_connected_ancestry(db: Session, person_name: str) -> List[Dict]:
        try:
            person_records = db.query(AncestryData).filter(
                AncestryData.person_name.ilike(f"%{person_name}%")
            ).all()

            connected = list(person_records)
            for record in person_records:
                if record.related_to:
                    related_records = db.query(AncestryData).filter(
                        AncestryData.person_name.ilike(f"%{record.related_to}%")
                    ).all()
                    connected.extend(related_records)

            seen = set()
            unique_records = []
            for record in connected:
                key = (record.id, record.person_name)
                if key not in seen:
                    seen.add(key)
                    unique_records.append(record.to_dict())

            return unique_records
        except Exception as e:
            logger.error(f"Error searching connected ancestry: {e}")
            return []

    @staticmethod
    def get_documents_by_type(db: Session, doc_type: str) -> List[Dict]:
        try:
            documents = db.query(Document).filter(
                Document.document_type == doc_type
            ).all()
            return [
                {
                    "id": doc.id,
                    "title": doc.title,
                    "type": doc.document_type,
                    "upload_date": doc.upload_date.isoformat() if doc.upload_date else None,
                    "file_name": doc.file_name
                }
                for doc in documents
            ]
        except Exception as e:
            logger.error(f"Error getting documents by type: {e}")
            return []