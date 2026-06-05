import uuid
from datetime import datetime, timezone
from typing import Optional

from sqlalchemy import BigInteger, Boolean, DateTime, ForeignKey, Integer, SmallInteger, String, Text
from sqlalchemy.dialects.postgresql import JSONB, UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from .base import Base


class PronunciationEvaluation(Base):
    __tablename__ = "pronunciation_evaluations"

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, default=uuid.uuid4
    )
    utterance_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("utterances.id"), unique=True
    )
    overall_score: Mapped[int] = mapped_column(SmallInteger, nullable=False)
    pronunciation_score: Mapped[Optional[int]] = mapped_column(SmallInteger, nullable=True)
    fluency_score: Mapped[Optional[int]] = mapped_column(SmallInteger, nullable=True)
    completeness_score: Mapped[Optional[int]] = mapped_column(SmallInteger, nullable=True)
    prosody_score: Mapped[Optional[int]] = mapped_column(SmallInteger, nullable=True)
    advice: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    detail_json: Mapped[Optional[dict]] = mapped_column(JSONB, nullable=True)
    evaluated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=lambda: datetime.now(timezone.utc)
    )

    utterance: Mapped["Utterance"] = relationship(back_populates="pronunciation")
    phoneme_scores: Mapped[list["PhonemeScore"]] = relationship(
        back_populates="evaluation"
    )


class PhonemeScore(Base):
    __tablename__ = "phoneme_scores"

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=True)
    evaluation_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("pronunciation_evaluations.id")
    )
    word: Mapped[str] = mapped_column(String(100), nullable=False)
    word_score: Mapped[Optional[int]] = mapped_column(SmallInteger, nullable=True)
    phoneme: Mapped[str] = mapped_column(String(10), nullable=False)
    phoneme_score: Mapped[int] = mapped_column(SmallInteger, nullable=False)
    is_error: Mapped[bool] = mapped_column(Boolean, default=False)
    suggested_phoneme: Mapped[Optional[str]] = mapped_column(String(10), nullable=True)
    start_time_ms: Mapped[Optional[int]] = mapped_column(Integer, nullable=True)
    end_time_ms: Mapped[Optional[int]] = mapped_column(Integer, nullable=True)

    evaluation: Mapped["PronunciationEvaluation"] = relationship(
        back_populates="phoneme_scores"
    )