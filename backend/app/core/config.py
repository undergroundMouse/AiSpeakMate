from pydantic_settings import BaseSettings


class Settings(BaseSettings):
    # App
    app_name: str = "AiSpeakMate"
    debug: bool = True

    # Database
    database_url: str = "postgresql+asyncpg://postgres:postgres@localhost:5432/aispeakmate"

    # Redis
    redis_url: str = "redis://localhost:6379/0"

    # JWT
    secret_key: str = "change-me-in-production"
    access_token_expire_minutes: int = 30

    # LLM — supports Groq, DeepSeek, GLM, Moonshot, DashScope
    llm_provider: str = ""       # groq | deepseek | glm | moonshot | dashscope
    llm_api_key: str = ""        # API key for the provider above
    llm_model: str = ""          # override default model (optional)
    # Legacy
    groq_api_key: str = ""
    groq_model: str = "llama-3.1-70b-versatile"

    # Pronunciation
    speechsuper_api_key: str = ""
    speechsuper_endpoint: str = "https://api.speechsuper.com"

    class Config:
        env_file = ".env"
        env_file_encoding = "utf-8"


settings = Settings()