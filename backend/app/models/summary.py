import uuid
from datetime import datetime
from typing import Optional

from sqlalchemy import ForeignKey, SmallInteger, Text
from sqlalchemy.dialects.postgresql import JSONB, UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from .base import Base
from .session import Session


class SessionSummary(Base):
    __tablename__ = "session_summaries"

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, default=uuid.uuid4
    )
    session_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("sessions.id", ondelete="CASCADE"),
        nullable=False,
        unique=True,
    )
    radar_fluency: Mapped[Optional[int]] = mapped_column(SmallInteger, nullable=True)
    radar_vocabulary: Mapped[Optional[int]] = mapped_column(SmallInteger, nullable=True)
    radar_grammar: Mapped[Optional[int]] = mapped_column(SmallInteger, nullable=True)
    radar_pronunciation: Mapped[Optional[int]] = mapped_column(
        SmallInteger, nullable=True
    )
    radar_interaction: Mapped[Optional[int]] = mapped_column(
        SmallInteger, nullable=True
    )
    highlights: Mapped[Optional[list]] = mapped_column(JSONB, nullable=True)
    practice_suggestions: Mapped[Optional[list]] = mapped_column(JSONB, nullable=True)
    share_image_url: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    created_at: Mapped[datetime] = mapped_column(default=lambda: datetime.utcnow())

    session: Mapped["Session"] = relationship(back_populates="summary")