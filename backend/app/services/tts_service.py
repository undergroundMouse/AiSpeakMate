"""TTS service — iFlytek primary, Edge-TTS fallback."""

import base64
import io
import logging
import re

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
MAX_SEGMENT_LEN = 400


def _split_for_tts(text: str, max_len: int = MAX_SEGMENT_LEN) -> list[str]:
    """Split long replies by sentence boundaries for provider limits."""
    cleaned = text.strip()
    if not cleaned:
        return []
    if len(cleaned) <= max_len:
        return [cleaned]

    sentences = re.split(r"(?<=[.!?])\s+", cleaned)
    chunks: list[str] = []
    buf = ""
    for sentence in sentences:
        if not sentence:
            continue
        candidate = f"{buf} {sentence}".strip() if buf else sentence
        if len(candidate) <= max_len:
            buf = candidate
            continue
        if buf:
            chunks.append(buf)
        if len(sentence) <= max_len:
            buf = sentence
        else:
            words = sentence.split()
            part = ""
            for word in words:
                candidate = f"{part} {word}".strip() if part else word
                if len(candidate) <= max_len:
                    part = candidate
                else:
                    if part:
                        chunks.append(part)
                    part = word
            buf = part
    if buf:
        chunks.append(buf)
    return chunks or [cleaned]


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


async def _synthesize_segment(text: str, voice: str, rate: str) -> bytes | None:
    if iflytek_tts_service.is_configured():
        audio = await iflytek_tts_service.synthesize_mp3(text, voice_key=voice)
        if audio:
            return audio
        logger.warning("iFlytek TTS returned no audio for segment, falling back to Edge-TTS")
    return await _edge_tts_mp3(text, voice, rate)


async def _synthesize_mp3(text: str, voice: str, rate: str) -> bytes | None:
    """Synthesize a single MP3 clip. Only valid for text within one TTS segment."""
    segments = _split_for_tts(text)
    if not segments:
        return None
    if len(segments) > 1:
        logger.warning(
            "Text spans %d TTS segments; use text_to_speech_stream() to avoid broken MP3 joins",
            len(segments),
        )
    audio = await _synthesize_segment(segments[0], voice, rate)
    return audio


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
    """Yield one valid base64 MP3 blob per TTS segment (never raw-concat MP3)."""
    for segment in _split_for_tts(text):
        audio_bytes = await _synthesize_segment(segment, voice, rate)
        if audio_bytes:
            yield base64.b64encode(audio_bytes).decode("utf-8")
