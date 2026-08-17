"""
sample_embedding_deepseek.py

Verification script for the AI providers used by this project:

1. Chat        -> DeepSeek API (primary LLM provider)
2. Embeddings  -> provider set by EMBEDDING_PROVIDER in .env
                  (ollama = local Ollama model, openai = OpenAI API)

API keys are loaded from the project's .env file — never hard-code keys.
Run from the project root:
    python sample_embedding_deepseek.py
"""

import re
from pathlib import Path

import requests


def load_env(path: Path = Path(__file__).parent / ".env") -> dict:
    """Minimal .env parser (KEY=VALUE lines, no extra dependencies)."""
    env = {}
    if not path.exists():
        return env
    for raw in path.read_text(encoding="utf-8").splitlines():
        line = raw.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, _, value = line.partition("=")
        env[key.strip()] = value.strip().strip('"').strip("'")
    return env


def post_json(url: str, headers: dict, payload: dict, timeout: int = 120):
    """POST JSON and fail loudly (with status + body) instead of crashing on .json()."""
    resp = requests.post(url, headers=headers, json=payload, timeout=timeout)
    if resp.status_code != 200:
        raise RuntimeError(
            f"HTTP {resp.status_code}: {resp.text[:300]}"
        )
    try:
        return resp.json()
    except requests.exceptions.JSONDecodeError:
        # This is the exact error the old script hit: a non-JSON body
        # (usually an HTML error page) parsed with .json() unchecked.
        raise RuntimeError(
            f"HTTP {resp.status_code} returned non-JSON body: {resp.text[:300]}"
        )


def main() -> None:
    env = load_env()

    deepseek_key = env.get("DEEPSEEK_API_KEY", "")
    deepseek_base = env.get("DEEPSEEK_BASE_URL", "https://api.deepseek.com").rstrip("/")
    deepseek_model = env.get("DEEPSEEK_MODEL", "deepseek-v4-pro")
    openai_key = env.get("OPENAI_API_KEY", "")
    embed_model = env.get("OPENAI_EMBEDDING_MODEL", "text-embedding-3-small")
    embed_provider = env.get("EMBEDDING_PROVIDER", "ollama")
    ollama_base = env.get("OLLAMA_BASE_URL", "http://localhost:11434").rstrip("/")
    ollama_embed_model = env.get("OLLAMA_EMBED_MODEL", "nomic-embed-text")

    # ------------------------------------------------------------------
    # 1. DeepSeek chat completion (primary LLM provider)
    # ------------------------------------------------------------------
    print("=" * 60)
    print("1) DeepSeek chat completion")
    print("=" * 60)
    try:
        if not deepseek_key or deepseek_key.startswith("sk-your"):
            raise RuntimeError(
                "DEEPSEEK_API_KEY is missing or still a placeholder in .env — "
                "set a real key first."
            )

        data = post_json(
            f"{deepseek_base}/chat/completions",
            headers={
                "Authorization": f"Bearer {deepseek_key}",
                "Content-Type": "application/json",
            },
            payload={
                "model": deepseek_model,
                "messages": [
                    {"role": "system", "content": "You are a helpful assistant"},
                    {"role": "user", "content": "Hello"},
                ],
                "stream": False,
                "reasoning_effort": "high",
                "thinking": {"type": "enabled"},
            },
        )
        reply = data["choices"][0]["message"]["content"]
        print(f"OK  model={deepseek_model}")
        print(f"    reply: {reply[:200]}")
    except Exception as exc:
        print(f"FAIL {type(exc).__name__}: {exc}")

    # ------------------------------------------------------------------
    # 2. Embeddings via the configured EMBEDDING_PROVIDER (pgvector search)
    # ------------------------------------------------------------------
    print()
    print("=" * 60)
    print(f"2) Embeddings via EMBEDDING_PROVIDER={embed_provider}")
    print("=" * 60)
    try:
        text = "Explain how LLMs generate human-like text."

        if embed_provider == "ollama":
            data = post_json(
                f"{ollama_base}/api/embed",
                headers={"Content-Type": "application/json"},
                payload={"model": ollama_embed_model, "input": text},
            )
            embedding = data["embeddings"][0]

        elif embed_provider == "openai":
            if not openai_key or openai_key.startswith("your"):
                raise RuntimeError(
                    "OPENAI_API_KEY is missing or still a placeholder in .env — "
                    "set a real key first."
                )
            data = post_json(
                "https://api.openai.com/v1/embeddings",
                headers={
                    "Authorization": f"Bearer {openai_key}",
                    "Content-Type": "application/json",
                },
                payload={"input": text, "model": embed_model},
            )
            embedding = data["data"][0]["embedding"]

        else:
            raise RuntimeError(
                f"Unsupported EMBEDDING_PROVIDER: {embed_provider!r}. "
                "Use 'ollama' or 'openai'."
            )

        used_model = ollama_embed_model if embed_provider == "ollama" else embed_model
        print(f"OK  model={used_model}")
        print(f"    dimensions={len(embedding)}")
        print(f"    first 5 values: {embedding[:5]}")
    except Exception as exc:
        print(f"FAIL {type(exc).__name__}: {exc}")

    print()
    print("Done. If a step failed, fix the error shown above and the values in .env.")


if __name__ == "__main__":
    main()