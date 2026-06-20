import uuid
import random
from datetime import date, datetime, timedelta, timezone

from fastapi import APIRouter, Depends, HTTPException

from sqlalchemy import select, func
from sqlalchemy.ext.asyncio import AsyncSession

from ..api.dependencies import get_current_user
from ..core.database import get_db
from ..models.evaluation import GrammarError, PronunciationEvaluation
from ..models.session import Session, Utterance
from ..models.summary import SessionSummary
from ..models.achievement import UserAchievement, Achievement
from ..models.progress import UserProgressSnapshot, UserWeaknessRecord
from ..models.user import User
from ..schemas.summary import (
    SessionSummaryResponse,
    RadarScores,
    Highlight,
    PracticeSuggestion,
    TopPronunciationError,
    TopGrammarError,
    CoachCardInsight,
    CoachCardResponse,
    NextPracticeOption,
    NextPracticeResponse,
    UserProgressResponse,
    ProgressSnapshot,
    WeaknessRecord,
    ProgressProvenance,
    DimensionAvailable,
    AchievementListResponse,
    AchievementInfo,
    TrendPoint,
    ForecastPoint,
    ProgressTrendResponse,
    WeaknessDistItem,
    WeaknessDistResponse,
)
from ..schemas.session import SessionListResponse, SessionHistory
from ..models.scene import Scene, SceneCategory

router = APIRouter()


# --- Progress Trend ---

VALID_DIMENSIONS = ["fluency", "vocabulary", "grammar", "pronunciation", "interaction"]
VALID_GRANULARITIES = ["daily", "weekly"]
PREFERRED_CATEGORY_KEYWORDS = ["daily life", "日常生活", "travel", "旅行", "transport", "出行"]


