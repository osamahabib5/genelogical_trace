from pydantic_settings import BaseSettings


class Settings(BaseSettings):
    # Database
    # Set DATABASE_URL in .env to your Supabase connection string
    # (Supabase Dashboard → Project Settings → Database → Connection string)
    database_url: str = "postgresql://postgres:postgres@localhost:5432/postgres"

    # Azure Database (for dual writing)
    azure_postgres_connection_string: str = ""

    # File upload
    upload_directory: str = "uploads"
    max_upload_size: int = 1000 * 1024 * 1024  # 1000MB

    # CORS
    allowed_origins: str = ""

    ## LLM Provider — "deepseek" (primary), "groq" (secondary),
    # "openai", "ollama", or "azure-foundry"
    llm_provider: str = "deepseek"

    # DeepSeek (primary)
    deepseek_api_key: str = ""
    deepseek_model: str = "deepseek-v4-pro"
    deepseek_base_url: str = "https://api.deepseek.com"

    # OpenAI
    openai_api_key: str = ""
    openai_model: str = "gpt-4o-mini"

    # Groq (secondary)
    groq_api_key: str = ""
    groq_model: str = "llama-3.1-8b-instant"

    # Ollama
    ollama_base_url: str = "http://localhost:11434"
    ollama_chat_model: str = "llama3.2:1b"
    ollama_embed_model: str = "nomic-embed-text"

    # Azure Foundry / Azure AI Endpoint
    # These will be mapped from AZURE_FOUNDRY_ENDPOINT, etc.
    azure_foundry_embed_version: str = ""
    azure_foundry_endpoint: str = ""
    azure_foundry_chat_endpoint: str = ""
    azure_foundry_api_key: str = ""
    azure_foundry_chat_model: str = ""
    azure_foundry_embed_model: str = "text-embedding-3-small"

    # Embeddings provider — "ollama" (default), "openai", or "azure-foundry".
    # DeepSeek and Groq do not provide embedding endpoints.
    embedding_provider: str = "ollama"
    openai_embedding_model: str = "text-embedding-3-small"

    # Texts per embedding HTTP request. Larger batches mean fewer requests
    # and less per-request overhead, but a failed request loses the whole
    # batch. Tune via EMBED_BATCH_SIZE in .env.
    embed_batch_size: int = 128

    # Embeddings dimension
    embedding_dimension: int = 768

    # Generation settings.
    # Keep max_tokens generous: DeepSeek "thinking" mode counts reasoning
    # tokens toward this budget, so a small limit yields empty answers.
    temperature: float = 0.1
    max_tokens: int = 1500
    max_results: int = 8

    # Document processing pipeline.
    # False = direct regex + Ollama embeddings (fast, no LLM calls on upload).
    # True  = DeepSeek-powered agentic cleaning (slower, more thorough).
    use_agent_processing: bool = False

    def __init__(self, **data):
        super().__init__(**data)
        
        # Set embedding dimension based on the embeddings provider
        # Note: If using Azure Foundry for embeddings, ensure it matches your deployment
        if self.embedding_provider in ["openai", "azure-foundry"]:
            self.embedding_dimension = 1536
        else:  # ollama
            self.embedding_dimension = 768

    model_config = {
        "env_file": ".env",
        "extra": "ignore",
        "case_sensitive": False
    }


settings = Settings()