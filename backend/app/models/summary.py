import uuid
from typing import Optional

from sqlalchemy import ForeignKey, SmallInteger, Text, func
from sqlalchemy.dialects.postgresql import JSONB, UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from .base import Base


class SessionSummary(Base):
    __tablename__ = "session_summaries"

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, default=uuid.uuid4
    )
    session_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("sessions.id"), unique=True
    )
    radar_fluency: Mapped[Optional[int]] = mapped_column(SmallInteger, nullable=True)
    radar_vocabulary: Mapped[Optional[int]] = mapped_column(SmallInteger, nullable=True)
    radar_grammar: Mapped[Optional[int]] = mapped_column(SmallInteger, nullable=True)
    radar_pronunciation: Mapped[Optional[int]] = mapped_column(SmallInteger, nullable=True)
    radar_interaction: Mapped[Optional[int]] = mapped_column(SmallInteger, nullable=True)
    highlights: Mapped[Optional[dict]] = mapped_column(JSONB, nullable=True)
    practice_suggestions: Mapped[Optional[dict]] = mapped_column(JSONB, nullable=True)
    share_image_url: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    created_at: Mapped[str] = mapped_column(Text, server_default=func.now())

    session = relationship("Session", back_populates="summary")