@router.get(
    "/users/{user_id}/progress/trend",
    response_model=ProgressTrendResponse,
    summary="获取进步趋势数据",
)
async def get_progress_trend(
    user_id: uuid.UUID,
    start_date: str,
    end_date: str,
    dimension: str = "all",
    granularity: str = "daily",
    include_forecast: bool = False,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """Get progress trend data with date range, dimension, and granularity filters."""
    from datetime import date as date_type, timedelta

    if current_user.id != user_id:
        raise HTTPException(403, "Access denied")

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
        return ProgressTrendResponse(data_points=[], dimension=dimension, granularity=granularity)

    # Helper: compute linear regression forecast
    def _compute_forecast(
        pts: list[TrendPoint], num_forecast: int = 2
    ) -> list[ForecastPoint]:
        if len(pts) < 2:
            return []
        n = len(pts)
        xs = list(range(n))
        ys = [p.score for p in pts]
        mean_x = sum(xs) / n
        mean_y = sum(ys) / n
        num = sum((xs[i] - mean_x) * (ys[i] - mean_y) for i in range(n))
        den = sum((xs[i] - mean_x) ** 2 for i in range(n))
        if den == 0:
            return []
        slope = num / den
        intercept = mean_y - slope * mean_x
        # Estimate confidence interval from residuals
        residuals = [ys[i] - (slope * xs[i] + intercept) for i in range(n)]
        std_err = (sum(r ** 2 for r in residuals) / (n - 2)) ** 0.5 if n > 2 else 2.0
        last_date = pts[-1].date
        forecasts: list[ForecastPoint] = []
        for i in range(1, num_forecast + 1):
            pred = slope * (n + i - 1) + intercept
            pred = max(0, min(100, int(pred)))
            lower = max(0, int(pred - 1.96 * std_err))
            upper = min(100, int(pred + 1.96 * std_err))
            next_date = last_date + timedelta(weeks=i) if granularity == "weekly" else last_date + timedelta(days=7 * i)
            forecasts.append(ForecastPoint(
                date=next_date, score=pred,
                confidence_interval_lower=lower, confidence_interval_upper=upper,
            ))
        return forecasts

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
        forecast = _compute_forecast(points) if include_forecast else []
        return ProgressTrendResponse(
            data_points=points, dimension=dimension, granularity=granularity, forecast=forecast,
        )
    else:
        # daily
        points: list[TrendPoint] = []
        for s in snapshots:
            if dimension == "all":
                points.append(TrendPoint(date=s.snapshot_date, score=s.total_score))
            else:
                dim_score = s.dimension_scores.get(dimension, 50)
                points.append(TrendPoint(date=s.snapshot_date, score=dim_score, dimension=dimension))
        forecast = _compute_forecast(points) if include_forecast else []
        return ProgressTrendResponse(
            data_points=points, dimension=dimension, granularity=granularity, forecast=forecast,
        )


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
    radar = _compute_radar_from_evaluations(pron_evals, total_grammar_errors, len(user_utterances), user_utterances)
    highlights = _compute_highlights(pron_evals)
    suggestions = _compute_suggestions(pron_evals, total_grammar_errors)
    opening_insight = None

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
            created_at=datetime.utcnow(),
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

    overall_score = _compute_overall_score(radar)
    score_delta = await _compute_score_delta(
        db, current_user.id, session.scene_id, session_id, overall_score
    )
    coach_card = _build_coach_card(
        scene_name, duration_seconds, radar, highlights,
        pronunciation_errors, grammar_errors, score_delta,
        chat_only=len(pronunciation_errors) == 0,
    )
    opening_insight = _generate_opening_insight(
        overall_score, pronunciation_errors, grammar_errors
    )
    if opening_insight and (not summary.opening_insight):
        summary.opening_insight = opening_insight
        await db.commit()
        await db.refresh(summary)

    next_practice_options = await _compute_next_practice_options(
        db, current_user.id, session, overall_score, pronunciation_errors,
        chat_only=len(pronunciation_errors) == 0,
    )

    return SessionSummaryResponse(
        id=summary.id,
        session_id=summary.session_id,
        scene_name=scene_name,
        duration_seconds=duration_seconds,
        radar_scores=radar,
        highlights=summary.highlights or [],
        top_pronunciation_errors=pronunciation_errors,
        top_grammar_errors=grammar_errors,
        practice_suggestions=summary.practice_suggestions or [],
        share_image_url=summary.share_image_url,
        coach_card=coach_card,
        next_practice_options=next_practice_options,
        created_at=summary.created_at,
    )


@router.get(
    "/users/{user_id}/next-practice",
    response_model=NextPracticeResponse,
    summary="获取明日练习推荐",
)
async def get_next_practice(
    user_id: uuid.UUID,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    if current_user.id != user_id:
        raise HTTPException(403, "Access denied")

    recent_result = await db.execute(
        select(Session)
        .where(
            Session.user_id == user_id,
            Session.status == "completed",
        )
        .order_by(Session.started_at.desc())
        .limit(1)
    )
    recent_session = recent_result.scalar_one_or_none()
    if not recent_session:
        options = await _default_next_practice_options(db)
        return NextPracticeResponse(options=options)

    summary_result = await db.execute(
        select(SessionSummary).where(SessionSummary.session_id == recent_session.id)
    )
    summary = summary_result.scalar_one_or_none()
    radar = RadarScores(
        fluency=summary.radar_fluency or 0,
        vocabulary=summary.radar_vocabulary or 0,
        grammar=summary.radar_grammar or 0,
        pronunciation=summary.radar_pronunciation or 0,
        interaction=summary.radar_interaction or 0,
    ) if summary else RadarScores(fluency=0, vocabulary=0, grammar=0, pronunciation=0, interaction=0)
    overall_score = _compute_overall_score(radar)

    pron_errors: list[TopPronunciationError] = []
    if recent_session:
        pron_err_result = await db.execute(
            select(PronunciationEvaluation)
            .join(Utterance, Utterance.id == PronunciationEvaluation.utterance_id)
            .where(Utterance.session_id == recent_session.id)
            .order_by(PronunciationEvaluation.overall_score.asc())
            .limit(1)
        )
        pe = pron_err_result.scalar_one_or_none()
        if pe:
            utt_result = await db.execute(
                select(Utterance.text).where(Utterance.id == pe.utterance_id)
            )
            utt_text = utt_result.scalar_one_or_none() or ""
            pron_errors.append(TopPronunciationError(
                utterance_id=pe.utterance_id,
                sentence=utt_text,
                score=pe.overall_score,
                detail_url=f"/sessions/{recent_session.id}/pronunciation/{pe.utterance_id}",
            ))

    options = await _compute_next_practice_options(
        db, user_id, recent_session, overall_score, pron_errors,
    )
    return NextPracticeResponse(options=options)


def _compute_radar_from_evaluations(
    pron_evals: list,
    total_grammar_errors: int,
    user_utterance_count: int,
    user_utterances: list | None = None,
) -> RadarScores:
    """Compute radar scores from actual evaluation data and user utterances."""
    if pron_evals:
        avg_pron = sum(e.overall_score for e in pron_evals) // len(pron_evals)
        avg_fluency = sum(e.fluency_score or 0 for e in pron_evals) // len(pron_evals)
    else:
        avg_pron = 0
        avg_fluency = 0

    # Grammar: fewer errors → higher score. Each error deducts 5 points, floor at 0.
    grammar_score = max(0, 80 - total_grammar_errors * 5) if user_utterance_count > 0 else 0

    # Vocabulary: compute actual Type-Token Ratio from user utterances
    if user_utterances:
        vocab_score = _compute_vocab_score_from_utterances(user_utterances)
    else:
        vocab_score = 0

    # Interaction: based on number of turns (each turn adds ~10 points, max 95)
    interaction_score = min(95, user_utterance_count * 10) if user_utterance_count > 0 else 0

    return RadarScores(
        fluency=min(100, avg_fluency),
        vocabulary=min(100, vocab_score),
        grammar=min(100, grammar_score),
        pronunciation=min(100, avg_pron),
        interaction=min(100, interaction_score),
    )


def _compute_vocab_score_from_utterances(utterances: list) -> int:
    """Compute vocabulary diversity score from actual user utterances using TTR."""
    if not utterances:
        return 0
    all_words: list[str] = []
    for u in utterances:
        text = u.text if hasattr(u, 'text') else str(u)
        words = [w.strip(".,!?;:\"'()").lower() for w in text.split()]
        all_words.extend(w for w in words if w and len(w) > 1)
    if not all_words:
        return 0
    total = len(all_words)
    unique = len(set(all_words))
    ttr = unique / max(total, 1)
    avg_len = sum(len(w) for w in all_words) / max(total, 1)
    length_factor = min(1.0, max(0.0, (avg_len - 3.0) / 3.0))
    raw = (ttr * 0.7 + length_factor * 0.3) * 100
    return int(max(0, min(95, raw)))


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
                type="pronunciation",
                target="基础发音练习",
                suggested_exercise_id="ex_pron_basic",
            ))
    if total_grammar_errors > 2:
        suggestions.append(PracticeSuggestion(
            type="grammar",
            target="时态和主谓一致",
            suggested_exercise_id="ex_grammar_review",
        ))
    if not suggestions:
        suggestions.append(PracticeSuggestion(
            type="comprehensive",
            target="挑战更高难度",
            suggested_exercise_id="ex_advanced",
        ))
    return suggestions


