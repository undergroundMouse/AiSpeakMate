"""Service for detecting and unlocking achievements automatically."""

import uuid
from datetime import date, timedelta

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from ..models.achievement import Achievement, UserAchievement
from ..models.evaluation import GrammarError, PronunciationEvaluation
from ..models.session import Session, Utterance

# Predefined achievement definitions — keyed by unique string
ACHIEVEMENT_DEFS = [
    {
        "key": "first_session",
        "title": "初次对话",
        "description": "完成首次AI对话练习",
        "icon": "🎙️",
        "condition_type": "sessions_count",
        "condition_value": 1,
    },
    {
        "key": "ten_sessions",
        "title": "坚持不懈",
        "description": "完成10次对话练习",
        "icon": "🔥",
        "condition_type": "sessions_count",
        "condition_value": 10,
    },
    {
        "key": "fifty_sessions",
        "title": "口语达人",
        "description": "完成50次对话练习",
        "icon": "⭐",
        "condition_type": "sessions_count",
        "condition_value": 50,
    },
    {
        "key": "score_80",
        "title": "发音之星",
        "description": "单次发音评分达到80分以上",
        "icon": "🌟",
        "condition_type": "score_threshold",
        "condition_value": 80,
    },
    {
        "key": "grammar_perfect",
        "title": "语法大师",
        "description": "整场对话零语法错误",
        "icon": "✅",
        "condition_type": "grammar_zero_errors",
        "condition_value": 1,
    },
    {
        "key": "streak_7",
        "title": "一周全勤",
        "description": "连续7天打卡练习",
        "icon": "📅",
        "condition_type": "streak_days",
        "condition_value": 7,
    },
]


async def ensure_achievement_defs(db: AsyncSession) -> None:
    """Make sure all predefined achievements exist in the database."""
    existing_keys = set()
    result = await db.execute(select(Achievement))
    for row in result.scalars().all():
        existing_keys.add(row.title)

    for ad in ACHIEVEMENT_DEFS:
        if ad["title"] not in existing_keys:
            db.add(Achievement(
                title=ad["title"],
                description=ad["description"],
                icon_url=ad["icon"],
                condition_type=ad["condition_type"],
                condition_value=ad["condition_value"],
            ))


async def check_and_unlock_achievements(
    db: AsyncSession,
    user_id: uuid.UUID,
    session_id: uuid.UUID,
) -> list[dict]:
    """
    Evaluate all achievement conditions for the user and unlock any
    newly met achievements. Returns a list of newly unlocked achievement info.
    """
    await ensure_achievement_defs(db)

    # Get all achievement definitions from DB
    result = await db.execute(select(Achievement))
    all_defs = {a.title: a for a in result.scalars().all()}

    # Get already unlocked achievements
    ua_result = await db.execute(
        select(UserAchievement).where(UserAchievement.user_id == user_id)
    )
    unlocked_keys = {ua.achievement_key for ua in ua_result.scalars().all()}

    # Count completed sessions
    sessions_count_result = await db.execute(
        select(func.count(Session.id)).where(
            Session.user_id == user_id,
            Session.status == "completed",
        )
    )
    total_sessions = sessions_count_result.scalar() or 0

    # Check pronunciation high scores
    has_high_score = False
    pron_result = await db.execute(
        select(PronunciationEvaluation.overall_score)
        .join(Utterance, Utterance.id == PronunciationEvaluation.utterance_id)
        .join(Session, Session.id == Utterance.session_id)
        .where(Session.user_id == user_id)
    )
    for row in pron_result.all():
        if row[0] and row[0] >= 80:
            has_high_score = True
            break

    # Check for any session with zero grammar errors
    has_perfect_session = False
    # Get all completed session IDs for this user
    session_ids_result = await db.execute(
        select(Session.id).where(
            Session.user_id == user_id,
            Session.status == "completed",
        )
    )
    for (sid,) in session_ids_result.all():
        err_count_result = await db.execute(
            select(func.count(GrammarError.id))
            .join(Utterance, Utterance.id == GrammarError.utterance_id)
            .where(
                Utterance.session_id == sid,
                GrammarError.is_expression_issue == False,
            )
        )
        if (err_count_result.scalar() or 0) == 0:
            has_perfect_session = True
            break

    # Check streak (consecutive days with sessions)
    streak = await _calculate_streak(db, user_id)

    newly_unlocked: list[dict] = []

    # Map condition_type → evaluator
    for ad in ACHIEVEMENT_DEFS:
        if ad["key"] in unlocked_keys:
            continue  # Already unlocked

        is_met = False
        if ad["condition_type"] == "sessions_count":
            is_met = total_sessions >= ad["condition_value"]
        elif ad["condition_type"] == "score_threshold":
            is_met = has_high_score
        elif ad["condition_type"] == "grammar_zero_errors":
            is_met = has_perfect_session
        elif ad["condition_type"] == "streak_days":
            is_met = streak >= ad["condition_value"]

        if is_met:
            # Find or create the DB achievement row
            db_ach = all_defs.get(ad["title"])
            if db_ach is None:
                db_ach = Achievement(
                    title=ad["title"],
                    description=ad["description"],
                    icon_url=ad["icon"],
                    condition_type=ad["condition_type"],
                    condition_value=ad["condition_value"],
                )
                db.add(db_ach)
                await db.flush()

            ua = UserAchievement(
                user_id=user_id,
                achievement_id=db_ach.id,
                achievement_key=ad["key"],
            )
            db.add(ua)
            unlocked_keys.add(ad["key"])
            newly_unlocked.append({
                "key": ad["key"],
                "title": ad["title"],
                "description": ad["description"],
                "icon": ad["icon"],
            })

    if newly_unlocked:
        await db.commit()

    return newly_unlocked


async def _calculate_streak(db: AsyncSession, user_id: uuid.UUID) -> int:
    """Calculate the current consecutive days with at least one session."""
    today = date.today()

    # Get distinct dates with completed sessions, ordered descending
    result = await db.execute(
        select(func.date(Session.started_at))
        .where(
            Session.user_id == user_id,
            Session.status == "completed",
        )
        .distinct()
        .order_by(func.date(Session.started_at).desc())
    )
    dates = [row[0] for row in result.all()]

    if not dates:
        return 0

    streak = 0
    expected = today
    for d in dates:
        if d == expected:
            streak += 1
            expected = d - timedelta(days=1)
        elif d == today and streak == 0:
            # Start counting from today
            streak = 1
            expected = today - timedelta(days=1)
        else:
            break

    return streak
