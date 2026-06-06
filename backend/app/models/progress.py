import uuid
from datetime import date, datetime
from typing import Optional

from sqlalchemy import (
    BigInteger,
    CheckConstraint,
    ForeignKey,
    Integer,
    SmallInteger,
    String,
)
from sqlalchemy.dialects.postgresql import JSONB, UUID
from sqlalchemy.orm import Mapped, mapped_column

from .base import Base


class UserProgressSnapshot(Base):
    __tablename__ = "user_progress_snapshots"

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True)
    user_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("users.id", ondelete="CASCADE"),
        nullable=False,
    )
    snapshot_date: Mapped[date] = mapped_column(nullable=False)
    total_score: Mapped[int] = mapped_column(
        SmallInteger, nullable=False,
    )
    dimension_scores: Mapped[dict] = mapped_column(JSONB, nullable=False)
    session_count: Mapped[int] = mapped_column(Integer, default=0)
    total_duration_seconds: Mapped[int] = mapped_column(Integer, default=0)


class UserWeaknessRecord(Base):
    __tablename__ = "user_weakness_records"
    __table_args__ = (
        CheckConstraint(
            "category IN ('pronunciation', 'grammar')",
            name="ck_weakness_category",
        ),
    )

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True)
    user_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("users.id", ondelete="CASCADE"),
        nullable=False,
    )
    period_start: Mapped[date] = mapped_column(nullable=False)
    period_end: Mapped[date] = mapped_column(nullable=False)
    category: Mapped[str] = mapped_column(String(50), nullable=False)
    item: Mapped[str] = mapped_column(String(100), nullable=False)
    error_count: Mapped[int] = mapped_column(Integer, nullable=False)
    trend: Mapped[Optional[str]] = mapped_column(String(20), nullable=True)