"""Streaming voice response pipeline: LLM → TTS with latency logging."""

from __future__ import annotations

import logging
import time
import uuid

from fastapi import WebSocket

from .llm_service import generate_response, generate_response_stream
from .stream_buffer import SentenceStreamBuffer
from .tts_service import text_to_speech_base64, text_to_speech_stream

logger = logging.getLogger(__name__)


async def stream_ai_response(
    websocket: WebSocket,
    session_id: str,
    system_prompt: str,
    user_message: str,
    history: list[dict],
    temperature: float,
    tts_voice: str,
    interrupt_id: str,
    cancel_check: callable,
) -> str | None:
    """Stream LLM deltas and TTS chunks. Returns full AI text or None if cancelled."""
    t0 = time.monotonic()
    buffer = SentenceStreamBuffer()
    full_text = ""
    tts_seq = 0
    first_audio = True

    async for delta in generate_response_stream(
        user_message, system_prompt, history, temperature=temperature, max_tokens=300,
    ):
        if cancel_check():
            await websocket.send_json({
                "type": "tts_cancelled",
                "payload": {"session_id": session_id, "interrupt_id": interrupt_id},
            })
            return None

        full_text += delta
        await websocket.send_json({
            "type": "llm_response_delta",
            "payload": {
                "session_id": session_id,
                "text": delta,
                "interrupt_id": interrupt_id,
                "is_sentence_end": False,
            },
        })

        for sentence in buffer.add(delta):
            if cancel_check():
                await websocket.send_json({
                    "type": "tts_cancelled",
                    "payload": {"session_id": session_id, "interrupt_id": interrupt_id},
                })
                return None
            async for audio_b64 in text_to_speech_stream(sentence, voice=tts_voice):
                if first_audio:
                    logger.info(
                        "[voice] session=%s time_to_first_audio=%.0fms",
                        session_id,
                        (time.monotonic() - t0) * 1000,
                    )
                    first_audio = False
                await websocket.send_json({
                    "type": "tts_audio_chunk",
                    "payload": {
                        "session_id": session_id,
                        "audio_base64": audio_b64,
                        "sequence": tts_seq,
                        "interrupt_id": interrupt_id,
                        "audio_mime": "audio/mp3",
                    },
                })
                tts_seq += 1

    remainder = buffer.flush()
    if remainder and not cancel_check():
        async for audio_b64 in text_to_speech_stream(remainder, voice=tts_voice):
            await websocket.send_json({
                "type": "tts_audio_chunk",
                "payload": {
                    "session_id": session_id,
                    "audio_base64": audio_b64,
                    "sequence": tts_seq,
                    "interrupt_id": interrupt_id,
                    "audio_mime": "audio/mp3",
                },
            })
            tts_seq += 1

    logger.info(
        "[voice] session=%s stream_complete latency=%.0fms chars=%d",
        session_id,
        (time.monotonic() - t0) * 1000,
        len(full_text),
    )
    return full_text.strip() or None


async def generate_ai_response_batch(
    user_message: str,
    system_prompt: str,
    history: list[dict],
    temperature: float,
    fallback_fn: callable,
    fallback_args: tuple,
) -> str:
    """Non-streaming LLM with simulated fallback."""
    ai_text = await generate_response(
        user_message, system_prompt, history, temperature=temperature, max_tokens=300,
    )
    if not ai_text:
        ai_text = fallback_fn(*fallback_args)
    return ai_text


async def send_batch_tts(
    websocket: WebSocket,
    session_id: str,
    text: str,
    tts_voice: str,
    interrupt_id: str,
) -> None:
    """Send full TTS audio (legacy path)."""
    tts_base64 = await text_to_speech_base64(text, voice=tts_voice)
    if tts_base64:
        await websocket.send_json({
            "type": "tts_audio",
            "payload": {
                "session_id": session_id,
                "stream_id": f"tts_{interrupt_id}",
                "interrupt_id": interrupt_id,
                "is_end": True,
                "text": text,
                "audio_base64": tts_base64,
                "audio_mime": "audio/mp3",
            },
        })
    else:
        await websocket.send_json({
            "type": "tts_audio",
            "payload": {
                "session_id": session_id,
                "stream_id": f"tts_{interrupt_id}",
                "interrupt_id": interrupt_id,
                "is_end": True,
                "text": text,
            },
        })
