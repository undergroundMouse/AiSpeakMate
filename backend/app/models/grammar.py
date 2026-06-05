import uuid
from typing import Optional

from sqlalchemy import BigInteger, Boolean, ForeignKey, Integer, String, Text, func
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from .base import Base


class GrammarError(Base):
    __tablename__ = "grammar_errors"

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=True)
    utterance_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("utterances.id"))
    error_type: Mapped[str] = mapped_column(String(50), nullable=False)
    error_span_start: Mapped[int] = mapped_column(Integer, nullable=False)
    error_span_end: Mapped[int] = mapped_column(Integer, nullable=False)
    original_text: Mapped[str] = mapped_column(Text, nullable=False)
    correction: Mapped[str] = mapped_column(Text, nullable=False)
    corrected_sentence: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    explanation: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    severity: Mapped[str] = mapped_column(String(20), default="medium")
    is_expression_issue: Mapped[bool] = mapped_column(Boolean, default=False)
    created_at: Mapped[str] = mapped_column(Text, server_default=func.now())

    utterance = relationship("Utterance", back_populates="grammar_errors")