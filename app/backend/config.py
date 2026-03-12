from pydantic_settings import BaseSettings

class Settings(BaseSettings):
    database_url: str = "postgresql://genealogy_user:genealogy_password@postgres:5432/genealogy_db"
    upload_directory: str = "/app/uploads"
    max_upload_size: int = 1000 * 1024 * 1024  # 1000MB
    allowed_origins: str = ""

    # LLM Provider — "ollama" or "openai"
    llm_provider: str = "ollama"

    # OpenAI settings (kept as fallback)
    openai_api_key: str = ""
    openai_model: str = "gpt-4o"

    # Ollama settings
    ollama_base_url: str = "http://ollama:11434"
    ollama_chat_model: str = "llama3.2"
    ollama_embed_model: str = "nomic-embed-text"

    # Shared LLM settings
    embedding_dimension: int = 768  # nomic-embed-text uses 768
    temperature: float = 0.1
    max_tokens: int = 500

    class Config:
        env_file = ".env"

settings = Settings()