def _compute_overall_score(radar: RadarScores) -> int:
    """Arithmetic mean of five radar dimensions."""
    return (
        radar.fluency + radar.vocabulary + radar.grammar
        + radar.pronunciation + radar.interaction
    ) // 5


async def _compute_score_delta(
    db: AsyncSession,
    user_id: uuid.UUID,
    scene_id: int | None,
    current_session_id: uuid.UUID,
    current_overall_score: int,
) -> int | None:
    if not scene_id:
        return None
    prev_result = await db.execute(
        select(SessionSummary)
        .join(Session, SessionSummary.session_id == Session.id)
        .where(
            Session.user_id == user_id,
            Session.scene_id == scene_id,
            Session.status == "completed",
            Session.id != current_session_id,
        )
        .order_by(Session.started_at.desc())
        .limit(1)
    )
    prev_summary = prev_result.scalar_one_or_none()
    if not prev_summary:
        return None
    prev_radar = RadarScores(
        fluency=prev_summary.radar_fluency or 0,
        vocabulary=prev_summary.radar_vocabulary or 0,
        grammar=prev_summary.radar_grammar or 0,
        pronunciation=prev_summary.radar_pronunciation or 0,
        interaction=prev_summary.radar_interaction or 0,
    )
    prev_overall = _compute_overall_score(prev_radar)
    return current_overall_score - prev_overall


