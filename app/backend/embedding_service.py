"""
Embedding service - supports Ollama (default), OpenAI, and Azure Foundry.
DeepSeek and Groq do not provide embedding endpoints. 
"""

import logging
import time
import requests
from typing import List, Optional
from config import settings

logger = logging.getLogger(__name__)


class EmbeddingService:
    def __init__(self):
        self.provider = settings.embedding_provider
        logger.info(f"Embedding service using provider: {self.provider}")

    def embed_text(self, text: str) -> List[float]:
        """Embed a single text string."""
        logger.info(f"Embedding single text ({len(text)} chars) via provider '{self.provider}'")
        try:
            if self.provider == "openai":
                return self._embed_openai_batch([text])[0]
            elif self.provider == "azure-foundry":
                return self._embed_azure_foundry_batch([text])[0]
            else:
                return self._embed_ollama_batch([text])[0]
        except Exception as e:
            logger.error(f"Error generating embedding: {e}")
            return [0.0] * settings.embedding_dimension

    def embed_texts(self, texts: List[str], batch_size: int = 32) -> List[List[float]]:
        """
        Embed multiple texts using batching for efficiency.
        """
        if not texts:
            return []

        all_embeddings = []
        for i in range(0, len(texts), batch_size):
            batch = texts[i:i + batch_size]
            batch_num = i // batch_size + 1
            logger.info(f"Embedding batch {batch_num} ({i+1}-{min(i+batch_size, len(texts))} of {len(texts)})")
            batch_embeddings = self._embed_batch_with_retry(batch, batch_num)
            all_embeddings.extend(batch_embeddings)
            logger.info(
                f"Embedded batch {batch_num}: {len(batch_embeddings)} vectors"
                f" (dim={len(batch_embeddings[0]) if batch_embeddings else 'n/a'})"
            )

        return all_embeddings

    def _embed_batch_with_retry(
        self,
        batch: List[str],
        batch_num: int,
        max_attempts: int = 2,
    ) -> List[List[float]]:
        """Embed one batch, retrying once on transient failure.

        Raises on the final attempt instead of returning zero-vectors, so a
        failed upload fails loudly rather than silently corrupting the
        vector index with zero embeddings.
        """
        last_error: Optional[Exception] = None
        for attempt in range(1, max_attempts + 1):
            try:
                if self.provider == "openai":
                    return self._embed_openai_batch(batch)
                elif self.provider == "azure-foundry":
                    return self._embed_azure_foundry_batch(batch)
                else:
                    return self._embed_ollama_batch(batch)
            except Exception as exc:
                last_error = exc
                if attempt < max_attempts:
                    logger.warning(
                        f"Embedding batch {batch_num} failed on attempt {attempt}: "
                        f"{exc}; retrying once..."
                    )
                    time.sleep(1)
        raise RuntimeError(
            f"Embedding batch {batch_num} failed after {max_attempts} attempts: {last_error}"
        ) from last_error

    def _embed_ollama_batch(self, texts: List[str]) -> List[List[float]]:
        response = requests.post(
            f"{settings.ollama_base_url}/api/embed",
            json={
                "model": settings.ollama_embed_model,
                "input": texts
            },
            timeout=120
        )
        response.raise_for_status()
        embeddings = response.json()["embeddings"]
        if embeddings:
            logger.info(
                f"Ollama '{settings.ollama_embed_model}' returned {len(embeddings)} "
                f"embeddings of dimension {len(embeddings[0])}"
            )
        return embeddings

    def _embed_openai_batch(self, texts: List[str]) -> List[List[float]]:
        from openai import OpenAI
        client = OpenAI(api_key=settings.openai_api_key)
        response = client.embeddings.create(
            input=texts,
            model=settings.openai_embedding_model
        )
        return [item.embedding for item in response.data]

    def _embed_azure_foundry_batch(self, texts: List[str]) -> List[List[float]]:
        """
        Send multiple texts to Azure Foundry embeddings endpoint.
        """
        from openai import AzureOpenAI

        endpoint = settings.azure_foundry_endpoint
        if not endpoint.endswith('/'):
            endpoint += '/'

        # Standard OpenAI-style Azure authentication
        client = AzureOpenAI(
            api_version=settings.azure_foundry_embed_version,
            azure_endpoint=settings.azure_foundry_endpoint,
            api_key=settings.azure_foundry_api_key
        )

        logger.info(f"Embedding {len(texts)} texts using Azure Foundry: {settings.azure_foundry_embed_model}")
        response = client.embeddings.create(
            input=texts,
            model=settings.azure_foundry_embed_model
        )
        
        embeddings = [item.embedding for item in response.data]
        logger.info(f"Successfully generated {len(embeddings)} embeddings")
        return embeddings


embedding_service = EmbeddingService()