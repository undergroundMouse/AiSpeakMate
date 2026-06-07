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
from ..models.progress import UserWeaknessRecord
from ..models.user import User
from ..schemas.evaluation import GrammarErrorOut
from ..schemas.summary import (
    SessionSummaryResponse,
    RadarScores,
    Highlight,
    PracticeSuggestion,
    TopPronunciationError,
    TopGrammarError,
    UserProgressResponse,
    ProgressSnapshot,
    WeaknessRecord,
    AchievementListResponse,
    AchievementInfo,
    TrendPoint,
    ProgressTrendResponse,
    WeaknessDistItem,
    WeaknessDistResponse,
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
    from ..models.evaluation import PronunciationEvaluation, GrammarError
    from ..models.session import Utterance
    from ..models.scene import Scene

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

    # Get scene name
    scene_name = None
    if session.scene_id:
        scene_result = await db.execute(
            select(Scene.name).where(Scene.id == session.scene_id)
        )
        scene_name = scene_result.scalar_one_or_none()
    duration_seconds = session.duration_seconds or 0

    # Gather evaluation data for real score computation
    user_utterances_result = await db.execute(
        select(Utterance).where(
            Utterance.session_id == session_id,
            Utterance.speaker == "user",
        )
    )
    user_utterances = user_utterances_result.scalars().all()

    # Compute aggregate pronunciation score from evaluations
    pron_eval_q = await db.execute(
        select(PronunciationEvaluation)
        .join(Utterance, Utterance.id == PronunciationEvaluation.utterance_id)
        .where(Utterance.session_id == session_id)
    )
    pron_evals = pron_eval_q.scalars().all()

    # Compute aggregate grammar error count
    grammar_count_q = await db.execute(
        select(func.count(GrammarError.id))
        .join(Utterance, Utterance.id == GrammarError.utterance_id)
        .where(
            Utterance.session_id == session_id,
            GrammarError.is_expression_issue == False,
        )
    )
    total_grammar_errors = grammar_count_q.scalar() or 0

    # Try to get existing summary
    summary_result = await db.execute(
        select(SessionSummary).where(
            SessionSummary.session_id == session_id
        )
    )
    summary = summary_result.scalar_one_or_none()

    # Generate or regenerate with real data
    radar = _compute_radar_from_evaluations(pron_evals, total_grammar_errors, len(user_utterances))
    highlights = _compute_highlights(pron_evals)
    suggestions = _compute_suggestions(pron_evals, total_grammar_errors)

    if not summary:
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

    # Get top pronunciation errors (up to 3)
    pronunciation_errors: list[TopPronunciationError] = []
    pron_err_result = await db.execute(
        select(PronunciationEvaluation)
        .join(Utterance, Utterance.id == PronunciationEvaluation.utterance_id)
        .where(Utterance.session_id == session_id)
        .order_by(PronunciationEvaluation.overall_score.asc())
        .limit(3)
    )
    for pe in pron_err_result.scalars().all():
        utt_result = await db.execute(
            select(Utterance.text).where(Utterance.id == pe.utterance_id)
        )
        utt_text = utt_result.scalar_one_or_none() or ""
        pronunciation_errors.append(TopPronunciationError(
            utterance_id=pe.utterance_id,
            sentence=utt_text,
            score=pe.overall_score,
            detail_url=f"/sessions/{session_id}/pronunciation/{pe.utterance_id}",
        ))

    # Get top grammar errors (up to 3)
    grammar_errors: list[TopGrammarError] = []
    gram_result = await db.execute(
        select(GrammarError)
        .join(Utterance, Utterance.id == GrammarError.utterance_id)
        .where(
            Utterance.session_id == session_id,
            GrammarError.is_expression_issue == False,
        )
        .order_by(GrammarError.id.desc())
        .limit(3)
    )
    for ge in gram_result.scalars().all():
        grammar_errors.append(TopGrammarError(
            utterance_id=ge.utterance_id,
            original=ge.original_text or "",
            error_type=ge.error_type or "unknown",
            error_span={"start": ge.error_span_start or 0, "end": ge.error_span_end or 0},
            correction=ge.correction or "",
            corrected_sentence=ge.corrected_sentence,
            explanation=ge.explanation,
            severity=ge.severity or "medium",
        ))

    return SessionSummaryResponse(
        id=summary.id,
        session_id=summary.session_id,
        scene_name=scene_name,
        duration_seconds=duration_seconds,
        radar=radar,
        highlights=summary.highlights or [],
        top_pronunciation_errors=pronunciation_errors,
        top_grammar_errors=grammar_errors,
        practice_suggestions=summary.practice_suggestions or [],
        share_image_url=summary.share_image_url,
        created_at=summary.created_at,
    )


def _compute_radar_from_evaluations(
    pron_evals: list,
    total_grammar_errors: int,
    user_utterance_count: int,
) -> RadarScores:
    """Compute radar scores from actual evaluation data."""
    if pron_evals:
        avg_pron = sum(e.overall_score for e in pron_evals) // len(pron_evals)
        avg_fluency = sum(e.fluency_score or 50 for e in pron_evals) // len(pron_evals)
    else:
        avg_pron = 50
        avg_fluency = 50

    # Grammar: fewer errors → higher score (baseline 80, -5 per error, min 20)
    grammar_score = max(20, 80 - total_grammar_errors * 5) if user_utterance_count > 0 else 50

    # Vocabulary: based on average utterance length (proxy for vocab richness)
    vocab_score = 50  # default; real implementation would use TTR or similar metrics

    # Interaction: based on number of turns
    interaction_score = min(95, 40 + user_utterance_count * 10) if user_utterance_count > 0 else 50

    return RadarScores(
        fluency=min(100, avg_fluency),
        vocabulary=min(100, vocab_score),
        grammar=min(100, grammar_score),
        pronunciation=min(100, avg_pron),
        interaction=min(100, interaction_score),
    )


def _compute_highlights(pron_evals: list) -> list[Highlight]:
    """Generate highlights based on actual good performance."""
    highlights: list[Highlight] = []
    if pron_evals:
        best = max(pron_evals, key=lambda e: e.overall_score)
        if best.overall_score >= 80:
            highlights.append(Highlight(
                title="发音准确",
                description=f"你的最高发音得分达到 {best.overall_score} 分，表现优秀！",
                example_sentence="继续保持这个水平。",
            ))
    if not highlights:
        highlights.append(Highlight(
            title="勇于开口",
            description="坚持开口练习是提升口语最重要的一步。",
            example_sentence="每次练习都在进步。",
        ))
    return highlights


def _compute_suggestions(
    pron_evals: list,
    total_grammar_errors: int,
) -> list[PracticeSuggestion]:
    """Generate practice suggestions based on weak areas."""
    suggestions: list[PracticeSuggestion] = []
    if pron_evals:
        avg_pron = sum(e.overall_score for e in pron_evals) // len(pron_evals)
        if avg_pron < 70:
            suggestions.append(PracticeSuggestion(
                title="加强发音练习",
                description="你的发音还有提升空间，建议每天跟读英语音频10分钟，关注元音发音位置。",
                resource_type="video",
                resource_url="https://example.com/pronunciation-basics",
            ))
    if total_grammar_errors > 2:
        suggestions.append(PracticeSuggestion(
            title="复习基础语法",
            description=f"本场对话检测到 {total_grammar_errors} 个语法错误，建议重点复习时态和主谓一致。",
            resource_type="article",
            resource_url="https://example.com/grammar-review",
        ))
    if not suggestions:
        suggestions.append(PracticeSuggestion(
            title="挑战更高难度",
            description="你表现得很好！尝试切换到高级难度，接触更复杂的表达。",
            resource_type="exercise",
            resource_url="https://example.com/advanced-practice",
        ))
    return suggestions


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


# --- Weakness Distribution ---

VALID_WEAKNESS_CATEGORIES = ["pronunciation", "grammar"]


@router.get(
    "/progress/weaknesses/distribution",
    response_model=WeaknessDistResponse,
    summary="获取弱点分布数据",
)
async def get_weakness_distribution(
    start_date: str,
    end_date: str,
    category: str | None = None,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """Get weakness distribution data aggregated by category and item."""
    from datetime import date as date_type

    if category is not None and category not in VALID_WEAKNESS_CATEGORIES:
        raise HTTPException(
            400,
            f"Invalid category. Must be one of: {', '.join(VALID_WEAKNESS_CATEGORIES)}",
        )

    try:
        sd = date_type.fromisoformat(start_date)
        ed = date_type.fromisoformat(end_date)
    except ValueError:
        raise HTTPException(400, "Invalid date format. Use YYYY-MM-DD.")

    if sd > ed:
        raise HTTPException(400, "start_date must be before or equal to end_date")

    # Build query conditions
    conditions = [
        UserWeaknessRecord.user_id == current_user.id,
        UserWeaknessRecord.period_end >= sd,
        UserWeaknessRecord.period_start <= ed,
    ]
    if category is not None:
        conditions.append(UserWeaknessRecord.category == category)

    result = await db.execute(
        select(UserWeaknessRecord).where(*conditions)
    )
    records = result.scalars().all()

    # Aggregate by (category, item) summing error_count
    from collections import defaultdict
    aggregated: dict[tuple[str, str], dict] = defaultdict(
        lambda: {"total_error_count": 0, "trends": []}
    )

    for r in records:
        agg = aggregated[(r.category, r.item)]
        agg["total_error_count"] += r.error_count
        if r.trend:
            agg["trends"].append(r.trend)

    items: list[WeaknessDistItem] = []
    for (cat, name), agg in sorted(aggregated.items(), key=lambda x: -x[1]["total_error_count"]):
        trend = None
        trends = agg["trends"]
        if trends:
            # Use the most recent trend (records ordered by period_end desc implicitly via query)
            # For simplicity, use the first non-stable, or last available
            trend = trends[-1]

        items.append(WeaknessDistItem(
            category=cat,
            item=name,
            total_error_count=agg["total_error_count"],
            trend=trend,
        ))

    return WeaknessDistResponse(
        user_id=current_user.id,
        period_start=sd,
        period_end=ed,
        items=items,
    )


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