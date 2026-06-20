"""Voice subsystem health checks."""

from fastapi import APIRouter

from ..core.config import settings
from ..services.asr_service import is_loaded
from ..services.audio_util import ffmpeg_available
from ..services.iflytek_ise_service import is_ise_configured
from ..services.iflytek_tts_service import is_configured as iflytek_tts_configured
from ..services.llm_service import is_llm_configured

router = APIRouter()


@router.get("/voice")
async def voice_health():
    return {
        "whisper": {
            "model": settings.whisper_model,
            "device": settings.whisper_device,
            "loaded": is_loaded(),
        },
        "iflytek_ise": {
            "configured": is_ise_configured(),
            "host": settings.iflytek_ise_host,
        },
        "iflytek_tts": {
            "configured": iflytek_tts_configured(),
            "host": settings.iflytek_tts_host,
        },
        "audio_conversion": {
            "ffmpeg_available": ffmpeg_available(),
        },
        "llm": {
            "configured": is_llm_configured(),
            "provider": settings.llm_provider or "groq",
        },
        "llm_provider": settings.llm_provider or "groq",
    }