def _build_coach_card(
    scene_name: str | None,
    duration_seconds: int,
    radar: RadarScores,
    highlights: list,
    pronunciation_errors: list[TopPronunciationError],
    grammar_errors: list[TopGrammarError],
    score_delta: int | None,
    chat_only: bool = False,
) -> CoachCardResponse:
    if chat_only:
        return CoachCardResponse(
            scene_name=scene_name or "聊天",
            duration_seconds=duration_seconds,
            overall_score=None,
            strengths=[CoachCardInsight(
                type="strength",
                text="今天聊得很顺！",
                detail="继续保持开口习惯",
            )],
            improvements=[],
            score_delta=None,
            chat_only=True,
        )

    overall = _compute_overall_score(radar)
    strengths: list[CoachCardInsight] = []
    improvements: list[CoachCardInsight] = []

    if highlights:
        hl = highlights[0]
        title = hl.get("title", "") if isinstance(hl, dict) else hl.title
        desc = hl.get("description", "") if isinstance(hl, dict) else hl.description
        strengths.append(CoachCardInsight(type="strength", text=title, detail=desc))
    else:
        dim_names = {
            "fluency": "流利度",
            "vocabulary": "词汇",
            "grammar": "语法",
            "pronunciation": "发音",
            "interaction": "互动",
        }
        best_dim = max(
            dim_names.keys(),
            key=lambda d: getattr(radar, d),
        )
        strengths.append(CoachCardInsight(
            type="strength",
            text=f"{dim_names[best_dim]}表现不错",
            detail=f"本次 {dim_names[best_dim]} 得分 {getattr(radar, best_dim)} 分",
        ))

    if pronunciation_errors:
        pe = pronunciation_errors[0]
        snippet = pe.sentence if len(pe.sentence) <= 50 else pe.sentence[:47] + "..."
        improvements.append(CoachCardInsight(
            type="improvement",
            text=f"「{snippet}」发音可以再清晰一些",
            detail=f"该句得分 {pe.score} 分",
        ))
    if grammar_errors and len(improvements) < 2:
        ge = grammar_errors[0]
        improvements.append(CoachCardInsight(
            type="improvement",
            text=f"试试更地道的表达：{ge.correction}",
            detail=ge.explanation,
        ))
    if not improvements and overall < 85:
        improvements.append(CoachCardInsight(
            type="improvement",
            text="继续保持开口练习，多说完整句子",
            detail=None,
        ))

    return CoachCardResponse(
        scene_name=scene_name or "练习场景",
        duration_seconds=duration_seconds,
        overall_score=overall,
        strengths=strengths[:1],
        improvements=improvements[:2],
        score_delta=score_delta,
        chat_only=False,
    )


def _generate_opening_insight(
    overall_score: int,
    pronunciation_errors: list[TopPronunciationError],
    grammar_errors: list[TopGrammarError],
) -> str | None:
    """Only generate opening reminder when prior session had pronunciation coaching data."""
    if not pronunciation_errors:
        return None

    if overall_score >= 85 and pronunciation_errors[0].score >= 70:
        insight = "Great job last time — let's keep the momentum going!"
    elif pronunciation_errors[0].score < 70:
        snippet = pronunciation_errors[0].sentence
        if len(snippet) > 40:
            snippet = snippet[:37] + "..."
        insight = f"Last time, try clearer pronunciation in: \"{snippet}\""
    else:
        return None

    if len(insight) > 120:
        return insight[:117] + "..."
    return insight


def _is_preferred_category(category_name: str) -> bool:
    lower = category_name.lower()
    return any(k in lower for k in PREFERRED_CATEGORY_KEYWORDS)


