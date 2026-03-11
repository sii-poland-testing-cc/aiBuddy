from typing import List
from pydantic_settings import BaseSettings


class Settings(BaseSettings):
    # App
    APP_ENV: str = "development"
    SECRET_KEY: str = "change-me-in-production"

    # CORS
    CORS_ORIGINS: List[str] = ["http://localhost:3000"]

    # LLM provider — "bedrock" (default) or "anthropic"
    LLM_PROVIDER: str = "bedrock"

    # Amazon Bedrock
    AWS_REGION: str = "eu-central-1"
    AWS_ACCESS_KEY_ID: str = ""
    AWS_SECRET_ACCESS_KEY: str = ""
    BEDROCK_MODEL_ID: str = "anthropic.claude-3-5-sonnet-20241022-v2:0"
    BEDROCK_EMBED_MODEL_ID: str = "amazon.titan-embed-text-v2:0"

    # Anthropic API (used when LLM_PROVIDER="anthropic")
    ANTHROPIC_API_KEY: str = ""
    ANTHROPIC_MODEL_ID: str = "claude-sonnet-4-6"

    # Vector store (local Chroma by default, swap to pgvector in prod)
    VECTOR_STORE_TYPE: str = "chroma"          # "chroma" | "pgvector"
    CHROMA_PERSIST_DIR: str = "./data/chroma"

    # PostgreSQL (for projects & file metadata)
    DATABASE_URL: str = "sqlite+aiosqlite:///./data/ai_buddy.db"

    # File uploads
    UPLOAD_DIR: str = "./data/uploads"
    MAX_UPLOAD_MB: int = 50
    ALLOWED_EXTENSIONS: List[str] = [".xlsx", ".csv", ".json", ".pdf", ".feature", ".txt", ".md", ".docx"]

    class Config:
        env_file = ".env"
        env_file_encoding = "utf-8"


settings = Settings()
