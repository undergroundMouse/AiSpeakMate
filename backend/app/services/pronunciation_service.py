"""Unified pronunciation evaluation: iFlytek ISE + text-analysis fallback."""

from __future__ import annotations

import logging

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from ..models.evaluation import PhonemeScore, PronunciationEvaluation
from ..models.session import Utterance
from .audio_util import convert_to_wav_16k_mono
from .iflytek_ise_service import evaluate_pronunciation as iflytek_evaluate
from .iflytek_ise_service import is_ise_configured
from .text_analysis_eval import store_text_analysis_evaluation

logger = logging.getLogger(__name__)


async def _get_existing_evaluation(
    db: AsyncSession,
    utterance_id,
) -> PronunciationEvaluation | None:
    result = await db.execute(
        select(PronunciationEvaluation).where(
            PronunciationEvaluation.utterance_id == utterance_id
        )
    )
    return result.scalar_one_or_none()


async def _persist_iflytek_result(
    db: AsyncSession,
    utterance: Utterance,
    result,
) -> PronunciationEvaluation:
    evaluation = PronunciationEvaluation(
        utterance_id=utterance.id,
        overall_score=result.overall_score,
        pronunciation_score=result.pronunciation_score,
        fluency_score=result.fluency_score,
        completeness_score=result.completeness_score,
        prosody_score=result.prosody_score,
        advice=result.advice,
        source="iflytek_ise",
    )
    db.add(evaluation)
    await db.flush()

    for ph in result.phonemes:
        db.add(PhonemeScore(
            evaluation_id=evaluation.id,
            word=ph.word,
            word_score=ph.word_score,
            phoneme=ph.phoneme,
            phoneme_score=ph.phoneme_score,
            is_error=ph.is_error,
            suggested_phoneme=ph.suggested_phoneme,
            start_time_ms=ph.start_time_ms,
            end_time_ms=ph.end_time_ms,
        ))

    await db.commit()
    await db.refresh(evaluation)
    return evaluation


async def store_pronunciation_evaluation(
    db: AsyncSession,
    utterance: Utterance,
    text: str,
    audio_bytes: bytes | None = None,
    audio_mime: str = "audio/webm",
    use_iflytek: bool = True,
) -> tuple[PronunciationEvaluation | None, str | None]:
    """Evaluate pronunciation. iFlytek ISE when configured; else text analysis."""
    if not text.strip():
        logger.info("Pronunciation eval skipped: empty text for utterance %s", utterance.id)
        return None, "no_text"

    existing = await _get_existing_evaluation(db, utterance.id)
    if existing:
        logger.info("Pronunciation eval already exists for utterance %s", utterance.id)
        return existing, None

    if use_iflytek and audio_bytes and is_ise_configured():
        wav = convert_to_wav_16k_mono(audio_bytes, audio_mime)
        if wav:
            result = await iflytek_evaluate(wav, text)
            if result:
                evaluation = await _persist_iflytek_result(db, utterance, result)
                logger.info("Pronunciation eval source=iflytek_ise score=%s", result.overall_score)
                return evaluation, None
            logger.warning(
                "iFlytek ISE failed for utterance %s, falling back to text analysis",
                utterance.id,
            )
        else:
            logger.warning(
                "Audio conversion failed for utterance %s, falling back to text analysis",
                utterance.id,
            )
    elif use_iflytek and audio_bytes and not is_ise_configured():
        logger.info(
            "iFlytek ISE not configured, using text analysis for utterance %s",
            utterance.id,
        )

    evaluation = await store_text_analysis_evaluation(
        db, utterance, text, no_audio=not audio_bytes,
    )
    logger.info("Pronunciation eval source=text_analysis score=%s", evaluation.overall_score)
    return evaluation, None
