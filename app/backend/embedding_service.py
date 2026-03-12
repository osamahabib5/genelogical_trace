"""
Embedding service - supports Ollama and OpenAI
"""

import logging
import requests
from typing import List
from config import settings

logger = logging.getLogger(__name__)


class EmbeddingService:
    def __init__(self):
        self.provider = settings.llm_provider
        logger.info(f"Embedding service using provider: {self.provider}")

    def embed_text(self, text: str) -> List[float]:
        try:
            if self.provider == "openai":
                return self._embed_openai(text)
            else:
                return self._embed_ollama(text)
        except Exception as e:
            logger.error(f"Error generating embedding: {e}")
            return [0.0] * settings.embedding_dimension

    def embed_texts(self, texts: List[str]) -> List[List[float]]:
        return [self.embed_text(t) for t in texts]

    # def _embed_ollama(self, text: str) -> List[float]:
        response = requests.post(
            f"{settings.ollama_base_url}/api/embeddings",
            json={
                "model": settings.ollama_embed_model,
                "prompt": text
            },
            timeout=30
        )
        response.raise_for_status()
        return response.json()["embedding"]
    
    def _embed_ollama(self, text: str) -> List[float]:
        response = requests.post(
            f"{settings.ollama_base_url}/api/embed",
            json={
                "model": settings.ollama_embed_model,
                "input": text
            },
            timeout=30
        )
        response.raise_for_status()
        return response.json()["embeddings"][0]

    def _embed_openai(self, text: str) -> List[float]:
        from openai import OpenAI
        client = OpenAI(api_key=settings.openai_api_key)
        response = client.embeddings.create(
            input=text,
            model="text-embedding-3-small"
        )
        return response.data[0].embedding


embedding_service = EmbeddingService()