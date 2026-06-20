"""Faster-Whisper ASR service with session audio buffering."""

from __future__ import annotations

import asyncio
import base64
import logging
import time
from dataclasses import dataclass, field

from .audio_util import convert_to_wav_16k_mono, pcm_rms_energy

logger = logging.getLogger(__name__)

_model = None
_model_lock = asyncio.Lock()
_loaded = False


@dataclass
class SessionAudioBuffer:
    """Per-session audio accumulator with simple energy-based VAD."""

    chunks: list[bytes] = field(default_factory=list)
    mime_type: str = "audio/webm"
    last_voice_at: float = field(default_factory=time.time)
    silence_ms: int = 0
    energy_threshold: float = 500.0
    silence_limit_ms: int = 900

    def add_chunk(self, data: bytes, mime_type: str | None = None) -> None:
        if mime_type:
            self.mime_type = mime_type
        self.chunks.append(data)
        energy = pcm_rms_energy(data)
        now = time.time()
        if energy >= self.energy_threshold:
            self.last_voice_at = now
            self.silence_ms = 0
        else:
            self.silence_ms = int((now - self.last_voice_at) * 1000)

    def get_combined(self) -> bytes:
        return b"".join(self.chunks)

    def should_finalize(self) -> bool:
        return self.silence_ms >= self.silence_limit_ms and len(self.chunks) > 0

    def clear(self) -> None:
        self.chunks.clear()
        self.silence_ms = 0


def is_loaded() -> bool:
    return _loaded


async def warmup() -> bool:
    """Load Whisper model. Returns True if successful."""
    global _model, _loaded
    async with _model_lock:
        if _loaded:
            return True
        try:
            from faster_whisper import WhisperModel
            from ..core.config import settings

            _model = WhisperModel(
                settings.whisper_model,
                device=settings.whisper_device,
                compute_type=settings.whisper_compute_type,
            )
            _loaded = True
            logger.info(
                "Whisper model loaded: %s on %s",
                settings.whisper_model,
                settings.whisper_device,
            )
            return True
        except Exception as e:
            logger.warning("Failed to load Whisper model: %s", e)
            return False


async def transcribe_audio(
    audio_bytes: bytes,
    mime_type: str = "audio/webm",
    partial: bool = False,
) -> tuple[str, float]:
    """Transcribe audio bytes. Returns (text, confidence)."""
    if not await warmup():
        return "", 0.0

    wav = convert_to_wav_16k_mono(audio_bytes, mime_type)
    if not wav:
        wav = audio_bytes

    t0 = time.monotonic()
    try:
        segments, _info = _model.transcribe(
            wav,
            language="en",
            beam_size=1 if partial else 3,
            vad_filter=True,
        )
        texts = []
        confidences = []
        for seg in segments:
            texts.append(seg.text.strip())
            if seg.avg_logprob:
                confidences.append(min(1.0, max(0.0, 1.0 + seg.avg_logprob)))
        text = " ".join(texts).strip()
        confidence = sum(confidences) / len(confidences) if confidences else 0.85
        logger.info(
            "[voice] asr latency=%.0fms partial=%s chars=%d",
            (time.monotonic() - t0) * 1000,
            partial,
            len(text),
        )
        return text, confidence
    except Exception as e:
        logger.warning("Whisper transcription failed: %s", e)
        return "", 0.0


def decode_chunk(audio_base64: str) -> bytes:
    return base64.b64decode(audio_base64)
