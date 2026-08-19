"""
LLM service - supports DeepSeek, OpenAI, Groq, Ollama, and Azure Foundry
"""

import logging
import re
import requests
from enum import Enum
from typing import Any, List, Dict, Optional, Tuple
from config import settings

logger = logging.getLogger(__name__)


class ReasoningMode(str, Enum):
    """DeepSeek thinking-effort levels (OpenAI format `reasoning_effort`)."""

    LOW = "low"
    HIGH = "high"
    MAX = "max"


# Rule-based query classification. Rules are checked in priority order:
# comparison / multi-step patterns win over simple factoid patterns so a
# query like "what is the difference between X and Y" is HIGH, not LOW.
RULES = [
    (r"\b(compare|difference|vs|versus|contrast)\b", ReasoningMode.HIGH),
    (
        r"\b(you said|earlier|what did you mean|last time|how does .* relate|"
        r"connect|between .* and|search|browse|fetch|calculate|email|send)\b",
        ReasoningMode.MAX,
    ),
    (r"\b(what is|who is|define|when did)\b", ReasoningMode.LOW),
]


def rule_based_classify(query: str) -> Optional[ReasoningMode]:
    """Classify a query into a DeepSeek reasoning-effort level.

    Returns None when no rule matches; callers should fall back to
    ReasoningMode.LOW (cheap, fast default).
    """
    q = query.lower()
    for pattern, mode in RULES:
        if re.search(pattern, q):
            return mode
    return None


