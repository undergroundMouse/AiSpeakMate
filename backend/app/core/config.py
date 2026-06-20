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

    # Pronunciation — SpeechSuper
    speechsuper_app_key: str = ""
    speechsuper_secret_key: str = ""
    speechsuper_api_key: str = ""  # legacy alias for app key
    speechsuper_endpoint: str = "https://api.speechsuper.com"

    # ASR — Faster-Whisper
    whisper_model: str = "base"
    whisper_device: str = "cpu"
    whisper_compute_type: str = "int8"

    # TTS — iFlytek Online
    iflytek_app_id: str = ""
    iflytek_api_key: str = ""
    iflytek_api_secret: str = ""
    iflytek_tts_host: str = "tts-api.xfyun.cn"
    iflytek_tts_path: str = "/v2/tts"

    @property
    def speechsuper_app_key_resolved(self) -> str:
        return self.speechsuper_app_key or self.speechsuper_api_key

    class Config:
        env_file = ".env"
        env_file_encoding = "utf-8"


settings = Settings()