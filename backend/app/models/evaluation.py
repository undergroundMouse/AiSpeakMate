import uuid
from datetime import datetime
from typing import Optional

from sqlalchemy import (
    Boolean,
    CheckConstraint,
    Float,
    ForeignKey,
    Integer,
    JSON,
    SmallInteger,
    String,
    Text,
)
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from .base import Base
from .session import Utterance


class PronunciationEvaluation(Base):
    __tablename__ = "pronunciation_evaluations"
    __table_args__ = (
        CheckConstraint(
            "overall_score >= 0 AND overall_score <= 100",
            name="ck_pron_overall_range",
        ),
    )

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, default=uuid.uuid4
    )
    utterance_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("utterances.id", ondelete="CASCADE"),
        nullable=False,
        unique=True,
    )
    overall_score: Mapped[int] = mapped_column(SmallInteger, nullable=False)
    pronunciation_score: Mapped[Optional[int]] = mapped_column(SmallInteger, nullable=True)
    fluency_score: Mapped[Optional[int]] = mapped_column(SmallInteger, nullable=True)
    completeness_score: Mapped[Optional[int]] = mapped_column(SmallInteger, nullable=True)
    prosody_score: Mapped[Optional[int]] = mapped_column(SmallInteger, nullable=True)
    advice: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    detail_json: Mapped[Optional[dict]] = mapped_column(JSON, nullable=True)
    evaluated_at: Mapped[datetime] = mapped_column(default=lambda: datetime.utcnow())

    utterance: Mapped["Utterance"] = relationship(back_populates="pronunciation")
    phoneme_scores: Mapped[list["PhonemeScore"]] = relationship(
        back_populates="evaluation", cascade="all, delete-orphan",
    )


class PhonemeScore(Base):
    __tablename__ = "phoneme_scores"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    evaluation_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("pronunciation_evaluations.id", ondelete="CASCADE"),
        nullable=False,
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


class GrammarError(Base):
    __tablename__ = "grammar_errors"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    utterance_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("utterances.id", ondelete="CASCADE"),
        nullable=False,
    )
    error_type: Mapped[str] = mapped_column(String(50), nullable=False)
    error_span_start: Mapped[int] = mapped_column(Integer, nullable=False)
    error_span_end: Mapped[int] = mapped_column(Integer, nullable=False)
    original_text: Mapped[str] = mapped_column(Text, nullable=False)
    correction: Mapped[str] = mapped_column(Text, nullable=False)
    corrected_sentence: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    explanation: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    severity: Mapped[str] = mapped_column(String(20), default="medium")
    is_expression_issue: Mapped[bool] = mapped_column(Boolean, default=False)
    created_at: Mapped[datetime] = mapped_column(default=lambda: datetime.utcnow())

    utterance: Mapped["Utterance"] = relationship(back_populates="grammar_errors")