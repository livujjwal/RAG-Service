from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    PROJECT_NAME: str = "RAG Engine API"
    API_V1_STR: str = "/api/v1"
    DEBUG: bool = False

    # Database & Redis Settings
    DATABASE_URL: str = (
        "postgresql+asyncpg://postgres:mysecretpassword@localhost:5434/rag_db"
    )
    REDIS_URL: str = "redis://localhost:6379/0"

    # JWT Settings
    SECRET_KEY: str = "your-super-secret-jwt-key"
    ALGORITHM: str = "HS256"
    ACCESS_TOKEN_EXPIRE_MINUTES: int = 60 * 24 * 7  # 7 days expiration

    # AI Provider Settings
    DEFAULT_AI_PROVIDER: str = "openai"
    OPENAI_API_KEY: str = ""
    DEFAULT_AI_API_KEY: str = ""

    # Storage Settings
    STORAGE_BACKEND: str = "local"  # "local" or "s3"
    LOCAL_UPLOAD_DIR: str = "uploads"

    # AWS / S3 Settings (used when STORAGE_BACKEND="s3")
    AWS_ACCESS_KEY_ID: str | None = None
    AWS_SECRET_ACCESS_KEY: str | None = None
    AWS_REGION_NAME: str = "us-east-1"
    S3_BUCKET_NAME: str | None = None
    AWS_ENDPOINT_URL: str | None = None

    # Reads from a .env file if it exists
    model_config = SettingsConfigDict(env_file=".env", extra="ignore")


settings = Settings()