async def _pick_explore_scene(
    db: AsyncSession,
    user_id: uuid.UUID,
    exclude_scene_id: int | None = None,
) -> Scene | None:
    seven_days_ago = datetime.utcnow() - timedelta(days=7)
    recent_q = await db.execute(
        select(Session.scene_id).where(
            Session.user_id == user_id,
            Session.status == "completed",
            Session.started_at >= seven_days_ago,
            Session.scene_id.isnot(None),
        )
    )
    recent_scene_ids = {row[0] for row in recent_q.all()}
    if exclude_scene_id:
        recent_scene_ids.add(exclude_scene_id)

    scenes_q = await db.execute(
        select(Scene, SceneCategory.name)
        .join(SceneCategory, Scene.category_id == SceneCategory.id)
        .where(Scene.is_active == True)
    )
    all_scenes = scenes_q.all()
    if not all_scenes:
        return None

    unseen = [(s, c) for s, c in all_scenes if s.id not in recent_scene_ids]
    if unseen:
        preferred = [s for s, c in unseen if _is_preferred_category(c)]
        pool = preferred or [s for s, c in unseen]
        return random.choice(pool)

    count_q = await db.execute(
        select(Session.scene_id, func.count(Session.id))
        .where(
            Session.user_id == user_id,
            Session.status == "completed",
            Session.scene_id.isnot(None),
        )
        .group_by(Session.scene_id)
    )
    counts = dict(count_q.all())
    candidates = [s for s, _ in all_scenes if s.id != exclude_scene_id]
    if not candidates:
        return None
    return min(candidates, key=lambda s: counts.get(s.id, 0))


async def _compute_next_practice_options(
    db: AsyncSession,
    user_id: uuid.UUID,
    session: Session,
    overall_score: int,
    pronunciation_errors: list[TopPronunciationError],
    chat_only: bool = False,
) -> list[NextPracticeOption]:
    options: list[NextPracticeOption] = []

    if session.scene_id:
        scene_result = await db.execute(
            select(Scene).where(Scene.id == session.scene_id)
        )
        scene = scene_result.scalar_one_or_none()
        if scene:
            if chat_only:
                reason = "继续刚才的话题"
                label = f"再聊「{scene.name}」"
            elif overall_score >= 85:
                reason = "表现不错，再练一次巩固记忆"
                label = f"再练「{scene.name}」"
            elif pronunciation_errors:
                reason = "继续练习，巩固发音和表达"
                label = f"再练「{scene.name}」"
            else:
                reason = "趁热打铁，再练一次同场景"
                label = f"再练「{scene.name}」"
            options.append(NextPracticeOption(
                kind="consolidate",
                scene_id=scene.id,
                scene_name=scene.name,
                label=label if not chat_only else label.replace("再练", "再聊"),
                reason=reason,
            ))

    explore = await _pick_explore_scene(db, user_id, exclude_scene_id=session.scene_id)
    if explore:
        options.append(NextPracticeOption(
            kind="explore",
            scene_id=explore.id,
            scene_name=explore.name,
            label=f"换话题「{explore.name}」" if chat_only else f"试试「{explore.name}」",
            reason="换个新话题，轻松聊聊" if chat_only else "换个新场景，轻松练练口语",
        ))

    return options[:2]


async def _default_next_practice_options(db: AsyncSession) -> list[NextPracticeOption]:
    """Fallback for users with no completed sessions."""
    scenes_q = await db.execute(
        select(Scene, SceneCategory.name)
        .join(SceneCategory, Scene.category_id == SceneCategory.id)
        .where(Scene.is_active == True)
        .order_by(Scene.id)
        .limit(10)
    )
    rows = scenes_q.all()
    preferred = [(s, c) for s, c in rows if _is_preferred_category(c)]
    pool = preferred or rows
    if len(pool) >= 2:
        picks = random.sample(pool, 2)
    elif pool:
        picks = [pool[0], pool[0]]
    else:
        return []

    options: list[NextPracticeOption] = []
    kinds = ["consolidate", "explore"]
    for i, (scene, _) in enumerate(picks[:2]):
        options.append(NextPracticeOption(
            kind=kinds[i],
            scene_id=scene.id,
            scene_name=scene.name,
            label=f"开始「{scene.name}」",
            reason="热门场景，适合开口练习",
        ))
    return options


# --- User Progress ---

