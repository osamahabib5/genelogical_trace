"""
Database models and session management
"""

# from sqlalchemy import Column, Integer, String, Text, DateTime, JSONB, ForeignKey, create_engine
from sqlalchemy import Column, Integer, String, Text, DateTime, ForeignKey, create_engine
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.ext.declarative import declarative_base
# from sqlalchemy.orm import relationship, Session
from sqlalchemy.orm import relationship, Session, sessionmaker
from datetime import datetime
from pgvector.sqlalchemy import Vector
from config import settings
import uuid

Base = declarative_base()


class Document(Base):
    __tablename__ = "documents"
    
    id = Column(Integer, primary_key=True)
    title = Column(String(255), nullable=False)
    document_type = Column(String(50), nullable=False)  # 'journal' or 'application'
    file_name = Column(String(255), nullable=False)
    content = Column(Text)
    upload_date = Column(DateTime, default=datetime.utcnow)
    uploaded_by = Column(String(255))
    doc_metadata  = Column(JSONB, default={})
    
    # Relationships
    chunks = relationship("DocumentChunk", back_populates="document", cascade="all, delete-orphan")
    ancestry_data = relationship("AncestryData", back_populates="document", cascade="all, delete-orphan")
    
    def __repr__(self):
        return f"<Document(id={self.id}, title='{self.title}', type='{self.document_type}')>"


class DocumentChunk(Base):
    __tablename__ = "document_chunks"
    
    id = Column(Integer, primary_key=True)
    document_id = Column(Integer, ForeignKey("documents.id"), nullable=False)
    chunk_text = Column(Text, nullable=False)
    chunk_number = Column(Integer)
    # embedding = Column(Vector(1536))
    embedding = Column(Vector(768))
    # Relationships
    document = relationship("Document", back_populates="chunks")
    
    def __repr__(self):
        return f"<DocumentChunk(id={self.id}, document_id={self.document_id})>"


class AncestryData(Base):
    __tablename__ = "ancestry_data"
    
    id = Column(Integer, primary_key=True)
    document_id = Column(Integer, ForeignKey("documents.id"), nullable=False)
    person_name = Column(String(255))
    birth_date = Column(String(50))
    birth_location = Column(String(255))
    death_date = Column(String(50))
    death_location = Column(String(255))
    occupation = Column(String(255))
    relation_type = Column(String(100))
    related_to = Column(String(255))
    raw_text = Column(Text)
    # embedding = Column(Vector(1536))
    embedding = Column(Vector(768))
    extraction_date = Column(DateTime, default=datetime.utcnow)
    
    # Relationships
    document = relationship("Document", back_populates="ancestry_data")
    
    def to_dict(self):
        return {
            "id": self.id,
            "person_name": self.person_name,
            "birth_date": self.birth_date,
            "birth_location": self.birth_location,
            "death_date": self.death_date,
            "death_location": self.death_location,
            "occupation": self.occupation,
            "relation_type": self.relation_type,
            "related_to": self.related_to,
            "raw_text": self.raw_text
        }
    
    def __repr__(self):
        return f"<AncestryData(id={self.id}, person={self.person_name})>"


class QueryHistory(Base):
    __tablename__ = "query_history"
    
    id = Column(Integer, primary_key=True)
    query_text = Column(Text, nullable=False)
    results = Column(JSONB)
    query_date = Column(DateTime, default=datetime.utcnow)
    relevance_score = Column(Integer)
    
    def __repr__(self):
        return f"<QueryHistory(id={self.id}, query='{self.query_text[:50]}...')>"



# Create engine
engine = create_engine(settings.database_url)

# Create session factory
SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)

def create_tables():
    """Create all tables in the database"""
    Base.metadata.create_all(bind=engine)