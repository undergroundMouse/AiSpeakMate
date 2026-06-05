from typing import Optional

from sqlalchemy import Boolean, ForeignKey, Integer, String, Text, func
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column, relationship

from .base import Base


class SceneCategory(Base):
    __tablename__ = "scene_categories"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    name: Mapped[str] = mapped_column(String(50), nullable=False)
    icon_url: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    sort_order: Mapped[int] = mapped_column(Integer, default=0)

    scenes: Mapped[list["Scene"]] = relationship(back_populates="category")


class Scene(Base):
    __tablename__ = "scenes"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    category_id: Mapped[int] = mapped_column(ForeignKey("scene_categories.id"))
    name: Mapped[str] = mapped_column(String(100), nullable=False)
    description: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    thumbnail_url: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    role_prompt: Mapped[str] = mapped_column(Text, nullable=False)
    opening_line: Mapped[str] = mapped_column(Text, nullable=False)
    difficulty_levels: Mapped[dict] = mapped_column(JSONB, nullable=False)
    difficulty_settings: Mapped[Optional[dict]] = mapped_column(JSONB, nullable=True)
    tags: Mapped[Optional[dict]] = mapped_column(JSONB, nullable=True)
    suggested_duration: Mapped[int] = mapped_column(Integer, default=300)
    is_active: Mapped[bool] = mapped_column(Boolean, default=True)
    created_at: Mapped[str] = mapped_column(Text, server_default=func.now())

    category: Mapped["SceneCategory"] = relationship(back_populates="scenes")
    vocabulary: Mapped[list["SceneVocabulary"]] = relationship(back_populates="scene")
    sentence_patterns: Mapped[list["SceneSentencePattern"]] = relationship(back_populates="scene")


class SceneVocabulary(Base):
    __tablename__ = "scene_vocabulary"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    scene_id: Mapped[int] = mapped_column(ForeignKey("scenes.id"))
    word: Mapped[str] = mapped_column(String(100), nullable=False)
    phonetic: Mapped[Optional[str]] = mapped_column(String(100), nullable=True)
    translation: Mapped[Optional[str]] = mapped_column(String(200), nullable=True)
    audio_url: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    part_of_speech: Mapped[Optional[str]] = mapped_column(String(20), nullable=True)

    scene: Mapped["Scene"] = relationship(back_populates="vocabulary")


class SceneSentencePattern(Base):
    __tablename__ = "scene_sentence_patterns"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    scene_id: Mapped[int] = mapped_column(ForeignKey("scenes.id"))
    pattern: Mapped[str] = mapped_column(Text, nullable=False)
    translation: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    example: Mapped[Optional[str]] = mapped_column(Text, nullable=True)

    scene: Mapped["Scene"] = relationship(back_populates="sentence_patterns")