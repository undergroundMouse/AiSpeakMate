"""iFlytek ISE (Intelligent Speech Evaluation) integration."""

from __future__ import annotations

import asyncio
import base64
import json
import logging
import xml.etree.ElementTree as ET

import websockets

from ..core.config import settings
from .iflytek_tts_service import build_auth_url as _build_iflytek_auth_url
from .iflytek_tts_service import is_configured
from .pronunciation_result import PhonemeResult, PronunciationResult

logger = logging.getLogger(__name__)

ISE_TIMEOUT_SECONDS = 45
AUDIO_CHUNK_SIZE = 1280


def is_ise_configured() -> bool:
    """Reuse iFlytek open-platform credentials (same as TTS)."""
    return is_configured()


def _build_ise_auth_url() -> str:
    return _build_iflytek_auth_url(
        host=settings.iflytek_ise_host,
        path=settings.iflytek_ise_path,
    )


def _wav_to_pcm(wav_bytes: bytes) -> bytes | None:
    if not wav_bytes:
        return None
    if wav_bytes[:4] != b"RIFF":
        return wav_bytes
    offset = 12
    while offset + 8 <= len(wav_bytes):
        chunk_id = wav_bytes[offset:offset + 4]
        chunk_size = int.from_bytes(wav_bytes[offset + 4:offset + 8], "little")
        if chunk_id == b"data":
            start = offset + 8
            return wav_bytes[start:start + chunk_size]
        offset += 8 + chunk_size
    if len(wav_bytes) > 44:
        return wav_bytes[44:]
    return None


def _format_reference_text(reference_text: str) -> str:
    return f"\ufeff[content]\n{reference_text.strip()}"


def _score_attr(element: ET.Element | None, *keys: str, default: float = 0.0) -> float:
    if element is None:
        return default
    for key in keys:
        raw = element.get(key)
        if raw is not None and raw != "":
            try:
                return float(raw)
            except ValueError:
                continue
    return default


def _parse_ise_xml(xml_text: str) -> PronunciationResult | None:
    try:
        root = ET.fromstring(xml_text)
    except ET.ParseError as exc:
        logger.warning("iFlytek ISE XML parse failed: %s", exc)
        return None

    score_node = None
    for tag in ("read_sentence", "read_word", "read_chapter"):
        for node in root.iter(tag):
            if node.get("total_score") is not None:
                score_node = node
                break
        if score_node is not None:
            break
    if score_node is None:
        for node in root.iter("rec_paper"):
            if node.get("total_score") is not None:
                score_node = node
                break
    if score_node is None:
        return None

    overall = _score_attr(score_node, "total_score")
    pronunciation = _score_attr(
        score_node, "accuracy_score", "phone_score", default=overall,
    )
    fluency = _score_attr(score_node, "fluency_score", default=overall)
    completeness = _score_attr(score_node, "integrity_score", default=overall)
    prosody = _score_attr(
        score_node, "standard_score", "emotion_score", default=fluency,
    )

    phonemes: list[PhonemeResult] = []
    for word_el in root.iter("word"):
        word_text = (word_el.get("content") or "").strip()
        if not word_text or word_text in {"sil", "silv", "fil"}:
            continue
        word_score = int(_score_attr(word_el, "total_score", default=overall))
        word_beg = int(float(word_el.get("beg_pos", 0) or 0))
        word_end = int(float(word_el.get("end_pos", 0) or 0))

        sylls = list(word_el.findall("syll"))
        if not sylls:
            phonemes.append(PhonemeResult(
                word=word_text,
                word_score=word_score,
                phoneme=word_text,
                phoneme_score=word_score,
                is_error=word_score < 60,
                suggested_phoneme=f"{word_text} (注意发音)" if word_score < 60 else None,
                start_time_ms=word_beg,
                end_time_ms=word_end,
            ))
            continue

        for syll in sylls:
            syll_content = (syll.get("content") or "").strip()
            if syll_content in {"sil", "silv", "fil"}:
                continue
            syll_score = int(_score_attr(syll, "syll_score", "phone_score", default=word_score))
            serr = int(syll.get("serr_msg", "0") or 0)
            syll_err = serr in {1, 2049}
            phones = list(syll.findall("phone"))
            if phones:
                for phone in phones:
                    ph = (phone.get("content") or syll_content or "?").strip()
                    if ph in {"sil", "silv", "fil"}:
                        continue
                    dp = int(phone.get("dp_message", "0") or 0)
                    is_err = dp != 0 or syll_err
                    ph_score = max(40, syll_score - (20 if is_err else 0))
                    beg = int(float(phone.get("beg_pos", word_beg) or word_beg))
                    end = int(float(phone.get("end_pos", word_end) or word_end))
                    phonemes.append(PhonemeResult(
                        word=word_text,
                        word_score=word_score,
                        phoneme=ph,
                        phoneme_score=ph_score,
                        is_error=is_err,
                        suggested_phoneme=f"{ph} (注意发音)" if is_err else None,
                        start_time_ms=beg,
                        end_time_ms=end,
                    ))
            else:
                phonemes.append(PhonemeResult(
                    word=word_text,
                    word_score=word_score,
                    phoneme=syll_content or word_text,
                    phoneme_score=syll_score,
                    is_error=syll_err,
                    suggested_phoneme=f"{syll_content} (注意发音)" if syll_err else None,
                    start_time_ms=int(float(syll.get("beg_pos", word_beg) or word_beg)),
                    end_time_ms=int(float(syll.get("end_pos", word_end) or word_end)),
                ))

    overall_i = min(100, max(0, int(round(overall))))
    advice = None
    if overall_i < 70:
        advice = "发音需要加强，建议放慢语速并注意单词重音。"
    elif overall_i >= 85:
        advice = "发音很好，继续保持！"

    return PronunciationResult(
        overall_score=overall_i,
        pronunciation_score=min(100, max(0, int(round(pronunciation)))),
        fluency_score=min(100, max(0, int(round(fluency)))),
        completeness_score=min(100, max(0, int(round(completeness)))),
        prosody_score=min(100, max(0, int(round(prosody)))),
        advice=advice,
        phonemes=phonemes,
        source="iflytek_ise",
    )


