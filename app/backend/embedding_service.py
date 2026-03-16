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
        """Embed a single text string."""
        try:
            if self.provider == "openai":
                return self._embed_openai_batch([text])[0]
            else:
                return self._embed_ollama_batch([text])[0]
        except Exception as e:
            logger.error(f"Error generating embedding: {e}")
            return [0.0] * settings.embedding_dimension

    def embed_texts(self, texts: List[str], batch_size: int = 32) -> List[List[float]]:
        """
        Embed multiple texts using batching for efficiency.
        Sends batch_size texts per API call instead of one at a time.
        """
        if not texts:
            return []

        all_embeddings = []

        for i in range(0, len(texts), batch_size):
            batch = texts[i:i + batch_size]
            logger.info(f"Embedding batch {i//batch_size + 1} "
                       f"({i+1}-{min(i+batch_size, len(texts))} of {len(texts)})")
            try:
                if self.provider == "openai":
                    batch_embeddings = self._embed_openai_batch(batch)
                else:
                    batch_embeddings = self._embed_ollama_batch(batch)
                all_embeddings.extend(batch_embeddings)
            except Exception as e:
                logger.error(f"Error embedding batch {i//batch_size + 1}: {e}")
                # Fall back to zero vectors for failed batch
                all_embeddings.extend(
                    [[0.0] * settings.embedding_dimension for _ in batch]
                )

        return all_embeddings

    def _embed_ollama_batch(self, texts: List[str]) -> List[List[float]]:
        """
        Send multiple texts to Ollama /api/embed in one request.
        Ollama accepts a list under the 'input' key.
        """
        response = requests.post(
            f"{settings.ollama_base_url}/api/embed",
            json={
                "model": settings.ollama_embed_model,
                "input": texts  # list of strings — Ollama handles batching natively
            },
            timeout=120  # longer timeout for batches
        )
        response.raise_for_status()
        return response.json()["embeddings"]

    def _embed_openai_batch(self, texts: List[str]) -> List[List[float]]:
        """
        Send multiple texts to OpenAI embeddings API in one request.
        OpenAI accepts up to 2048 inputs per call.
        """
        from openai import OpenAI
        client = OpenAI(api_key=settings.openai_api_key)
        response = client.embeddings.create(
            input=texts,
            model="text-embedding-3-small"
        )
        # Results are returned in the same order as input
        return [item.embedding for item in response.data]


embedding_service = EmbeddingService()