class LLMService:
    def __init__(self):
        self.provider = settings.llm_provider
        self.last_reasoning_mode: Optional[str] = None
        logger.info(f"LLM service using provider: {self.provider}")

    def generate_response(
        self,
        query: str,
        context: List[Dict],
        system_prompt: Optional[str] = None
    ) -> str:
        """Generate a response, discarding token usage metadata."""
        content, _ = self.generate_response_with_usage(query, context, system_prompt)
        return content

    def generate_response_with_usage(
        self,
        query: str,
        context: List[Dict],
        system_prompt: Optional[str] = None
    ) -> Tuple[str, Dict[str, int]]:
        """Generate a response and return (content, token_usage).

        `token_usage` contains prompt_tokens / completion_tokens / total_tokens
        when the provider reports usage; otherwise it is an empty dict.
        """
        if not system_prompt:
            system_prompt = self._get_default_system_prompt()

        context_str = self._build_context_string(context)
        user_message = f"Context:\n{context_str}\n\nQuestion: {query}"

        try:
            if self.provider == "openai":
                return self._call_openai(system_prompt, user_message)
            elif self.provider == "deepseek":
                return self._call_deepseek(query, system_prompt, user_message)
            elif self.provider == "groq":
                return self._call_groq(system_prompt, user_message)
            elif self.provider == "azure-foundry":
                return self._call_azure_foundry(system_prompt, user_message)
            else:
                return self._call_ollama(system_prompt, user_message)
        except Exception as e:
            logger.error(f"Error generating response: {e}")
            return f"Error generating response: {str(e)}", {}

    def get_active_model_name(self) -> str:
        """Name of the chat model currently in use (for pricing lookup)."""
        model_by_provider = {
            "openai": settings.openai_model,
            "deepseek": settings.deepseek_model,
            "groq": settings.groq_model,
            "azure-foundry": settings.azure_foundry_chat_model,
            "ollama": settings.ollama_chat_model,
        }
        return model_by_provider.get(self.provider, "")

    def _call_groq(self, system_prompt: str, user_message: str) -> Tuple[str, Dict[str, int]]:
        """Call Groq API — fast LLaMA inference, free tier available."""
        try:
            from groq import Groq
        except ImportError:
            raise ImportError(
                "groq package not installed. Add 'groq==0.9.0' to requirements.txt "
                "and rebuild with docker-compose up --build"
            )

        client = Groq(api_key=settings.groq_api_key)
        response = client.chat.completions.create(
            model=settings.groq_model,
            messages=[
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": user_message}
            ],
            max_tokens=settings.max_tokens,
            temperature=settings.temperature
        )
        return response.choices[0].message.content, self._usage_from_openai_response(response)

    def _call_ollama(self, system_prompt: str, user_message: str) -> Tuple[str, Dict[str, int]]:
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
        data = response.json()
        prompt_tokens = data.get("prompt_eval_count") or 0
        completion_tokens = data.get("eval_count") or 0
        usage = {
            "prompt_tokens": prompt_tokens,
            "completion_tokens": completion_tokens,
            "total_tokens": prompt_tokens + completion_tokens,
        }
        return data["message"]["content"], usage

    def _call_deepseek(self, query: str, system_prompt: str, user_message: str) -> Tuple[str, Dict[str, int]]:
        """Call the DeepSeek API (OpenAI-compatible) with classified thinking.

        The query is classified with rule_based_classify() and mapped to a
        `reasoning_effort` level (low/high/max) so simple factoid questions
        answer quickly while comparison / multi-step questions get a bigger
        reasoning budget. Queries matching no rule default to low.
        DeepSeek's default is thinking mode enabled.
        """
        from openai import OpenAI
        client = OpenAI(
            api_key=settings.deepseek_api_key,
            base_url=settings.deepseek_base_url
        )
        messages = [
            {"role": "system", "content": system_prompt},
            {"role": "user", "content": user_message}
        ]

        # No rule match falls back to LOW — the cheap, fast default.
        mode = rule_based_classify(query) or ReasoningMode.LOW
        self.last_reasoning_mode = mode.value
        logger.info("DeepSeek reasoning mode for query: %s", mode.value)

        # In DeepSeek "thinking" mode, reasoning tokens count toward max_tokens.
        # Reserve enough budget so the final answer is not truncated to an
        # empty content (which previously caused source-only responses).
        response = client.chat.completions.create(
            model=settings.deepseek_model,
            messages=messages,
            stream=False,
            reasoning_effort=mode.value,
            extra_body={"thinking": {"type": "enabled"}},
            temperature=settings.temperature,
            max_tokens=max(settings.max_tokens, 4096)
        )
        content = response.choices[0].message.content

        # Fallback: if the thinking phase still consumed the whole budget,
        # retry with plain (non-thinking) completion so an answer is produced.
        if not content:
            logger.warning(
                "DeepSeek returned empty content (thinking consumed the token "
                "budget); retrying without thinking mode"
            )
            response = client.chat.completions.create(
                model=settings.deepseek_model,
                messages=messages,
                stream=False,
                temperature=settings.temperature,
                max_tokens=settings.max_tokens
            )
            content = response.choices[0].message.content

        return content or "", self._usage_from_openai_response(response)

    def _call_openai(self, system_prompt: str, user_message: str) -> Tuple[str, Dict[str, int]]:
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
        return response.choices[0].message.content, self._usage_from_openai_response(response)

    def _call_azure_foundry(self, system_prompt: str, user_message: str) -> Tuple[str, Dict[str, int]]:
        """Call Azure Foundry AI Hub endpoint."""
        from openai import OpenAI

        # Use OpenAI SDK with Azure Foundry endpoint
        client = OpenAI(
            api_key=settings.azure_foundry_api_key,
            base_url=settings.azure_foundry_chat_endpoint,
            default_headers={"User-Agent": "genealogy-chatbot/1.0"}
        )

        response = client.chat.completions.create(
            model=settings.azure_foundry_chat_model,
            messages=[
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": user_message}
            ],
            temperature=settings.temperature,
            max_tokens=settings.max_tokens
        )
        return response.choices[0].message.content, self._usage_from_openai_response(response)

    @staticmethod
    def _usage_from_openai_response(response: Any) -> Dict[str, int]:
        """Extract token usage from an OpenAI-compatible completion response.

        Includes DeepSeek prompt-cache fields (reported when prompt caching
        is enabled) so cost can be split into cache hit / cache miss.
        """
        usage = getattr(response, "usage", None)
        if not usage:
            return {}
        return {
            "prompt_tokens": getattr(usage, "prompt_tokens", None) or 0,
            "completion_tokens": getattr(usage, "completion_tokens", None) or 0,
            "total_tokens": getattr(usage, "total_tokens", None) or 0,
            "prompt_cache_hit_tokens": getattr(usage, "prompt_cache_hit_tokens", None) or 0,
            "prompt_cache_miss_tokens": getattr(usage, "prompt_cache_miss_tokens", None) or 0,
        }

    @staticmethod
    def _get_default_system_prompt() -> str:
        return """You are an expert genealogist specializing in African American ancestry research.

CRITICAL INSTRUCTIONS:
1. You MUST answer based ONLY on the context provided. The context contains real excerpts from historical documents.
2. If the context mentions a person, family, or event — use that information to answer directly and specifically.
3. If you cannot find information in the documents, explicitly mention that answer is not in the documents. Don't generate any hallucinated responses.
4. Do NOT suggest external research resources if the answer is in the context.
5. When the context includes footnote citations, reference them in your answer using [footnote X] notation.
6. Only say information is unavailable if it is genuinely absent from ALL provided context chunks.
7. Be specific — include names, dates, locations, and family relationships from the context.

Answer directly and specifically. Start your answer immediately without preamble."""

    @staticmethod
    def _build_context_string(context: List[Dict]) -> str:
        if not context:
            return "No relevant context found."

        context_parts = []
        for i, item in enumerate(context):
            if not isinstance(item, dict):
                continue

            if 'text' in item:
                header = (
                    f"[Document {i+1}: {item.get('document_title', 'Unknown')} "
                    f"- Relevance: {item.get('similarity_score', 0):.2%}]"
                )
                body = item['text']

                footnotes = item.get('footnotes', [])
                if footnotes:
                    fn_lines = "\nFootnote Citations:"
                    for fn in footnotes:
                        fn_lines += f"\n  [{fn['number']}] {fn['citation']}"
                    body += fn_lines

                context_parts.append(f"{header}\n{body}")

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