async def _evaluate_once(
    pcm_bytes: bytes,
    reference_text: str,
    category: str,
) -> PronunciationResult | None:
    from .iflytek_tts_service import _app_id

    url = _build_ise_auth_url()
    formatted_text = _format_reference_text(reference_text)
    final_xml: str | None = None

    async with websockets.connect(url, open_timeout=ISE_TIMEOUT_SECONDS) as ws:
        ssb_frame = {
            "common": {"app_id": _app_id()},
            "business": {
                "sub": "ise",
                "ent": "en_vip",
                "category": category,
                "cmd": "ssb",
                "text": formatted_text,
                "ttp_skip": True,
                "aue": "raw",
                "auf": "audio/L16;rate=16000",
                "rst": "entirety",
                "ise_unite": "1",
                "extra_ability": "multi_dimension",
                "tte": "utf-8",
            },
            "data": {"status": 0},
        }
        await ws.send(json.dumps(ssb_frame))

        chunks = [
            pcm_bytes[i:i + AUDIO_CHUNK_SIZE]
            for i in range(0, len(pcm_bytes), AUDIO_CHUNK_SIZE)
        ] or [b""]

        for idx, chunk in enumerate(chunks):
            is_first = idx == 0
            is_last = idx == len(chunks) - 1
            auw_frame = {
                "business": {
                    "cmd": "auw",
                    "aus": 1 if is_first else (4 if is_last else 2),
                },
                "data": {
                    "status": 2 if is_last else 1,
                    "encoding": "raw",
                    "data_type": 1,
                    "data": base64.b64encode(chunk).decode("utf-8"),
                },
            }
            await ws.send(json.dumps(auw_frame))

        async for message in ws:
            payload = json.loads(message)
            code = payload.get("code", -1)
            if code != 0:
                logger.warning(
                    "iFlytek ISE error %s: %s",
                    code,
                    payload.get("message", "unknown error"),
                )
                return None

            data = payload.get("data") or {}
            if data.get("data"):
                try:
                    final_xml = base64.b64decode(data["data"]).decode("utf-8")
                except Exception as exc:
                    logger.warning("iFlytek ISE result decode failed: %s", exc)
                    return None

            if data.get("status") == 2:
                break

    if not final_xml:
        return None
    return _parse_ise_xml(final_xml)


async def evaluate_pronunciation(
    audio_wav: bytes,
    reference_text: str,
    language: str = "en-US",
) -> PronunciationResult | None:
    """Call iFlytek ISE streaming API. Returns None on failure."""
    if not is_ise_configured():
        logger.debug("iFlytek ISE not configured")
        return None
    if not audio_wav or not reference_text.strip():
        return None

    pcm = _wav_to_pcm(audio_wav)
    if not pcm:
        logger.warning("iFlytek ISE: failed to extract PCM from audio")
        return None

    words = reference_text.strip().split()
    category = "read_word" if len(words) <= 1 else "read_sentence"

    try:
        return await asyncio.wait_for(
            _evaluate_once(pcm, reference_text, category),
            timeout=ISE_TIMEOUT_SECONDS,
        )
    except asyncio.TimeoutError:
        logger.warning("iFlytek ISE timed out after %ss", ISE_TIMEOUT_SECONDS)
        return None
    except Exception as exc:
        logger.warning("iFlytek ISE request failed: %s", exc)
        return None