async def _compute_progress_provenance(
    db: AsyncSession,
    user_id: uuid.UUID,
    total_sessions: int,
    has_strengths: bool,
) -> tuple[ProgressProvenance, DimensionAvailable]:
    """Aggregate data source metadata for progress metrics."""
    pron_q = await db.execute(
        select(PronunciationEvaluation.source)
        .join(Utterance, Utterance.id == PronunciationEvaluation.utterance_id)
        .join(Session, Session.id == Utterance.session_id)
        .where(Session.user_id == user_id)
        .order_by(PronunciationEvaluation.evaluated_at.desc())
        .limit(20)
    )
    sources = [row[0] or "text_analysis" for row in pron_q.all()]

    if not sources:
        pron_source = "none"
        fluency_source = "none"
    else:
        real_count = sum(1 for s in sources if s in {"iflytek_ise", "speechsuper"})
        ta_count = sum(1 for s in sources if s == "text_analysis")
        if real_count > ta_count:
            pron_source = fluency_source = "iflytek_ise"
        else:
            pron_source = fluency_source = "text_analysis"

    has_sessions = total_sessions > 0
    provenance = ProgressProvenance(
        pronunciation=pron_source,
        fluency=fluency_source,
        grammar="evaluation" if has_sessions else "none",
        vocabulary="heuristic" if has_sessions else "none",
        interaction="heuristic" if has_sessions else "none",
        strengths="computed" if has_strengths else "none",
    )
    dimension_available = DimensionAvailable(
        pronunciation=pron_source != "none",
        fluency=fluency_source != "none",
        grammar=has_sessions,
        vocabulary=has_sessions,
        interaction=has_sessions,
    )
    return provenance, dimension_available


@router.get(
    "/users/{user_id}/progress",
    response_model=UserProgressResponse,
    summary="获取用户学习进度总览",
)
async def get_user_progress(
    user_id: uuid.UUID,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """
    Get overall learning progress for the current user,
    computed from real AI conversation evaluation data.
    """
    if current_user.id != user_id:
        raise HTTPException(403, "Access denied")

    today = date.today()

    # 1. Count completed sessions and total duration
    session_query = await db.execute(
        select(
            func.count(Session.id),
            func.coalesce(func.sum(Session.duration_seconds), 0),
        ).where(
            Session.user_id == current_user.id,
            Session.status == "completed",
        )
    )
    total_sessions, total_duration = session_query.one()
    total_hours = round(total_duration / 3600, 1) if total_duration else 0.0

    # 2. Query real snapshots (last 7 entries, chronological order)
    snapshots_result = await db.execute(
        select(UserProgressSnapshot)
        .where(UserProgressSnapshot.user_id == current_user.id)
        .order_by(UserProgressSnapshot.snapshot_date.desc())
        .limit(7)
    )
    snapshot_models = snapshots_result.scalars().all()

    snapshots: list[ProgressSnapshot] = []
    overall_score = 0
    for s in reversed(snapshot_models):  # chronological order for display
        snapshots.append(ProgressSnapshot(
            snapshot_date=s.snapshot_date,
            total_score=s.total_score,
            dimension_scores=s.dimension_scores or {},
            session_count=s.session_count,
            total_duration_seconds=s.total_duration_seconds,
        ))
    if snapshot_models:
        overall_score = snapshot_models[0].total_score  # most recent
    else:
        # Fallback: compute from recent evaluations
        overall_score = await _compute_recent_score(db, current_user.id)

    rating = _get_rating(overall_score)

    # 3. Query real weaknesses
    weaknesses_result = await db.execute(
        select(UserWeaknessRecord)
        .where(UserWeaknessRecord.user_id == current_user.id)
        .order_by(UserWeaknessRecord.error_count.desc())
        .limit(10)
    )
    weakness_models = weaknesses_result.scalars().all()

    weaknesses: list[WeaknessRecord] = []
    for w in weakness_models:
        # Clean up item name for display
        item_display = w.item
        if item_display.startswith("phoneme "):
            item_display = item_display[8:]  # strip "phoneme " prefix
        weaknesses.append(WeaknessRecord(
            period_start=w.period_start,
            period_end=w.period_end,
            category=w.category,
            item=item_display,
            error_count=w.error_count,
            trend=w.trend,
        ))

    # 4. Compute strengths from best dimension scores
    strengths: list[dict] = []
    if snapshot_models:
        dim_scores = snapshot_models[0].dimension_scores or {}
        dim_labels = {
            "fluency": "流利度",
            "vocabulary": "词汇量",
            "grammar": "语法",
            "pronunciation": "发音",
            "interaction": "互动",
        }
        sorted_dims = sorted(dim_scores.items(), key=lambda x: x[1], reverse=True)
        for dim_key, score in sorted_dims[:2]:
            if score >= 55:  # Only count as strength if above baseline
                strengths.append({
                    "area": dim_labels.get(dim_key, dim_key),
                    "score": score,
                    "trend": "stable",
                })

    provenance, dimension_available = await _compute_progress_provenance(
        db, current_user.id, total_sessions, bool(strengths),
    )

    return UserProgressResponse(
        user_id=current_user.id,
        overall_rating=rating,
        total_score=overall_score,
        total_sessions=total_sessions,
        total_hours=total_hours,
        snapshots=snapshots,
        weaknesses=weaknesses,
        strengths=strengths,
        data_provenance=provenance,
        dimension_available=dimension_available,
    )


async def _compute_recent_score(db: AsyncSession, user_id: uuid.UUID) -> int:
    """Compute a score from recent session evaluations (fallback when no snapshots)."""
    thirty_days_ago = datetime.now(timezone.utc) - timedelta(days=30)

    # Compare naive datetimes since Session.ended_at is stored without timezone
    thirty_days_ago_naive = thirty_days_ago.replace(tzinfo=None)

    recent_sessions_q = await db.execute(
        select(Session.id).where(
            Session.user_id == user_id,
            Session.status == "completed",
            Session.ended_at >= thirty_days_ago_naive,
        ).limit(20)
    )
    recent_ids = [row[0] for row in recent_sessions_q.all()]

    if not recent_ids:
        # No recent sessions — user hasn't practiced yet (or no completed sessions)
        return 0

    # Aggregate pronunciation scores from actual evaluations
    pron_q = await db.execute(
        select(func.avg(PronunciationEvaluation.overall_score))
        .join(Utterance, Utterance.id == PronunciationEvaluation.utterance_id)
        .where(Utterance.session_id.in_(recent_ids))
    )
    avg_pron = pron_q.scalar() or 0.0

    # Count grammar errors from actual utterances
    grammar_q = await db.execute(
        select(func.count(GrammarError.id))
        .join(Utterance, Utterance.id == GrammarError.utterance_id)
        .where(
            Utterance.session_id.in_(recent_ids),
            GrammarError.is_expression_issue == False,
        )
    )
    total_grammar = grammar_q.scalar() or 0

    # Grammar score: deduct 5 per error, floor at 0
    grammar_score = max(0, 80 - total_grammar * 5)

    # Compute purely from actual evaluation data — no simulated component
    return int(min(100, avg_pron * 0.55 + grammar_score * 0.45))


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
    "/users/{user_id}/progress/weakness-distribution",
    response_model=WeaknessDistResponse,
    summary="获取弱点分布数据",
)
async def get_weakness_distribution(
    user_id: uuid.UUID,
    start_date: str,
    end_date: str,
    category: str | None = None,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """Get weakness distribution data aggregated by category and item."""
    from datetime import date as date_type

    if current_user.id != user_id:
        raise HTTPException(403, "Access denied")

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
            error_count=agg["total_error_count"],
            trend=trend,
            suggested_exercise_id=f"ex_{name.replace(' ', '_').replace('/', '')}",
        ))

    return WeaknessDistResponse(
        user_id=current_user.id,
        period=f"{sd.isoformat()}_to_{ed.isoformat()}",
        weakness_matrix=items,
    )


