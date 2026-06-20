"""Audio format conversion utilities for ASR and SpeechSuper."""

import io
import logging
import subprocess
import tempfile

logger = logging.getLogger(__name__)


def convert_to_wav_16k_mono(audio_bytes: bytes, mime_type: str = "audio/webm") -> bytes | None:
    """Convert audio bytes to 16kHz mono WAV using ffmpeg if available."""
    if not audio_bytes:
        return None

    if mime_type in ("audio/wav", "audio/x-wav", "audio/wave"):
        return audio_bytes

    suffix = ".webm" if "webm" in mime_type else ".ogg" if "ogg" in mime_type else ".bin"
    try:
        with tempfile.NamedTemporaryFile(suffix=suffix, delete=False) as inp:
            inp.write(audio_bytes)
            inp_path = inp.name
        out_path = inp_path + ".wav"
        result = subprocess.run(
            [
                "ffmpeg", "-y", "-i", inp_path,
                "-ar", "16000", "-ac", "1", "-f", "wav", out_path,
            ],
            capture_output=True,
            timeout=30,
        )
        if result.returncode != 0:
            logger.warning("ffmpeg conversion failed: %s", result.stderr.decode(errors="ignore")[:200])
            return None
        with open(out_path, "rb") as f:
            return f.read()
    except FileNotFoundError:
        logger.warning("ffmpeg not found; cannot convert %s to wav", mime_type)
        return None
    except Exception as e:
        logger.warning("audio conversion error: %s", e)
        return None
    finally:
        try:
            import os
            if "inp_path" in dir() and os.path.exists(inp_path):
                os.unlink(inp_path)
            if "out_path" in dir() and os.path.exists(out_path):
                os.unlink(out_path)
        except Exception:
            pass


def pcm_rms_energy(audio_bytes: bytes) -> float:
    """Rough RMS energy for simple VAD (expects 16-bit PCM or raw amplitude)."""
    if len(audio_bytes) < 2:
        return 0.0
    try:
        import struct
        count = len(audio_bytes) // 2
        samples = struct.unpack(f"<{count}h", audio_bytes[: count * 2])
        if not samples:
            return 0.0
        return (sum(s * s for s in samples) / len(samples)) ** 0.5
    except Exception:
        return float(len(audio_bytes))
