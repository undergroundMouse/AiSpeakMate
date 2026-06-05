import uuid
from datetime import date
from typing import Optional

from sqlalchemy import BigInteger, Date, ForeignKey, Integer, SmallInteger, String, UniqueConstraint
from sqlalchemy.dialects.postgresql import JSONB, UUID
from sqlalchemy.orm import Mapped, mapped_column

from .base import Base


class UserProgressSnapshot(Base):
    __tablename__ = "user_progress_snapshots"

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=True)
    user_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("users.id"))
    snapshot_date: Mapped[date] = mapped_column(Date, nullable=False)
    total_score: Mapped[int] = mapped_column(SmallInteger, nullable=False)
    dimension_scores: Mapped[dict] = mapped_column(JSONB, nullable=False)
    session_count: Mapped[int] = mapped_column(Integer, default=0)
    total_duration_seconds: Mapped[int] = mapped_column(Integer, default=0)

    __table_args__ = (
        UniqueConstraint("user_id", "snapshot_date", name="uq_progress_user_date"),
    )


class UserWeaknessRecord(Base):
    __tablename__ = "user_weakness_records"

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=True)
    user_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("users.id"))
    period_start: Mapped[date] = mapped_column(Date, nullable=False)
    period_end: Mapped[date] = mapped_column(Date, nullable=False)
    category: Mapped[str] = mapped_column(String(50), nullable=False)
    item: Mapped[str] = mapped_column(String(100), nullable=False)
    error_count: Mapped[int] = mapped_column(Integer, nullable=False)
    trend: Mapped[Optional[str]] = mapped_column(String(20), nullable=True)

    __table_args__ = (
        UniqueConstraint(
            "user_id", "period_start", "period_end", "category", "item",
            name="uq_weakness_record"
        ),
    )