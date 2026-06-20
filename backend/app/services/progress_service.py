"""Service layer for computing and storing user progress data."""

import uuid
from datetime import date, datetime, timezone

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from ..models.evaluation import GrammarError, PhonemeScore, PronunciationEvaluation
from ..models.progress import UserProgressSnapshot, UserWeaknessRecord
from ..models.session import Session, Utterance


async def generate_progress_snapshot(
    db: AsyncSession,
    session_id: uuid.UUID,
) -> UserProgressSnapshot | None:
    """Compute and persist a progress snapshot for the completed session."""
    # Get session info
    result = await db.execute(select(Session).where(Session.id == session_id))
    session = result.scalar_one_or_none()
    if not session or session.status != "completed":
        return None

    user_id = session.user_id
    today = date.today()

    # Get all user utterances in this session
    utt_result = await db.execute(
        select(Utterance).where(
            Utterance.session_id == session_id,
            Utterance.speaker == "user",
        )
    )
    user_utterances = utt_result.scalars().all()
    utterance_count = len(user_utterances)

    if utterance_count == 0:
        return None

    # Get pronunciation evaluations for this session
    pron_q = await db.execute(
        select(PronunciationEvaluation)
        .join(Utterance, Utterance.id == PronunciationEvaluation.utterance_id)
        .where(Utterance.session_id == session_id)
    )
    pron_evals = pron_q.scalars().all()

    # Compute average scores from actual evaluations only
    has_pron_evals = bool(pron_evals)
    if has_pron_evals:
        avg_pron = sum(e.overall_score for e in pron_evals) // len(pron_evals)
        avg_fluency = sum(e.fluency_score or 0 for e in pron_evals) // len(pron_evals)
    else:
        avg_pron = 0
        avg_fluency = 0

    # Count grammar errors
    grammar_q = await db.execute(
        select(func.count(GrammarError.id))
        .join(Utterance, Utterance.id == GrammarError.utterance_id)
        .where(
            Utterance.session_id == session_id,
            GrammarError.is_expression_issue == False,
        )
    )
    total_grammar_errors = grammar_q.scalar() or 0
    grammar_score = max(0, 80 - total_grammar_errors * 5)

    # Compute vocabulary score from actual text diversity
    vocab_score = _compute_vocabulary_score(user_utterances)

    interaction_score = min(100, utterance_count * 10)

    if has_pron_evals:
        total_score = (
            avg_pron * 0.35 + avg_fluency * 0.25 + grammar_score * 0.25 + vocab_score * 0.15
        )
        dimension_scores = {
            "fluency": min(100, avg_fluency),
            "vocabulary": min(100, vocab_score),
            "grammar": min(100, grammar_score),
            "pronunciation": min(100, avg_pron),
            "interaction": interaction_score,
        }
    else:
        total_score = grammar_score * 0.55 + vocab_score * 0.30 + interaction_score * 0.15
        dimension_scores = {
            "vocabulary": min(100, vocab_score),
            "grammar": min(100, grammar_score),
            "interaction": interaction_score,
        }
    total_score = int(min(100, max(0, total_score)))

    # Check if a snapshot already exists for today
    existing_q = await db.execute(
        select(UserProgressSnapshot).where(
            UserProgressSnapshot.user_id == user_id,
            UserProgressSnapshot.snapshot_date == today,
        )
    )
    existing = existing_q.scalar_one_or_none()

    if existing:
        # Update existing: average with new scores
        existing.total_score = (existing.total_score + total_score) // 2
        existing.dimension_scores = {
            k: (existing.dimension_scores.get(k, 50) + dimension_scores.get(k, 50)) // 2
            for k in set(existing.dimension_scores) | set(dimension_scores)
        }
        existing.session_count += 1
        existing.total_duration_seconds += session.duration_seconds or 0
        snapshot = existing
    else:
        snapshot = UserProgressSnapshot(
            user_id=user_id,
            snapshot_date=today,
            total_score=total_score,
            dimension_scores=dimension_scores,
            session_count=1,
            total_duration_seconds=session.duration_seconds or 0,
        )
        db.add(snapshot)

    await db.commit()
    await db.refresh(snapshot)
    return snapshot


