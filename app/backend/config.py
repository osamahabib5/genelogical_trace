from pydantic_settings import BaseSettings


class Settings(BaseSettings):
    # Database
    database_url: str = "postgresql://genealogy_user:genealogy_password@postgres:5432/genealogy_db"

    # File upload
    upload_directory: str = "/app/uploads"
    max_upload_size: int = 1000 * 1024 * 1024  # 1000MB

    # CORS
    allowed_origins: str = ""

    # LLM Provider — "ollama", "openai", or "groq"
    llm_provider: str = "groq"

    # OpenAI
    openai_api_key: str = ""
    openai_model: str = "gpt-4o-mini"

    # Groq
    groq_api_key: str = ""
    groq_model: str = "llama-3.1-8b-instant"

    # Ollama
    ollama_base_url: str = "http://ollama:11434"
    ollama_chat_model: str = "llama3.2:1b"
    ollama_embed_model: str = "nomic-embed-text"

    # Embeddings always use Ollama (local, free)
    embedding_dimension: int = 768

    # Generation settings
    temperature: float = 0.1
    max_tokens: int = 300
    max_results: int = 8

    class Config:
        env_file = ".env"


settings = Settings()