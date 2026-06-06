import uuid
from datetime import datetime
from typing import Optional

from sqlalchemy import Boolean, ForeignKey, String, Text
from sqlalchemy.dialects.postgresql import JSONB, UUID
from sqlalchemy.orm import Mapped, mapped_column

from .base import Base


class CustomScene(Base):
    __tablename__ = "custom_scenes"

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, default=uuid.uuid4
    )
    user_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("users.id", ondelete="CASCADE"),
        nullable=False,
    )
    name: Mapped[str] = mapped_column(String(100), nullable=False)
    topic: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    role: Mapped[Optional[str]] = mapped_column(String(50), nullable=True)
    difficulty: Mapped[Optional[str]] = mapped_column(String(20), nullable=True)
    focus_grammar: Mapped[Optional[list]] = mapped_column(JSONB, nullable=True)
    focus_vocab: Mapped[Optional[list]] = mapped_column(JSONB, nullable=True)
    prompt_snapshot: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    is_temporary: Mapped[bool] = mapped_column(Boolean, default=False)
    created_at: Mapped[datetime] = mapped_column(
        default=lambda: datetime.utcnow(),
    )