async def update_weakness_records(
    db: AsyncSession,
    session_id: uuid.UUID,
) -> list[UserWeaknessRecord]:
    """Aggregate phoneme and grammar errors from the session and update weakness records."""
    # Get session info
    result = await db.execute(select(Session).where(Session.id == session_id))
    session = result.scalar_one_or_none()
    if not session:
        return []

    user_id = session.user_id
    today = date.today()
    period_start = today.replace(day=1)  # Start of current month
    records: list[UserWeaknessRecord] = []

    # Aggregate phoneme errors
    phoneme_q = await db.execute(
        select(PhonemeScore.phoneme, func.count(PhonemeScore.id).label("cnt"))
        .join(PronunciationEvaluation)
        .join(Utterance, Utterance.id == PronunciationEvaluation.utterance_id)
        .where(
            Utterance.session_id == session_id,
            PhonemeScore.is_error == True,
        )
        .group_by(PhonemeScore.phoneme)
        .order_by(func.count(PhonemeScore.id).desc())
        .limit(10)
    )
    for row in phoneme_q.all():
        records.append(
            await _upsert_weakness(
                db, user_id, period_start, today,
                category="pronunciation",
                item=f"phoneme {row[0]}",
                error_count=row[1],
                trend="stable",
            )
        )

    # Aggregate grammar error types
    grammar_q = await db.execute(
        select(GrammarError.error_type, func.count(GrammarError.id).label("cnt"))
        .join(Utterance, Utterance.id == GrammarError.utterance_id)
        .where(
            Utterance.session_id == session_id,
            GrammarError.is_expression_issue == False,
        )
        .group_by(GrammarError.error_type)
        .order_by(func.count(GrammarError.id).desc())
        .limit(10)
    )
    for row in grammar_q.all():
        records.append(
            await _upsert_weakness(
                db, user_id, period_start, today,
                category="grammar",
                item=f"{row[0]}",
                error_count=row[1],
                trend="stable",
            )
        )

    await db.commit()
    return records


async def _upsert_weakness(
    db: AsyncSession,
    user_id: uuid.UUID,
    period_start: date,
    period_end: date,
    category: str,
    item: str,
    error_count: int,
    trend: str,
) -> UserWeaknessRecord:
    """Insert or update a weakness record for the given period."""
    # Check if record exists for this period
    existing_q = await db.execute(
        select(UserWeaknessRecord).where(
            UserWeaknessRecord.user_id == user_id,
            UserWeaknessRecord.period_start == period_start,
            UserWeaknessRecord.period_end == period_end,
            UserWeaknessRecord.category == category,
            UserWeaknessRecord.item == item,
        )
    )
    existing = existing_q.scalar_one_or_none()

    if existing:
        # The error_count accumulates within the period.
        # Trend compares the newly added portion vs the previous total to gauge
        # whether the user is making more or fewer errors of this type.
        new_total = existing.error_count + error_count
        # If the new errors are fewer than 20% of the existing total, improving
        if error_count < existing.error_count * 0.2:
            existing.trend = "improving"
        elif error_count > existing.error_count * 0.5:
            existing.trend = "worsening"
        else:
            existing.trend = "stable"
        existing.error_count = new_total
        record = existing
    else:
        record = UserWeaknessRecord(
            user_id=user_id,
            period_start=period_start,
            period_end=period_end,
            category=category,
            item=item,
            error_count=error_count,
            trend="stable",
        )
        db.add(record)

    await db.flush()
    return record


def _compute_vocabulary_score(utterances: list) -> int:
    """Compute vocabulary diversity score from user utterances.

    Uses Type-Token Ratio (TTR) with a sliding window for stability,
    plus word-length complexity as a secondary factor.
    """
    if not utterances:
        return 0

    all_words: list[str] = []
    for u in utterances:
        text = u.text if hasattr(u, 'text') else str(u)
        words = [w.strip(".,!?;:\"'()").lower() for w in text.split()]
        all_words.extend(w for w in words if w and len(w) > 1)

    if not all_words:
        return 50

    total = len(all_words)
    unique = len(set(all_words))

    # TTR (unique / total) — typical range for English learners: 0.4–0.85
    ttr = unique / max(total, 1)

    # Average word length complexity (longer words → richer vocabulary)
    avg_len = sum(len(w) for w in all_words) / max(total, 1)
    # avg_len 4–5 is typical for intermediate; above 5 is advanced
    length_factor = min(1.0, max(0.0, (avg_len - 3.0) / 3.0))

    # Combine TTR (70%) + length complexity (30%) → 0–100 scale
    raw = (ttr * 0.7 + length_factor * 0.3) * 100
    return int(max(0, min(100, raw)))
