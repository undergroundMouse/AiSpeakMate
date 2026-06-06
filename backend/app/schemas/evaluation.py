import uuid
from datetime import datetime
from typing import Optional

from pydantic import BaseModel, Field


# --- Pronunciation ---

class PhonemeScoreOut(BaseModel):
    word: str
    word_score: int | None = None
    phoneme: str
    phoneme_score: int
    is_error: bool = False
    suggested_phoneme: str | None = None
    start_time_ms: int | None = None
    end_time_ms: int | None = None

    class Config:
        from_attributes = True


class WordScoreOut(BaseModel):
    word: str
    score: int
    phonemes: list["PhonemeScoreOut"] | None = None

    class Config:
        from_attributes = True


class ProsodyOut(BaseModel):
    intonation_score: int | None = None
    rhythm_score: int | None = None
    stress_errors: list[dict] | None = None


class PronunciationEvaluateRequest(BaseModel):
    reference_text: str = Field(..., min_length=1, max_length=2000)
    language: str = "en-US"
    detail_level: str = "full"  # "basic" or "full"


class PronunciationEvaluateResponse(BaseModel):
    overall_score: int
    pronunciation_score: int | None = None
    fluency_score: int | None = None
    completeness_score: int | None = None
    words: list[WordScoreOut] | None = None
    prosody: ProsodyOut | None = None
    advice: str | None = None


class PronunciationDetailResponse(BaseModel):
    utterance_id: uuid.UUID
    overall_score: int
    pronunciation_score: int | None = None
    fluency_score: int | None = None
    completeness_score: int | None = None
    words: list[WordScoreOut] | None = None
    prosody: ProsodyOut | None = None
    advice: str | None = None
    evaluated_at: datetime | None = None


# --- Grammar ---

class GrammarErrorOut(BaseModel):
    utterance_id: uuid.UUID
    original: str
    error_type: str
    error_span: dict  # {"start": int, "end": int}
    correction: str
    corrected_sentence: str | None = None
    explanation: str | None = None
    severity: str = "medium"

    class Config:
        from_attributes = True


class GrammarReportResponse(BaseModel):
    session_id: uuid.UUID
    errors: list[GrammarErrorOut] = []
    optimization_suggestions: list[dict] = []
    total_errors: int = 0
    total_suggestions: int = 0


class GrammarCorrectRequest(BaseModel):
    text: str = Field(..., min_length=1, max_length=2000)
    mode: str = "full"  # "light" or "full"


class GrammarCorrectResponse(BaseModel):
    original: str
    errors: list[GrammarErrorOut] = []
    corrected_text: str | None = None
    optimization_suggestions: list[dict] = []