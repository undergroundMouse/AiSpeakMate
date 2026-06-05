import uuid
from datetime import datetime, timezone
from typing import Optional

from sqlalchemy import DateTime, Float, ForeignKey, Integer, String, Text, func
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from .base import Base


class Session(Base):
    __tablename__ = "sessions"

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, default=uuid.uuid4
    )
    user_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("users.id"))
    scene_id: Mapped[Optional[int]] = mapped_column(ForeignKey("scenes.id"), nullable=True)
    custom_scene_id: Mapped[Optional[uuid.UUID]] = mapped_column(
        ForeignKey("custom_scenes.id"), nullable=True
    )
    difficulty: Mapped[str] = mapped_column(String(20), nullable=False)
    status: Mapped[str] = mapped_column(String(20), default="active")
    started_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=lambda: datetime.now(timezone.utc)
    )
    ended_at: Mapped[Optional[datetime]] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    duration_seconds: Mapped[Optional[int]] = mapped_column(Integer, nullable=True)

    user = relationship("User", back_populates="sessions")
    utterances: Mapped[list["Utterance"]] = relationship(back_populates="session")
    summary: Mapped[Optional["SessionSummary"]] = relationship(back_populates="session")


class Utterance(Base):
    __tablename__ = "utterances"

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, default=uuid.uuid4
    )
    session_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("sessions.id"))
    speaker: Mapped[str] = mapped_column(String(10), nullable=False)  # 'user' or 'ai'
    text: Mapped[str] = mapped_column(Text, nullable=False)
    asr_confidence: Mapped[Optional[float]] = mapped_column(Float, nullable=True)
    audio_url: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    tts_audio_url: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    sequence: Mapped[int] = mapped_column(Integer, nullable=False)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=lambda: datetime.now(timezone.utc)
    )

    session: Mapped["Session"] = relationship(back_populates="utterances")
    grammar_errors: Mapped[list["GrammarError"]] = relationship(back_populates="utterance")
    pronunciation: Mapped[Optional["PronunciationEvaluation"]] = relationship(
        back_populates="utterance"
    )