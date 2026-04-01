from pydantic_settings import BaseSettings


class Settings(BaseSettings):
    # Database
    database_url: str = "postgresql://genealogy_user:genealogy_password@postgres:5432/genealogy_db"

    # File upload
    upload_directory: str = "/app/uploads"
    max_upload_size: int = 1000 * 1024 * 1024  # 1000MB

    # CORS
    allowed_origins: str = ""

    # LLM Provider — "ollama", "openai", "groq", or "azure-foundry"
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

    # Azure Foundry / Azure AI Endpoint
    azure_foundry_endpoint: str = ""
    azure_foundry_api_key: str = ""
    azure_foundry_chat_model: str = "gpt-oss-120b"
    azure_foundry_embed_model: str = "text-embedding-3-small"

    # Embeddings dimension (768 for Ollama, 1536 for text-embedding-3-small/OpenAI)
    embedding_dimension: int = 768

    # Generation settings
    temperature: float = 0.1
    max_tokens: int = 300
    max_results: int = 8

    def __init__(self, **data):
        super().__init__(**data)
        # Set embedding dimension based on provider
        if self.llm_provider in ["openai", "azure-foundry"]:
            self.embedding_dimension = 1536
        elif self.llm_provider == "groq":
            # Groq doesn't provide embeddings, so keep default
            self.embedding_dimension = 768
        else:  # ollama
            self.embedding_dimension = 768

    class Config:
        env_file = ".env"


settings = Settings()