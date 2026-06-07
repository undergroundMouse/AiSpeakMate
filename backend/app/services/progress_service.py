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

    # Compute average scores
    if pron_evals:
        avg_pron = sum(e.overall_score for e in pron_evals) // len(pron_evals)
        avg_fluency = sum(e.fluency_score or 50 for e in pron_evals) // len(pron_evals)
    else:
        avg_pron = 50
        avg_fluency = 50

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
    grammar_score = max(20, 80 - total_grammar_errors * 5)

    # Total score: weighted average
    total_score = (avg_pron * 0.35 + avg_fluency * 0.25 + grammar_score * 0.25 + 50 * 0.15)
    total_score = int(min(100, max(0, total_score)))

    dimension_scores = {
        "fluency": min(100, avg_fluency),
        "vocabulary": 50,  # placeholder — real TTR calculation would go here
        "grammar": min(100, grammar_score),
        "pronunciation": min(100, avg_pron),
        "interaction": min(95, 40 + utterance_count * 10),
    }

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
        # Compare this period's count with previous to determine trend
        prev_error_count = existing.error_count
        existing.error_count += error_count
        if existing.error_count < prev_error_count:
            existing.trend = "improving"
        elif existing.error_count > prev_error_count * 1.5:
            existing.trend = "worsening"
        else:
            existing.trend = "stable"
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
