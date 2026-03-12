"""
Genealogy Ancestry Chatbot Backend
Main FastAPI application for processing documents and answering genealogical queries
"""

import os
from contextlib import asynccontextmanager
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from config import settings
from routes import documents, queries
from database import Base


# Initialize database
engine = create_engine(
    settings.database_url,
    pool_pre_ping=True,
    echo=False
)

SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)


@asynccontextmanager
async def lifespan(app: FastAPI):
    # Startup
    print("Starting up - creating database tables...")
    Base.metadata.create_all(bind=engine)
    print("Database tables created/verified")
    yield
    # Shutdown
    print("Shutting down...")


app = FastAPI(
    title="Genealogy Ancestry Chatbot",
    description="AI-powered chatbot for tracing African American genealogical ancestry",
    version="1.0.0",
    lifespan=lifespan
)

# Configure CORS
origins = [
    "http://localhost:3000",
    "http://localhost:8000",
    "http://127.0.0.1:3000",
    "http://127.0.0.1:8000",
]

if settings.allowed_origins:
    origins.extend(settings.allowed_origins.split(","))

app.add_middleware(
    CORSMiddleware,
    allow_origins=origins,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Include routes
app.include_router(documents.router, prefix="/api/documents", tags=["documents"])
app.include_router(queries.router, prefix="/api/queries", tags=["queries"])


@app.get("/")
async def root():
    """Root endpoint"""
    return {
        "message": "Genealogy Ancestry Chatbot API",
        "version": "1.0.0",
        "docs": "/docs"
    }


@app.get("/health")
async def health_check():
    """Health check endpoint"""
    return {
        "status": "healthy",
        "service": "genealogy-chatbot-backend"
    }


if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=8000)
