import uuid
from datetime import date, datetime
from typing import Optional

from typing import Literal

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
    type: str
    target: str
    suggested_exercise_id: str | None = None


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


class CoachCardInsight(BaseModel):
    type: Literal["strength", "improvement"]
    text: str
    detail: str | None = None


class CoachCardResponse(BaseModel):
    scene_name: str
    duration_seconds: int
    overall_score: int | None = Field(default=None, ge=0, le=100)
    strengths: list[CoachCardInsight] = []
    improvements: list[CoachCardInsight] = []
    score_delta: int | None = None
    chat_only: bool = False


class NextPracticeOption(BaseModel):
    kind: Literal["consolidate", "explore"]
    scene_id: int
    scene_name: str
    label: str
    reason: str


class NextPracticeResponse(BaseModel):
    options: list[NextPracticeOption]


class SessionSummaryResponse(BaseModel):
    id: uuid.UUID
    session_id: uuid.UUID
    scene_name: str | None = None
    duration_seconds: int = 0
    radar_scores: RadarScores
    highlights: list[Highlight] = []
    top_pronunciation_errors: list[TopPronunciationError] = []
    top_grammar_errors: list[TopGrammarError] = []
    practice_suggestions: list[PracticeSuggestion] = []
    share_image_url: str | None = None
    coach_card: CoachCardResponse | None = None
    next_practice_options: list[NextPracticeOption] = []
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


class ProgressProvenance(BaseModel):
    pronunciation: str = "none"  # iflytek_ise | text_analysis | none
    fluency: str = "none"
    grammar: str = "none"  # evaluation | none
    vocabulary: str = "none"  # heuristic | none
    interaction: str = "none"  # heuristic | none
    strengths: str = "none"  # computed | none


class DimensionAvailable(BaseModel):
    pronunciation: bool = False
    fluency: bool = False
    grammar: bool = False
    vocabulary: bool = False
    interaction: bool = False


class UserProgressResponse(BaseModel):
    user_id: uuid.UUID
    overall_rating: str  # "A1"-"C2" or "beginner"-"advanced"
    total_score: int = Field(ge=0, le=100)
    total_sessions: int
    total_hours: float
    snapshots: list[ProgressSnapshot] = []
    weaknesses: list[WeaknessRecord] = []
    strengths: list[dict] = []
    data_provenance: ProgressProvenance = Field(default_factory=ProgressProvenance)
    dimension_available: DimensionAvailable = Field(default_factory=DimensionAvailable)


# --- Achievements ---

class AchievementInfo(BaseModel):
    id: str
    title: str
    description: str
    current_progress: int = 0
    target: int = 100
    unlocked_at: datetime | None = None
    icon_url: str | None = None
    icon: str | None = None

    class Config:
        from_attributes = True


class AchievementListResponse(BaseModel):
    user_id: uuid.UUID
    achievements: list[AchievementInfo] = []


# --- Progress Trend ---

class TrendPoint(BaseModel):
    date: date
    score: int
    dimension: str | None = None  # None when dimension="all"


class ForecastPoint(BaseModel):
    date: date
    score: int
    confidence_interval_lower: int
    confidence_interval_upper: int


class ProgressTrendResponse(BaseModel):
    dimension: str = "total_score"
    granularity: str = "daily"
    data_points: list[TrendPoint] = []
    forecast: list[ForecastPoint] = []


# --- Weakness Distribution ---

class WeaknessDistItem(BaseModel):
    category: str
    item: str
    error_count: int
    trend: str | None = None
    suggested_exercise_id: str | None = None


class WeaknessDistResponse(BaseModel):
    user_id: uuid.UUID
    period: str = "last_month"
    weakness_matrix: list[WeaknessDistItem] = []
