"""
check_embedding.py

Quick check of the local Ollama embedding endpoint.
Ollama must be running (ollama serve) with the model pulled:
    ollama pull nomic-embed-text

Run from the project root:
    python miscellaneous_code/check_embedding.py
"""

import requests

OLLAMA_BASE_URL = "http://localhost:11434"
EMBED_MODEL = "nomic-embed-text"

resp = requests.post(
    f"{OLLAMA_BASE_URL}/api/embed",
    json={"model": EMBED_MODEL, "input": ["first phrase", "second phrase", "third phrase"]},
    timeout=120,
)
resp.raise_for_status()
embeddings = resp.json()["embeddings"]

for index, embedding in enumerate(embeddings):
    print(
        f"data[{index}]: length={len(embedding)}, "
        f"[{embedding[0]}, {embedding[1]}, ..., {embedding[-2]}, {embedding[-1]}]"
    )
print(f"total embeddings: {len(embeddings)}")