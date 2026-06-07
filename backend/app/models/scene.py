from typing import Optional

from sqlalchemy import Boolean, ForeignKey, Integer, String, Text
from sqlalchemy import JSON
from sqlalchemy.orm import Mapped, mapped_column, relationship

from .base import Base


class SceneCategory(Base):
    __tablename__ = "scene_categories"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    name: Mapped[str] = mapped_column(String(50), nullable=False)
    icon_url: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    sort_order: Mapped[int] = mapped_column(Integer, default=0)

    scenes: Mapped[list["Scene"]] = relationship(back_populates="category")


class Scene(Base):
    __tablename__ = "scenes"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    category_id: Mapped[int] = mapped_column(
        Integer, ForeignKey("scene_categories.id"), nullable=False
    )
    name: Mapped[str] = mapped_column(String(100), nullable=False)
    description: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    thumbnail_url: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    role_prompt: Mapped[str] = mapped_column(Text, nullable=False)
    opening_line: Mapped[str] = mapped_column(Text, nullable=False)
    difficulty_levels: Mapped[list] = mapped_column(
        JSON, nullable=False, default=lambda: ["beginner", "intermediate", "advanced"]
    )
    difficulty_settings: Mapped[Optional[dict]] = mapped_column(JSON, nullable=True)
    tags: Mapped[Optional[list]] = mapped_column(JSON, nullable=True)
    suggested_duration: Mapped[int] = mapped_column(Integer, default=300)
    is_active: Mapped[bool] = mapped_column(Boolean, default=True)

    category: Mapped["SceneCategory"] = relationship(back_populates="scenes")
    vocabulary: Mapped[list["SceneVocabulary"]] = relationship(
        back_populates="scene", cascade="all, delete-orphan"
    )
    sentence_patterns: Mapped[list["SceneSentencePattern"]] = relationship(
        back_populates="scene", cascade="all, delete-orphan"
    )

    def get_difficulty_levels(self) -> list[str]:
        """Return difficulty_levels as a list, handling both JSON-decoded
        lists and legacy double-encoded JSON strings."""
        if self.difficulty_levels is None:
            return []
        if isinstance(self.difficulty_levels, list):
            return self.difficulty_levels
        return []

    def get_tags(self) -> list[str]:
        """Return tags as a list, handling both JSON-decoded
        lists and legacy double-encoded JSON strings."""
        if self.tags is None:
            return []
        if isinstance(self.tags, list):
            return self.tags
        return []


class SceneVocabulary(Base):
    __tablename__ = "scene_vocabulary"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    scene_id: Mapped[int] = mapped_column(
        Integer, ForeignKey("scenes.id", ondelete="CASCADE"), nullable=False
    )
    word: Mapped[str] = mapped_column(String(100), nullable=False)
    phonetic: Mapped[Optional[str]] = mapped_column(String(100), nullable=True)
    translation: Mapped[Optional[str]] = mapped_column(String(200), nullable=True)
    audio_url: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    part_of_speech: Mapped[Optional[str]] = mapped_column(String(20), nullable=True)

    scene: Mapped["Scene"] = relationship(back_populates="vocabulary")


class SceneSentencePattern(Base):
    __tablename__ = "scene_sentence_patterns"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    scene_id: Mapped[int] = mapped_column(
        Integer, ForeignKey("scenes.id", ondelete="CASCADE"), nullable=False
    )
    pattern: Mapped[str] = mapped_column(Text, nullable=False)
    translation: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    example: Mapped[Optional[str]] = mapped_column(Text, nullable=True)

    scene: Mapped["Scene"] = relationship(back_populates="sentence_patterns")