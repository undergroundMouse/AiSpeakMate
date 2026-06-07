import random
import uuid
from datetime import datetime, timezone

from fastapi import APIRouter, Depends, HTTPException, UploadFile, File, Form

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from ..api.dependencies import get_current_user
from ..core.database import get_db
from ..models.evaluation import (
    PronunciationEvaluation,
    PhonemeScore,
    GrammarError,
)
from ..models.session import Session, Utterance
from ..models.user import User
from ..schemas.evaluation import (
    PronunciationEvaluateResponse,
    PronunciationDetailResponse,
    WordScoreOut,
    PhonemeScoreOut,
    ProsodyOut,
    GrammarReportResponse,
    GrammarErrorOut,
    GrammarCorrectRequest,
    GrammarCorrectResponse,
)

router = APIRouter()


# --- Pronunciation ---

@router.post(
    "/pronunciation/evaluate",
    response_model=PronunciationEvaluateResponse,
    summary="单句发音评测",
)
async def evaluate_pronunciation(
    audio: UploadFile = File(...),
    reference_text: str = Form(...),
    language: str = Form("en-US"),
    detail_level: str = Form("full"),
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """
    Evaluate pronunciation of a single sentence.
    Accepts audio upload (WAV/MP3) and returns detailed scoring.
    """
    # Simulated evaluation result
    overall = random.randint(55, 95)

    words = reference_text.split()
    word_scores = []
    for i, word in enumerate(words):
        ws = random.randint(50, 100)
        phonemes = []
        for j, ch in enumerate(word[:3]):  # simulate up to 3 phonemes per word
            ps = random.randint(40, 100)
            is_err = ps < 60
            phonemes.append(PhonemeScoreOut(
                word=word,
                word_score=ws,
                phoneme=f"/{ch}/",
                phoneme_score=ps,
                is_error=is_err,
                suggested_phoneme=f"/{ch}/" if is_err else None,
            ))
        word_scores.append(WordScoreOut(
            word=word,
            score=ws,
            phonemes=phonemes if detail_level == "full" else None,
        ))

    return PronunciationEvaluateResponse(
        overall_score=overall,
        pronunciation_score=random.randint(50, 100),
        fluency_score=random.randint(50, 100),
        completeness_score=100,
        words=word_scores if detail_level == "full" else None,
        prosody=ProsodyOut(
            intonation_score=random.randint(50, 100),
            rhythm_score=random.randint(50, 100),
            stress_errors=[],
        ),
        advice="重点练习元音发音，注意单词的重音位置。",
    )


@router.get(
    "/sessions/{session_id}/pronunciation/{utterance_id}",
    response_model=PronunciationDetailResponse,
    summary="获取对话中某句发音详情",
)
async def get_utterance_pronunciation(
    session_id: uuid.UUID,
    utterance_id: uuid.UUID,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """
    Get pronunciation evaluation detail for a specific utterance in a session.
    """
    # Verify session exists and belongs to user
    result = await db.execute(
        select(Session).where(
            Session.id == session_id,
            Session.user_id == current_user.id,
        )
    )
    session = result.scalar_one_or_none()
    if not session:
        raise HTTPException(status_code=404, detail="Session not found")

    # Get the pronunciation evaluation
    eval_result = await db.execute(
        select(PronunciationEvaluation)
        .join(Utterance)
        .where(
            Utterance.id == utterance_id,
            Utterance.session_id == session_id,
        )
    )
    evaluation = eval_result.scalar_one_or_none()
    if not evaluation:
        raise HTTPException(
            status_code=404, detail="Pronunciation evaluation not found"
        )

    # Build word scores with phoneme details
    phoneme_result = await db.execute(
        select(PhonemeScore).where(
            PhonemeScore.evaluation_id == evaluation.id
        ).order_by(PhonemeScore.id)
    )
    phoneme_scores = phoneme_result.scalars().all()

    # Group phonemes by word
    word_map: dict[str, list[PhonemeScore]] = {}
    for ps in phoneme_scores:
        word_map.setdefault(ps.word, []).append(ps)

    words = []
    for word_name, p_list in word_map.items():
        avg_score = sum(p.phoneme_score for p in p_list) // len(p_list) if p_list else 0
        words.append(WordScoreOut(
            word=word_name,
            score=avg_score,
            phonemes=[
                PhonemeScoreOut(
                    word=p.word,
                    word_score=p.word_score,
                    phoneme=p.phoneme,
                    phoneme_score=p.phoneme_score,
                    is_error=p.is_error,
                    suggested_phoneme=p.suggested_phoneme,
                    start_time_ms=p.start_time_ms,
                    end_time_ms=p.end_time_ms,
                )
                for p in p_list
            ],
        ))

    return PronunciationDetailResponse(
        utterance_id=evaluation.utterance_id,
        overall_score=evaluation.overall_score,
        pronunciation_score=evaluation.pronunciation_score,
        fluency_score=evaluation.fluency_score,
        completeness_score=evaluation.completeness_score,
        words=words,
        prosody=ProsodyOut(
            intonation_score=evaluation.prosody_score,
            rhythm_score=None,
            stress_errors=None,
        ),
        advice=evaluation.advice,
        evaluated_at=evaluation.evaluated_at,
    )


# --- Grammar ---

@router.get(
    "/sessions/{session_id}/grammar-report",
    response_model=GrammarReportResponse,
    summary="获取会话语法纠错报告",
)
async def get_grammar_report(
    session_id: uuid.UUID,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """
    Get grammar error correction report for a session.
    """
    # Verify session exists and belongs to user
    result = await db.execute(
        select(Session).where(
            Session.id == session_id,
            Session.user_id == current_user.id,
        )
    )
    session = result.scalar_one_or_none()
    if not session:
        raise HTTPException(status_code=404, detail="Session not found")

    # Get all grammar errors for utterances in this session
    errors_result = await db.execute(
        select(GrammarError)
        .join(Utterance)
        .where(Utterance.session_id == session_id)
        .order_by(GrammarError.id)
    )
    errors = errors_result.scalars().all()

    error_list = []
    for e in errors:
        if not e.is_expression_issue:
            error_list.append(GrammarErrorOut(
                utterance_id=e.utterance_id,
                original=e.original_text,
                error_type=e.error_type,
                error_span={"start": e.error_span_start, "end": e.error_span_end},
                correction=e.correction,
                corrected_sentence=e.corrected_sentence,
                explanation=e.explanation,
                severity=e.severity,
            ))

    suggestions = []
    for e in errors:
        if e.is_expression_issue:
            suggestions.append({
                "utterance_id": str(e.utterance_id),
                "original": e.original_text,
                "suggestion": e.correction,
                "reason": e.explanation or "",
            })

    return GrammarReportResponse(
        session_id=session_id,
        errors=error_list,
        optimization_suggestions=suggestions,
        total_errors=len(error_list),
        total_suggestions=len(suggestions),
    )


@router.post(
    "/grammar/correct",
    response_model=GrammarCorrectResponse,
    summary="文本即时纠错",
)
async def correct_grammar(
    req: GrammarCorrectRequest,
    current_user: User = Depends(get_current_user),
):
    """
    Instant grammar correction for given text.
    In 'light' mode only returns corrected_text without detailed errors or suggestions.
    In 'full' mode returns all errors, corrections, and expression suggestions.
    """
    text = req.text.strip()
    errors = _detect_grammar_errors(text)
    corrected = text

    # Apply corrections
    for err in sorted(errors, key=lambda x: x["error_span"]["start"], reverse=True):
        sp = err["error_span"]
        corrected = corrected[:sp["start"]] + err["correction"] + corrected[sp["end"]:]

    if req.mode == "light":
        return GrammarCorrectResponse(
            original=text,
            corrected_text=corrected if corrected != text else None,
        )

    return GrammarCorrectResponse(
        original=text,
        errors=errors,
        corrected_text=corrected if corrected != text else None,
        optimization_suggestions=_get_expression_suggestions(text),
    )


def _detect_grammar_errors(text: str) -> list[dict]:
    errors = []
    lower = text.lower()

    # Simple rule-based detection
    if "i go to" in lower and "yesterday" in lower:
        idx = lower.find("i go to")
        errors.append({
            "utterance_id": uuid.uuid4(),
            "original": text[idx:idx + len("i go to")],
            "error_type": "tense",
            "error_span": {"start": idx, "end": idx + len("i go to")},
            "correction": "I went to",
            "corrected_sentence": text[:idx] + "I went to" + text[idx + len("i go to"):],
            "explanation": "应使用过去时 'went'",
            "severity": "medium",
        })
    if "he go" in lower:
        idx = lower.find("he go")
        errors.append({
            "utterance_id": uuid.uuid4(),
            "original": text[idx:idx + 6],
            "error_type": "subject-verb agreement",
            "error_span": {"start": idx + 3, "end": idx + 5},
            "correction": "goes",
            "corrected_sentence": text[:idx + 3] + "goes" + text[idx + 5:],
            "explanation": "主语 he 为第三人称单数，动词需用 goes",
            "severity": "medium",
        })
    if "i has" in lower:
        idx = lower.find("i has")
        errors.append({
            "utterance_id": uuid.uuid4(),
            "original": text[idx:idx + 5],
            "error_type": "subject-verb agreement",
            "error_span": {"start": idx + 2, "end": idx + 5},
            "correction": "have",
            "corrected_sentence": text[:idx + 2] + "have" + text[idx + 5:],
            "explanation": "第一人称应使用 'have' 而非 'has'",
            "severity": "low",
        })
    if "two apple" in lower:
        idx = lower.find("two apple")
        errors.append({
            "utterance_id": uuid.uuid4(),
            "original": "two apple",
            "error_type": "plural",
            "error_span": {"start": idx + 4, "end": idx + 9},
            "correction": "apples",
            "corrected_sentence": text[:idx + 4] + "apples" + text[idx + 9:],
            "explanation": "'two' 后应使用复数形式 'apples'",
            "severity": "medium",
        })

    return errors


def _get_expression_suggestions(text: str) -> list[dict]:
    suggestions = []
    lower = text.lower()
    if "very good" in lower:
        suggestions.append({
            "original": "very good",
            "suggestion": "excellent / outstanding",
            "reason": "使用更高级词汇可提升表达丰富度",
        })
    if "very bad" in lower:
        suggestions.append({
            "original": "very bad",
            "suggestion": "terrible / awful",
            "reason": "使用更高级词汇可提升表达丰富度",
        })
    return suggestions