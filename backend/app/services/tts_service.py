"""TTS service using Edge-TTS (free Microsoft online TTS)."""

import asyncio
import base64
import io
import tempfile
import uuid

import edge_tts

VOICES = {
    "en-US-male": "en-US-GuyNeural",
    "en-US-female": "en-US-JennyNeural",
    "en-GB-male": "en-GB-RyanNeural",
    "en-GB-female": "en-GB-SoniaNeural",
}


async def text_to_speech_base64(
    text: str,
    voice: str = "en-US-female",
    rate: str = "-10%",
) -> str | None:
    """Convert text to speech, return base64-encoded MP3 data.

    Args:
        text: English text to speak
        voice: Voice name (see VOICES dict)
        rate: Speed adjustment, e.g. '-10%' for slower

    Returns:
        Base64-encoded MP3 audio, or None on failure
    """
    voice_name = VOICES.get(voice, "en-US-JennyNeural")

    try:
        communicate = edge_tts.Communicate(
            text=text,
            voice=voice_name,
            rate=rate,
        )

        # Collect audio chunks
        audio_data = io.BytesIO()
        async for chunk in communicate.stream():
            if chunk["type"] == "audio":
                audio_data.write(chunk["data"])

        audio_bytes = audio_data.getvalue()
        if audio_bytes:
            return base64.b64encode(audio_bytes).decode("utf-8")
        return None
    except Exception as e:
        print(f"Edge-TTS error: {e}")
        return None
