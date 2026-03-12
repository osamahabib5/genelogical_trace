"""
LLM service - supports Ollama and OpenAI
"""

import logging
import requests
from typing import List, Dict, Optional
from config import settings

logger = logging.getLogger(__name__)


class LLMService:
    def __init__(self):
        self.provider = settings.llm_provider
        logger.info(f"LLM service using provider: {self.provider}")

    def generate_response(
        self,
        query: str,
        context: List[Dict],
        system_prompt: Optional[str] = None
    ) -> str:
        if not system_prompt:
            system_prompt = self._get_default_system_prompt()

        context_str = self._build_context_string(context)
        user_message = f"Context:\n{context_str}\n\nQuestion: {query}"

        try:
            if self.provider == "openai":
                return self._call_openai(system_prompt, user_message)
            else:
                return self._call_ollama(system_prompt, user_message)
        except Exception as e:
            logger.error(f"Error generating response: {e}")
            return f"Error generating response: {str(e)}"

    def _call_ollama(self, system_prompt: str, user_message: str) -> str:
        response = requests.post(
            f"{settings.ollama_base_url}/api/chat",
            json={
                "model": settings.ollama_chat_model,
                "messages": [
                    {"role": "system", "content": system_prompt},
                    {"role": "user", "content": user_message}
                ],
                "stream": False,
                "options": {
                    "temperature": settings.temperature,
                    "num_predict": settings.max_tokens
                }
            },
            timeout=300
        )
        response.raise_for_status()
        return response.json()["message"]["content"]

    def _call_openai(self, system_prompt: str, user_message: str) -> str:
        from openai import OpenAI
        client = OpenAI(api_key=settings.openai_api_key)
        response = client.chat.completions.create(
            model=settings.openai_model,
            messages=[
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": user_message}
            ],
            temperature=settings.temperature,
            max_tokens=settings.max_tokens
        )
        return response.choices[0].message.content

    @staticmethod
    def _get_default_system_prompt() -> str:
        return """You are an expert genealogist specializing in African American ancestry research.

CRITICAL INSTRUCTIONS:
1. You MUST answer based ONLY on the context provided. The context contains real excerpts from historical documents.
2. If the context mentions a person, family, or event — use that information to answer directly and specifically.
3. Do NOT say you cannot find information if it appears anywhere in the context.
4. Do NOT suggest external research resources if the answer is in the context.
5. Quote directly from the context when relevant to support your answer.
6. Only say information is unavailable if it is genuinely absent from ALL provided context chunks.
7. Be specific — include names, dates, locations, and family relationships mentioned in the context.

Answer directly and specifically using the context. Start your answer immediately without preamble."""

    @staticmethod
    def _build_context_string(context: List[Dict]) -> str:
        if not context:
            return "No relevant context found."

        context_parts = []
        for i, item in enumerate(context):
            if isinstance(item, dict):
                if 'text' in item:
                    context_parts.append(
                        f"[Document {i+1}: {item.get('document_title', 'Unknown')} "
                        f"- Relevance: {item.get('similarity_score', 0):.2%}]\n"
                        f"{item['text']}\n"
                    )
                elif 'person_name' in item:
                    parts = [
                        f"[Ancestry Record {i+1}]",
                        f"Name: {item.get('person_name', 'Unknown')}"
                    ]
                    if item.get('birth_date'):
                        parts.append(f"Birth: {item['birth_date']}")
                    if item.get('birth_location'):
                        parts.append(f"Location: {item['birth_location']}")
                    if item.get('occupation'):
                        parts.append(f"Occupation: {item['occupation']}")
                    if item.get('relation_type'):
                        parts.append(f"Relation: {item['relation_type']}")
                    context_parts.append(" | ".join(parts))

        return "\n---\n".join(context_parts) if context_parts else "No relevant context found."


llm_service = LLMService()