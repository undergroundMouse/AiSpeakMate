import uuid
from datetime import datetime
from typing import Optional

from sqlalchemy import CheckConstraint, Float, ForeignKey, Integer, String, Text
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from .base import Base


class Session(Base):
    __tablename__ = "sessions"

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, default=uuid.uuid4
    )
    user_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("users.id", ondelete="CASCADE"),
        nullable=False,
    )
    scene_id: Mapped[Optional[int]] = mapped_column(
        Integer, ForeignKey("scenes.id"), nullable=True
    )
    custom_scene_id: Mapped[Optional[uuid.UUID]] = mapped_column(
        UUID(as_uuid=True), ForeignKey("custom_scenes.id"), nullable=True
    )
    difficulty: Mapped[str] = mapped_column(String(20), nullable=False)
    status: Mapped[str] = mapped_column(String(20), default="active")
    started_at: Mapped[datetime] = mapped_column(default=lambda: datetime.utcnow())
    ended_at: Mapped[Optional[datetime]] = mapped_column(nullable=True)
    duration_seconds: Mapped[Optional[int]] = mapped_column(Integer, nullable=True)

    utterances: Mapped[list["Utterance"]] = relationship(
        back_populates="session", cascade="all, delete-orphan",
        order_by="Utterance.sequence",
    )
    summary: Mapped[Optional["SessionSummary"]] = relationship(
        back_populates="session", cascade="all, delete-orphan",
    )


class Utterance(Base):
    __tablename__ = "utterances"
    __table_args__ = (
        CheckConstraint("speaker IN ('user', 'ai')", name="ck_utterances_speaker"),
    )

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, default=uuid.uuid4
    )
    session_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("sessions.id", ondelete="CASCADE"),
        nullable=False,
    )
    speaker: Mapped[str] = mapped_column(String(10), nullable=False)
    text: Mapped[str] = mapped_column(Text, nullable=False)
    asr_confidence: Mapped[Optional[float]] = mapped_column(Float, nullable=True)
    audio_url: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    tts_audio_url: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    sequence: Mapped[int] = mapped_column(Integer, nullable=False)
    created_at: Mapped[datetime] = mapped_column(default=lambda: datetime.utcnow())

    session: Mapped["Session"] = relationship(back_populates="utterances")
    pronunciation: Mapped[Optional["PronunciationEvaluation"]] = relationship(
        back_populates="utterance", cascade="all, delete-orphan",
    )
    grammar_errors: Mapped[list["GrammarError"]] = relationship(
        back_populates="utterance", cascade="all, delete-orphan",
    )