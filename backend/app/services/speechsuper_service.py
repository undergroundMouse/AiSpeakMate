"""SpeechSuper pronunciation assessment integration."""

from __future__ import annotations

import hashlib
import json
import logging
import time
import uuid
from dataclasses import dataclass, field

import httpx

from ..core.config import settings

logger = logging.getLogger(__name__)

_runtime_credentials: dict[str, str] = {}


def set_runtime_credentials(app_key: str, secret_key: str) -> None:
    _runtime_credentials["app_key"] = app_key.strip()
    _runtime_credentials["secret_key"] = secret_key.strip()


def _app_key() -> str:
    return _runtime_credentials.get("app_key") or settings.speechsuper_app_key_resolved


def _secret_key() -> str:
    return _runtime_credentials.get("secret_key") or settings.speechsuper_secret_key


@dataclass
class PhonemeResult:
    word: str
    word_score: int
    phoneme: str
    phoneme_score: int
    is_error: bool
    suggested_phoneme: str | None = None
    start_time_ms: int = 0
    end_time_ms: int = 0


@dataclass
class PronunciationResult:
    overall_score: int
    pronunciation_score: int
    fluency_score: int
    completeness_score: int
    prosody_score: int
    advice: str | None
    phonemes: list[PhonemeResult] = field(default_factory=list)
    source: str = "speechsuper"


def is_configured() -> bool:
    return bool(_app_key() and _secret_key())


def _make_sig(app_key: str, secret_key: str, timestamp: str) -> str:
    raw = f"{app_key}{timestamp}{secret_key}"
    return hashlib.sha1(raw.encode("utf-8")).hexdigest()


def _parse_response(data: dict, reference_text: str) -> PronunciationResult | None:
    """Parse SpeechSuper eval response into PronunciationResult."""
    result = data.get("result") or data.get("data", {}).get("result") or data
    if not isinstance(result, dict):
        return None

    overall = int(result.get("overall", result.get("score", 0)) or 0)
    pron = int(result.get("pronunciation", result.get("accuracy", overall)) or overall)
    fluency = int(result.get("fluency", overall) or overall)
    completeness = int(result.get("integrity", result.get("completeness", overall)) or overall)
    prosody = int(result.get("rhythm", result.get("prosody", fluency)) or fluency)

    phonemes: list[PhonemeResult] = []
    words = result.get("words") or result.get("word_scores") or []
    for w in words:
        if not isinstance(w, dict):
            continue
        word_text = w.get("word", w.get("text", ""))
        word_score = int(w.get("score", w.get("pronunciation", 70)) or 70)
        for ph in w.get("phonemes", w.get("phones", [])) or []:
            if not isinstance(ph, dict):
                continue
            ph_score = int(ph.get("score", ph.get("pronunciation", word_score)) or word_score)
            ph_symbol = ph.get("phoneme", ph.get("phone", "?"))
            span = ph.get("span") or {}
            start_ms = int((span.get("start", 0) or 0) * 1000)
            end_ms = int((span.get("end", 0) or 0) * 1000)
            is_err = ph_score < 60
            phonemes.append(PhonemeResult(
                word=word_text,
                word_score=word_score,
                phoneme=ph_symbol,
                phoneme_score=ph_score,
                is_error=is_err,
                suggested_phoneme=f"{ph_symbol} (注意发音)" if is_err else None,
                start_time_ms=start_ms,
                end_time_ms=end_ms,
            ))

    advice = None
    if overall < 70:
        advice = "Focus on clearer pronunciation — try speaking a bit slower."
    elif overall >= 85:
        advice = "Great pronunciation! Keep it up."

    return PronunciationResult(
        overall_score=min(100, max(0, overall)),
        pronunciation_score=min(100, max(0, pron)),
        fluency_score=min(100, max(0, fluency)),
        completeness_score=min(100, max(0, completeness)),
        prosody_score=min(100, max(0, prosody)),
        advice=advice,
        phonemes=phonemes,
        source="speechsuper",
    )


async def evaluate_pronunciation(
    audio_wav: bytes,
    reference_text: str,
    language: str = "en-US",
) -> PronunciationResult | None:
    """Call SpeechSuper sent.eval.promax API. Returns None on failure."""
    if not is_configured():
        logger.debug("SpeechSuper not configured")
        return None
    if not audio_wav or not reference_text.strip():
        return None

    app_key = _app_key()
    secret_key = _secret_key()
    user_id = str(uuid.uuid4())[:16]
    ts = str(int(time.time()))
    sig = _make_sig(app_key, secret_key, ts)

    core_type = "sent.eval.promax" if len(reference_text.split()) > 1 else "word.eval.promax"
    param = {
        "app": {
            "applicationId": app_key,
            "userId": user_id,
            "timestamp": ts,
            "sig": sig,
        },
        "audio": {
            "audioType": "wav",
            "channel": 1,
            "sampleBytes": 2,
            "sampleRate": 16000,
        },
        "request": {
            "coreType": core_type,
            "refText": reference_text.strip(),
            "tokenId": str(uuid.uuid4()),
        },
    }

    base = settings.speechsuper_endpoint.rstrip("/")
    url = f"{base}/{core_type}"

    try:
        async with httpx.AsyncClient(timeout=30.0) as client:
            response = await client.post(
                url,
                data={"text": json.dumps(param)},
                files={"audio": ("audio.wav", audio_wav, "audio/wav")},
            )
            response.raise_for_status()
            data = response.json()
            if data.get("errId") and data.get("errId") != 0:
                logger.warning("SpeechSuper API error: %s", data.get("error") or data)
                return None
            return _parse_response(data, reference_text)
    except Exception as e:
        logger.warning("SpeechSuper request failed: %s", e)
        return None
