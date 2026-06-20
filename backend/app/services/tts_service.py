"""TTS service — iFlytek primary, Edge-TTS fallback."""

import base64
import io
import logging

import edge_tts

from . import iflytek_tts_service

logger = logging.getLogger(__name__)

EDGE_VOICES = {
    "en-US-male": "en-US-GuyNeural",
    "en-US-female": "en-US-JennyNeural",
    "en-GB-male": "en-GB-RyanNeural",
    "en-GB-female": "en-GB-SoniaNeural",
}

DEFAULT_RATE = "+0%"


async def _edge_tts_mp3(text: str, voice: str, rate: str) -> bytes | None:
    voice_name = EDGE_VOICES.get(voice, EDGE_VOICES["en-US-female"])
    try:
        communicate = edge_tts.Communicate(text=text, voice=voice_name, rate=rate)
        audio_data = io.BytesIO()
        async for chunk in communicate.stream():
            if chunk["type"] == "audio":
                audio_data.write(chunk["data"])
        return audio_data.getvalue() or None
    except Exception as exc:
        logger.warning("Edge-TTS failed: %s", exc)
        return None


async def _synthesize_mp3(text: str, voice: str, rate: str) -> bytes | None:
    if iflytek_tts_service.is_configured():
        audio = await iflytek_tts_service.synthesize_mp3(text, voice_key=voice)
        if audio:
            return audio
        logger.warning("iFlytek TTS returned no audio, falling back to Edge-TTS")

    return await _edge_tts_mp3(text, voice, rate)


async def text_to_speech_base64(
    text: str,
    voice: str = "en-US-female",
    rate: str = DEFAULT_RATE,
) -> str | None:
    """Convert text to speech, return base64-encoded MP3 data."""
    audio_bytes = await _synthesize_mp3(text, voice, rate)
    if audio_bytes:
        return base64.b64encode(audio_bytes).decode("utf-8")
    return None


async def text_to_speech_stream(
    text: str,
    voice: str = "en-US-female",
    rate: str = DEFAULT_RATE,
):
    """Yield base64 MP3 chunks for a text segment."""
    audio_bytes = await _synthesize_mp3(text, voice, rate)
    if audio_bytes:
        yield base64.b64encode(audio_bytes).decode("utf-8")
