"""Unified pronunciation evaluation: SpeechSuper + text-analysis fallback."""

from __future__ import annotations

import logging

from sqlalchemy.ext.asyncio import AsyncSession

from ..models.evaluation import PhonemeScore, PronunciationEvaluation
from ..models.session import Utterance
from .audio_util import convert_to_wav_16k_mono
from .speechsuper_service import evaluate_pronunciation as speechsuper_evaluate

logger = logging.getLogger(__name__)


async def store_pronunciation_evaluation(
    db: AsyncSession,
    utterance: Utterance,
    text: str,
    audio_bytes: bytes | None = None,
    audio_mime: str = "audio/webm",
    use_speechsuper: bool = True,
) -> PronunciationEvaluation:
    """Evaluate and persist pronunciation for an utterance."""
    from ..api.ws import (
        _analyze_text,
        _get_word_phonemes,
        _score_word_pronunciation,
    )

    result = None
    if use_speechsuper and audio_bytes:
        wav = convert_to_wav_16k_mono(audio_bytes, audio_mime)
        if wav:
            result = await speechsuper_evaluate(wav, text)

    if result:
        evaluation = PronunciationEvaluation(
            utterance_id=utterance.id,
            overall_score=result.overall_score,
            pronunciation_score=result.pronunciation_score,
            fluency_score=result.fluency_score,
            completeness_score=result.completeness_score,
            prosody_score=result.prosody_score,
            advice=result.advice,
            source="speechsuper",
        )
        db.add(evaluation)
        await db.flush()

        if result.phonemes:
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
        else:
            _add_text_phonemes(db, evaluation, text, _get_word_phonemes, _score_word_pronunciation)

        await db.commit()
        await db.refresh(evaluation)
        logger.info("Pronunciation eval source=speechsuper score=%s", result.overall_score)
        return evaluation

    # Text-analysis fallback
    analysis = _analyze_text(text)
    evaluation = PronunciationEvaluation(
        utterance_id=utterance.id,
        overall_score=analysis["overall"],
        pronunciation_score=analysis["pronunciation_score"],
        fluency_score=analysis["fluency_score"],
        completeness_score=analysis["completeness_score"],
        prosody_score=analysis["prosody_score"],
        advice=analysis["advice"],
        source="text_analysis",
    )
    db.add(evaluation)
    await db.flush()
    _add_text_phonemes(db, evaluation, text, _get_word_phonemes, _score_word_pronunciation)
    await db.commit()
    await db.refresh(evaluation)
    logger.info("Pronunciation eval source=text-analysis score=%s", analysis["overall"])
    return evaluation


def _add_text_phonemes(db, evaluation, text, get_phonemes, score_word):
    words = [w.strip(".,!?;:\"'()") for w in text.split()]
    words = [w for w in words[:10] if w]
    for word in words:
        phonemes = get_phonemes(word)
        word_score = score_word(word)
        for i, (ph, is_diff) in enumerate(phonemes):
            ph_score = max(40, min(100, word_score - (15 if is_diff else 0)))
            db.add(PhonemeScore(
                evaluation_id=evaluation.id,
                word=word,
                word_score=word_score,
                phoneme=ph,
                phoneme_score=ph_score,
                is_error=is_diff,
                suggested_phoneme=f"{ph} (注意发音)" if is_diff else None,
                start_time_ms=i * 200,
                end_time_ms=(i + 1) * 200,
            ))
