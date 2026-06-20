import uuid
from datetime import datetime, timezone

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from ..core.database import get_db
from ..models.scene import Scene
from ..models.session import Session, Utterance
from ..models.user import User
from ..schemas.session import (
    EndSessionResponse,
    SessionHistory,
    SessionListResponse,
    SessionResponse,
    StartSessionRequest,
    UtteranceBrief,
)
from .dependencies import get_current_user

router = APIRouter(prefix="/sessions", tags=["sessions"])


async def _list_sessions_impl(
    user: User,
    db: AsyncSession,
    page: int = 1,
    page_size: int = 20,
    status: str | None = None,
    scene_id: int | None = None,
) -> SessionListResponse:
    """Shared implementation for listing user sessions with page-based pagination."""
    page = max(1, page)
    page_size = max(1, min(100, page_size))
    offset = (page - 1) * page_size

    count_q = select(func.count(Session.id)).where(Session.user_id == user.id)
    if status:
        count_q = count_q.where(Session.status == status)
    if scene_id:
        count_q = count_q.where(Session.scene_id == scene_id)

    total_result = await db.execute(count_q)
    total = total_result.scalar() or 0

    rows_q = (
        select(Session)
        .where(Session.user_id == user.id)
        .order_by(Session.started_at.desc())
        .offset(offset)
        .limit(page_size)
    )
    if status:
        rows_q = rows_q.where(Session.status == status)
    if scene_id:
        rows_q = rows_q.where(Session.scene_id == scene_id)

    rows_result = await db.execute(rows_q)
    rows = rows_result.scalars().all()

    sessions: list[SessionHistory] = []
    for sess in rows:
        scene_name = None
        if sess.scene_id:
            scene_result = await db.execute(
                select(Scene.name).where(Scene.id == sess.scene_id)
            )
            scene_name = scene_result.scalar_one_or_none()
        sessions.append(
            SessionHistory(
                session_id=sess.id,
                scene_id=sess.scene_id,
                scene_name=scene_name,
                date=sess.started_at,
                duration_seconds=sess.duration_seconds or 0,
                total_score=0,
            )
        )

    return SessionListResponse(
        data=sessions, total=total, page=page, page_size=page_size,
    )


@router.get("", response_model=SessionListResponse)
async def list_sessions(
    page: int = 1,
    page_size: int = 20,
    status: str | None = None,
    scene_id: int | None = None,
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """List sessions for the current user with optional filters and pagination."""
    return await _list_sessions_impl(user, db, page=page, page_size=page_size, status=status, scene_id=scene_id)


@router.post("/start", response_model=SessionResponse, status_code=status.HTTP_201_CREATED)
async def start_session(
    body: StartSessionRequest,
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    if body.scene_id is not None:
        result = await db.execute(select(Scene).where(Scene.id == body.scene_id, Scene.is_active == True))
        scene = result.scalar_one_or_none()
        if scene is None:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Scene not found")

    session = Session(
        user_id=user.id,
        scene_id=body.scene_id,
        custom_scene_id=body.custom_scene_id,
        difficulty=body.difficulty,
        mode=body.mode if body.mode in ("immersive", "practice") else "immersive",
    )
    db.add(session)
    await db.commit()
    await db.refresh(session)
    return SessionResponse(
        session_id=session.id,
        scene_id=session.scene_id,
        custom_scene_id=session.custom_scene_id,
        difficulty=session.difficulty,
        mode=session.mode,
        status=session.status,
        started_at=session.started_at,
    )


@router.post("/{session_id}/end", response_model=EndSessionResponse)
async def end_session(
    session_id: uuid.UUID,
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    result = await db.execute(
        select(Session).where(Session.id == session_id, Session.user_id == user.id)
    )
    session = result.scalar_one_or_none()
    if session is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Session not found")
    if session.status != "active":
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Session already ended")

    now = datetime.utcnow()
    session.status = "completed"
    session.ended_at = now
    duration = int((now - session.started_at.replace(tzinfo=None)).total_seconds())
    session.duration_seconds = duration
    await db.commit()

    # Generate progress snapshot and weakness records
    from ..services.progress_service import (
        generate_progress_snapshot,
        update_weakness_records,
    )
    await generate_progress_snapshot(db, session.id)
    await update_weakness_records(db, session.id)

    return EndSessionResponse(
        session_id=session.id,
        status=session.status,
        duration_seconds=duration,
    )


@router.get("/{session_id}/messages", response_model=list[UtteranceBrief])
async def get_messages(
    session_id: uuid.UUID,
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    # verify ownership
    session_result = await db.execute(
        select(Session).where(Session.id == session_id, Session.user_id == user.id)
    )
    if session_result.scalar_one_or_none() is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Session not found")

    result = await db.execute(
        select(Utterance)
        .where(Utterance.session_id == session_id)
        .order_by(Utterance.sequence)
    )
    utterances = result.scalars().all()
    return [
        UtteranceBrief(
            utterance_id=u.id,
            speaker=u.speaker,
            text=u.text,
            sequence=u.sequence,
        )
        for u in utterances
    ]


@router.delete("/{session_id}/audio", summary="删除会话音频数据")
async def delete_session_audio(
    session_id: uuid.UUID,
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """V1.1: Delete audio data for a session (privacy compliance)."""
    result = await db.execute(
        select(Session).where(Session.id == session_id, Session.user_id == user.id)
    )
    if result.scalar_one_or_none() is None:
        raise HTTPException(status_code=404, detail="Session not found")

    # Clear audio URLs from utterances
    utt_result = await db.execute(
        select(Utterance).where(Utterance.session_id == session_id)
    )
    for u in utt_result.scalars().all():
        u.audio_url = None
        u.tts_audio_url = None
    await db.commit()
    return {"status": "deleted", "session_id": str(session_id)}


@router.get("/history", response_model=list[SessionHistory])
async def list_history(
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    result = await db.execute(
        select(Session)
        .where(Session.user_id == user.id)
        .order_by(Session.started_at.desc())
        .limit(50)
    )
    sessions = result.scalars().all()
    history: list[SessionHistory] = []
    for sess in sessions:
        scene_name = None
        if sess.scene_id:
            scene_result = await db.execute(select(Scene.name).where(Scene.id == sess.scene_id))
            scene_name = scene_result.scalar_one_or_none()
        history.append(
            SessionHistory(
                session_id=sess.id,
                scene_id=sess.scene_id,
                scene_name=scene_name,
                date=sess.started_at,
                duration_seconds=sess.duration_seconds or 0,
                total_score=0,
            )
        )
    return history
