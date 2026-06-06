import random
import uuid
from datetime import datetime, timezone

from fastapi import APIRouter, Depends, HTTPException

from sqlalchemy import select, func
from sqlalchemy.ext.asyncio import AsyncSession

from ..api.dependencies import get_current_user
from ..core.database import get_db
from ..models.session import Session
from ..models.summary import SessionSummary
from ..models.achievement import UserAchievement, Achievement
from ..models.user import User
from ..schemas.summary import (
    SessionSummaryResponse,
    RadarScores,
    Highlight,
    PracticeSuggestion,
    UserProgressResponse,
    ProgressSnapshot,
    WeaknessRecord,
    AchievementListResponse,
    AchievementInfo,
    TrendPoint,
    ProgressTrendResponse,
)

router = APIRouter()


# --- Progress Trend ---

VALID_DIMENSIONS = ["fluency", "vocabulary", "grammar", "pronunciation", "interaction"]
VALID_GRANULARITIES = ["daily", "weekly"]


@router.get(
    "/progress/trend",
    response_model=ProgressTrendResponse,
    summary="获取进步趋势数据",
)
async def get_progress_trend(
    start_date: str,
    end_date: str,
    dimension: str = "all",
    granularity: str = "daily",
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """Get progress trend data with date range, dimension, and granularity filters."""
    from datetime import date as date_type, timedelta

    if dimension != "all" and dimension not in VALID_DIMENSIONS:
        raise HTTPException(400, f"Invalid dimension. Must be one of: all, {', '.join(VALID_DIMENSIONS)}")

    if granularity not in VALID_GRANULARITIES:
        raise HTTPException(400, f"Invalid granularity. Must be one of: {', '.join(VALID_GRANULARITIES)}")

    try:
        sd = date_type.fromisoformat(start_date)
        ed = date_type.fromisoformat(end_date)
    except ValueError:
        raise HTTPException(400, "Invalid date format. Use YYYY-MM-DD.")

    if sd > ed:
        raise HTTPException(400, "start_date must be before or equal to end_date")

    from ..models.progress import UserProgressSnapshot

    result = await db.execute(
        select(UserProgressSnapshot)
        .where(
            UserProgressSnapshot.user_id == current_user.id,
            UserProgressSnapshot.snapshot_date >= sd,
            UserProgressSnapshot.snapshot_date <= ed,
        )
        .order_by(UserProgressSnapshot.snapshot_date)
    )
    snapshots = result.scalars().all()

    if not snapshots:
        return ProgressTrendResponse(points=[])

    if granularity == "weekly":
        # Group by ISO week. Compute an average score per week.
        from collections import defaultdict
        week_buckets: dict[str, list[dict]] = defaultdict(list)
        for s in snapshots:
            iso_year, iso_week, _ = s.snapshot_date.isocalendar()
            week_key = f"{iso_year}-W{iso_week:02d}"
            week_buckets[week_key].append({
                "total_score": s.total_score,
                "dimension_scores": s.dimension_scores,
            })

        points: list[TrendPoint] = []
        for week_key in sorted(week_buckets.keys()):
            items = week_buckets[week_key]
            # Use Monday of that week as date
            year, week = int(week_key[:4]), int(week_key[6:])
            monday = date_type.fromisocalendar(year, week, 1)
            if dimension == "all":
                avg_score = sum(it["total_score"] for it in items) // len(items)
                points.append(TrendPoint(date=monday, score=avg_score))
            else:
                avg_dim = sum(it["dimension_scores"].get(dimension, 50) for it in items) // len(items)
                points.append(TrendPoint(date=monday, score=avg_dim, dimension=dimension))
        return ProgressTrendResponse(points=points)
    else:
        # daily
        points: list[TrendPoint] = []
        for s in snapshots:
            if dimension == "all":
                points.append(TrendPoint(date=s.snapshot_date, score=s.total_score))
            else:
                dim_score = s.dimension_scores.get(dimension, 50)
                points.append(TrendPoint(date=s.snapshot_date, score=dim_score, dimension=dimension))
        return ProgressTrendResponse(points=points)


# --- Session Summary ---

@router.get(
    "/sessions/{session_id}/summary",
    response_model=SessionSummaryResponse,
    summary="获取会话总结报告",
)
async def get_session_summary(
    session_id: uuid.UUID,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """
    Get the summary report for a completed session.
    Returns radar chart scores, highlights, and practice suggestions.
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

    # Try to get existing summary
    summary_result = await db.execute(
        select(SessionSummary).where(
            SessionSummary.session_id == session_id
        )
    )
    summary = summary_result.scalar_one_or_none()

    # Generate if not exists
    if not summary:
        radar = _generate_radar_scores()
        highlights = _generate_highlights(session.scene_id)
        suggestions = _generate_suggestions()

        summary = SessionSummary(
            session_id=session_id,
            radar_fluency=radar.fluency,
            radar_vocabulary=radar.vocabulary,
            radar_grammar=radar.grammar,
            radar_pronunciation=radar.pronunciation,
            radar_interaction=radar.interaction,
            highlights=[h.model_dump() for h in highlights],
            practice_suggestions=[s.model_dump() for s in suggestions],
            created_at=datetime.now(timezone.utc),
        )
        db.add(summary)
        await db.commit()
        await db.refresh(summary)

    return SessionSummaryResponse(
        id=summary.id,
        session_id=summary.session_id,
        radar=RadarScores(
            fluency=summary.radar_fluency or 50,
            vocabulary=summary.radar_vocabulary or 50,
            grammar=summary.radar_grammar or 50,
            pronunciation=summary.radar_pronunciation or 50,
            interaction=summary.radar_interaction or 50,
        ),
        highlights=summary.highlights or [],
        practice_suggestions=summary.practice_suggestions or [],
        share_image_url=summary.share_image_url,
        created_at=summary.created_at,
    )


def _generate_radar_scores() -> RadarScores:
    return RadarScores(
        fluency=random.randint(40, 85),
        vocabulary=random.randint(40, 85),
        grammar=random.randint(40, 85),
        pronunciation=random.randint(40, 85),
        interaction=random.randint(40, 85),
    )


def _generate_highlights(scene_id: uuid.UUID | None) -> list[Highlight]:
    highlights = [
        Highlight(
            title="发音准确",
            description="大部分单词发音清晰，元音发音基本准确。",
            example_sentence="The weather is nice today.",
        ),
        Highlight(
            title="表达流畅",
            description="对话中较少出现长时间停顿，语速适中。",
            example_sentence="I think that's a great idea.",
        ),
        Highlight(
            title="词汇运用",
            description="使用了一些中级词汇，表达较为丰富。",
            example_sentence="I'm particularly interested in this topic.",
        ),
    ]
    return highlights


def _generate_suggestions() -> list[PracticeSuggestion]:
    return [
        PracticeSuggestion(
            title="练习连读技巧",
            description="英语母语者常使用连读，建议每天跟读10分钟。",
            resource_type="video",
            resource_url="https://example.com/connected-speech-practice",
        ),
        PracticeSuggestion(
            title="积累同义替换词汇",
            description="用更丰富的词汇替代常见词汇，如用'excellent'替代'good'。",
            resource_type="article",
            resource_url="https://example.com/synonym-practice",
        ),
    ]


# --- User Progress ---

@router.get(
    "/progress",
    response_model=UserProgressResponse,
    summary="获取用户学习进度总览",
)
async def get_user_progress(
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """
    Get overall learning progress for the current user.
    """
    # Count total sessions
    session_count_result = await db.execute(
        select(func.count(Session.id)).where(
            Session.user_id == current_user.id,
            Session.status == "completed",
        )
    )
    total_sessions = session_count_result.scalar() or 0

    # TODO: In production, calculate real duration from utterances
    total_duration = total_sessions * random.randint(5, 15) * 60  # approximate seconds

    overall_score = random.randint(45, 90)
    rating = _get_rating(overall_score)

    # Generate mock snapshots
    from datetime import date, timedelta
    today = date.today()
    snapshots = []
    for i in range(7):
        d = today - timedelta(days=i * 7)
        snapshots.append(ProgressSnapshot(
            snapshot_date=d,
            total_score=min(100, overall_score - random.randint(-5, 3) * (7 - i)),
            dimension_scores={
                "fluency": random.randint(30, 80) + (7 - i) * 2,
                "vocabulary": random.randint(30, 80) + (7 - i) * 2,
                "grammar": random.randint(30, 80) + (7 - i) * 2,
                "pronunciation": random.randint(30, 80) + (7 - i) * 2,
            },
            session_count=(i + 1),
            total_duration_seconds=random.randint(300, 1800),
        ))

    # Mock weaknesses
    weaknesses = [
        WeaknessRecord(
            period_start=today - timedelta(days=30),
            period_end=today,
            category="pronunciation",
            item="/θ/",
            error_count=12,
            trend="falling",
        ),
        WeaknessRecord(
            period_start=today - timedelta(days=30),
            period_end=today,
            category="grammar",
            item="过去时",
            error_count=8,
            trend="stable",
        ),
    ]

    strengths = [
        {"area": "流利度", "score": random.randint(70, 90), "trend": "rising"},
        {"area": "词汇量", "score": random.randint(60, 85), "trend": "rising"},
    ]

    return UserProgressResponse(
        user_id=current_user.id,
        overall_rating=rating,
        total_score=overall_score,
        total_sessions=total_sessions,
        total_hours=round(total_duration / 3600, 1),
        snapshots=snapshots,
        weaknesses=weaknesses,
        strengths=strengths,
    )


def _get_rating(score: int) -> str:
    if score >= 85:
        return "B2 (高级)"
    elif score >= 70:
        return "B1 (中高级)"
    elif score >= 55:
        return "A2 (中级)"
    else:
        return "A1 (初级)"


# --- Achievements ---

@router.get(
    "/achievements",
    response_model=AchievementListResponse,
    summary="获取用户成就列表",
)
async def get_achievements(
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """
    Get the achievement list for current user.
    """
    # Predefined achievements
    predefined = [
        {
            "key": "first_session",
            "title": "初次对话",
            "description": "完成首次AI对话",
            "icon": "🎙️",
            "count_needed": 1,
        },
        {
            "key": "ten_sessions",
            "title": "坚持不懈",
            "description": "完成10次对话练习",
            "icon": "🔥",
            "count_needed": 10,
        },
        {
            "key": "fifty_sessions",
            "title": "口语达人",
            "description": "完成50次对话练习",
            "icon": "⭐",
            "count_needed": 50,
        },
        {
            "key": "score_80",
            "title": "发音之星",
            "description": "单次发音评分达到80分以上",
            "icon": "🌟",
            "count_needed": 1,
        },
        {
            "key": "grammar_perfect",
            "title": "语法大师",
            "description": "整场对话零语法错误",
            "icon": "✅",
            "count_needed": 1,
        },
        {
            "key": "streak_7",
            "title": "一周全勤",
            "description": "连续7天打卡练习",
            "icon": "📅",
            "count_needed": 7,
        },
    ]

    # Count completed sessions
    session_count_result = await db.execute(
        select(func.count(Session.id)).where(
            Session.user_id == current_user.id,
            Session.status == "completed",
        )
    )
    total_completed = session_count_result.scalar() or 0

    # Get existing unlocked achievements
    ua_result = await db.execute(
        select(UserAchievement).where(
            UserAchievement.user_id == current_user.id
        )
    )
    unlocked = {ua.achievement_key: ua for ua in ua_result.scalars().all()}

    achievements = []
    total_locked = 0
    for pdef in predefined:
        ua = unlocked.get(pdef["key"])
        progress = 0.0
        if pdef["key"] == "first_session":
            progress = min(total_completed / 1, 1.0) if total_completed > 0 else 0.0
        elif pdef["key"] == "ten_sessions":
            progress = min(total_completed / 10, 1.0)
        elif pdef["key"] == "fifty_sessions":
            progress = min(total_completed / 50, 1.0)
        elif pdef["key"] in ("score_80", "grammar_perfect"):
            progress = 1.0 if ua else 0.0
        elif pdef["key"] == "streak_7":
            progress = 1.0 if ua else 0.0

        achievements.append(AchievementInfo(
            achievement_key=pdef["key"],
            title=pdef["title"],
            description=pdef["description"],
            icon=pdef["icon"],
            unlocked_at=ua.unlocked_at if ua else None,
            progress=progress,
        ))
        if not ua:
            total_locked += 1

    return AchievementListResponse(
        user_id=current_user.id,
        achievements=achievements,
        total_locked=total_locked,
    )