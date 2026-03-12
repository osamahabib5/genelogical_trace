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
            timeout=300  # Ollama can be slow on first response
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
        return """You are an expert genealogist and historian specializing in African American ancestry research.
Your role is to help users trace and understand genealogical connections based on historical documents and records.

When answering queries:
1. Use the provided context from documents and records to answer accurately
2. Identify family relationships (parents, siblings, spouses, children)
3. Extract and highlight important biographical information (birth/death dates, locations, occupations)
4. Provide clear explanations of genealogical connections
5. Acknowledge any gaps in the records or uncertain information
6. Suggest possible connections or areas for further research

Be respectful and sensitive when discussing historical records, particularly those related to slavery or discrimination.
Always cite which document or record the information comes from when possible."""

    @staticmethod
    def _build_context_string(context: List[Dict]) -> str:
        if not context:
            return "No relevant context found."

        context_parts = []
        for item in context:
            if isinstance(item, dict):
                if 'text' in item:
                    context_parts.append(
                        f"From {item.get('document_title', 'Unknown')} "
                        f"({item.get('document_type', 'unknown')} - "
                        f"Relevance: {item.get('similarity_score', 0):.2%}):\n"
                        f"{item['text'][:500]}...\n"
                    )
                elif 'person_name' in item:
                    parts = [f"Name: {item.get('person_name', 'Unknown')}"]
                    if item.get('birth_date'):
                        parts.append(f"Birth: {item['birth_date']}")
                    if item.get('birth_location'):
                        parts.append(f"Location: {item['birth_location']}")
                    if item.get('occupation'):
                        parts.append(f"Occupation: {item['occupation']}")
                    if item.get('relation_type'):
                        parts.append(f"Relation: {item['relation_type']}")
                    context_parts.append(" | ".join(parts))

        return "\n".join(context_parts) if context_parts else "No relevant context found."


llm_service = LLMService()