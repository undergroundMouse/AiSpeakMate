import uuid
from datetime import date, datetime
from typing import Optional

from pydantic import BaseModel, Field


# --- Session Summary ---

class RadarScores(BaseModel):
    fluency: int = Field(ge=0, le=100)
    vocabulary: int = Field(ge=0, le=100)
    grammar: int = Field(ge=0, le=100)
    pronunciation: int = Field(ge=0, le=100)
    interaction: int = Field(ge=0, le=100)


class Highlight(BaseModel):
    title: str
    description: str
    example_sentence: str | None = None


class PracticeSuggestion(BaseModel):
    title: str
    description: str
    resource_type: str | None = None  # "video", "article", "exercise"
    resource_url: str | None = None


class TopPronunciationError(BaseModel):
    utterance_id: uuid.UUID
    sentence: str
    score: int
    detail_url: str


class TopGrammarError(BaseModel):
    utterance_id: uuid.UUID
    original: str
    error_type: str
    error_span: dict
    correction: str
    corrected_sentence: str | None = None
    explanation: str | None = None
    severity: str = "medium"


class SessionSummaryResponse(BaseModel):
    id: uuid.UUID
    session_id: uuid.UUID
    scene_name: str | None = None
    duration_seconds: int = 0
    radar: RadarScores
    highlights: list[Highlight] = []
    top_pronunciation_errors: list[TopPronunciationError] = []
    top_grammar_errors: list[TopGrammarError] = []
    practice_suggestions: list[PracticeSuggestion] = []
    share_image_url: str | None = None
    created_at: datetime

    class Config:
        from_attributes = True


# --- User Progress ---

class ProgressSnapshot(BaseModel):
    snapshot_date: date
    total_score: int
    dimension_scores: dict  # {"fluency": 60, "vocabulary": 55, ...}
    session_count: int
    total_duration_seconds: int


class WeaknessRecord(BaseModel):
    period_start: date
    period_end: date
    category: str  # "pronunciation" or "grammar"
    item: str
    error_count: int
    trend: str | None = None  # "rising", "falling", "stable"


class UserProgressResponse(BaseModel):
    user_id: uuid.UUID
    overall_rating: str  # "A1"-"C2" or "beginner"-"advanced"
    total_score: int = Field(ge=0, le=100)
    total_sessions: int
    total_hours: float
    snapshots: list[ProgressSnapshot] = []
    weaknesses: list[WeaknessRecord] = []
    strengths: list[dict] = []


# --- Achievements ---

class AchievementInfo(BaseModel):
    achievement_key: str
    title: str
    description: str
    icon: str | None = None
    unlocked_at: datetime | None = None
    progress: float = 0.0  # 0.0 - 1.0

    class Config:
        from_attributes = True


class AchievementListResponse(BaseModel):
    user_id: uuid.UUID
    achievements: list[AchievementInfo] = []
    total_locked: int = 0


# --- Progress Trend ---

class TrendPoint(BaseModel):
    date: date
    score: int
    dimension: str | None = None  # None when dimension="all"


class ProgressTrendResponse(BaseModel):
    points: list[TrendPoint] = []


# --- Weakness Distribution ---

class WeaknessDistItem(BaseModel):
    category: str
    item: str
    total_error_count: int
    trend: str | None = None


class WeaknessDistResponse(BaseModel):
    user_id: uuid.UUID
    period_start: date
    period_end: date
    items: list[WeaknessDistItem] = []