# --- User Sessions (V1.1) ---

@router.get("/users/{user_id}/sessions", response_model=SessionListResponse, summary="获取用户练习历史列表")
async def list_user_sessions(
    user_id: uuid.UUID,
    page: int = 1,
    page_size: int = 20,
    scene_id: int | None = None,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """V1.1: List sessions for a user with page-based pagination."""
    if current_user.id != user_id:
        raise HTTPException(403, "Access denied")

    page = max(1, page)
    page_size = max(1, min(100, page_size))
    offset = (page - 1) * page_size

    count_q = select(func.count(Session.id)).where(Session.user_id == current_user.id)
    if scene_id:
        count_q = count_q.where(Session.scene_id == scene_id)
    total_result = await db.execute(count_q)
    total = total_result.scalar() or 0

    rows_q = (
        select(Session)
        .where(Session.user_id == current_user.id)
        .order_by(Session.started_at.desc())
        .offset(offset)
        .limit(page_size)
    )
    if scene_id:
        rows_q = rows_q.where(Session.scene_id == scene_id)
    rows_result = await db.execute(rows_q)
    rows = rows_result.scalars().all()

    sessions: list[SessionHistory] = []
    for sess in rows:
        scene_name = None
        if sess.scene_id:
            scene_result = await db.execute(select(Scene.name).where(Scene.id == sess.scene_id))
            scene_name = scene_result.scalar_one_or_none()
        sessions.append(SessionHistory(
            session_id=sess.id,
            scene_id=sess.scene_id,
            scene_name=scene_name,
            date=sess.started_at,
            duration_seconds=sess.duration_seconds or 0,
            total_score=0,
        ))

    return SessionListResponse(data=sessions, total=total, page=page, page_size=page_size)


# --- Review Plan (V1.1) ---

@router.get("/users/{user_id}/review-plan", summary="获取复习计划")
async def get_review_plan(
    user_id: uuid.UUID,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """V1.1: Generate a personalized review plan based on user weaknesses."""
    if current_user.id != user_id:
        raise HTTPException(403, "Access denied")

    from ..models.evaluation import PhonemeScore, PronunciationEvaluation
    from ..models.session import Utterance

    # Get top weaknesses
    weakness_q = await db.execute(
        select(UserWeaknessRecord)
        .where(UserWeaknessRecord.user_id == user_id)
        .order_by(UserWeaknessRecord.error_count.desc())
        .limit(5)
    )
    weaknesses = weakness_q.scalars().all()

    items = []
    for w in weaknesses:
        ex_ids = [f"ex_{w.item.replace(' ', '_').replace('/', '')}_{i}" for i in range(1, 3)]
        items.append({
            "type": w.category,
            "target": w.item,
            "exercise_ids": ex_ids,
            "estimated_minutes": min(w.error_count * 2, 10),
        })

    return {
        "plan_id": f"plan_{uuid.uuid4().hex[:8]}",
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "items": items,
    }


# --- Data Export (V1.1) ---

@router.get("/users/{user_id}/export", summary="导出用户数据")
async def export_user_data(
    user_id: uuid.UUID,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """V1.1: Export all user data as a JSON package."""
    if current_user.id != user_id:
        raise HTTPException(403, "Access denied")

    # Gather all session data
    sessions_q = await db.execute(
        select(Session).where(
            Session.user_id == user_id,
            Session.status == "completed",
        ).order_by(Session.started_at.desc()).limit(50)
    )
    sessions_data = []
    for sess in sessions_q.scalars().all():
        utt_q = await db.execute(
            select(Utterance).where(Utterance.session_id == sess.id)
        )
        sessions_data.append({
            "session_id": str(sess.id),
            "scene_id": sess.scene_id,
            "difficulty": sess.difficulty,
            "started_at": sess.started_at.isoformat() if sess.started_at else None,
            "duration_seconds": sess.duration_seconds,
            "utterances": [{"speaker": u.speaker, "text": u.text} for u in utt_q.scalars().all()],
        })

    return {
        "user_id": str(user_id),
        "username": current_user.username,
        "email": current_user.email,
        "exported_at": datetime.now(timezone.utc).isoformat(),
        "sessions": sessions_data,
    }


# --- Achievements ---

@router.get(
    "/users/{user_id}/achievements",
    response_model=AchievementListResponse,
    summary="获取用户成就列表",
)
async def get_achievements(
    user_id: uuid.UUID,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """
    Get the achievement list for current user.
    """
    if current_user.id != user_id:
        raise HTTPException(403, "Access denied")

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
    for pdef in predefined:
        ua = unlocked.get(pdef["key"])
        current_progress = 0
        if pdef["key"] == "first_session":
            current_progress = min(total_completed, 1)
        elif pdef["key"] == "ten_sessions":
            current_progress = min(total_completed, 10)
        elif pdef["key"] == "fifty_sessions":
            current_progress = min(total_completed, 50)
        elif pdef["key"] in ("score_80", "grammar_perfect"):
            current_progress = 1 if ua else 0
        elif pdef["key"] == "streak_7":
            current_progress = 1 if ua else 0

        achievements.append(AchievementInfo(
            id=pdef["key"],
            title=pdef["title"],
            description=pdef["description"],
            current_progress=current_progress,
            target=pdef["count_needed"],
            unlocked_at=ua.unlocked_at if ua else None,
            icon_url=None,
            icon=pdef["icon"],
        ))

    return AchievementListResponse(
        user_id=current_user.id,
        achievements=achievements,
    )