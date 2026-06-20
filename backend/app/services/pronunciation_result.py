"""Shared pronunciation evaluation result types."""

from __future__ import annotations

from dataclasses import dataclass, field


@dataclass
class PhonemeResult:
    word: str
    word_score: int
    phoneme: str
    phoneme_score: int
    is_error: bool
    suggested_phoneme: str | None = None
    start_time_ms: int = 0
    end_time_ms: int = 0


@dataclass
class PronunciationResult:
    overall_score: int
    pronunciation_score: int
    fluency_score: int
    completeness_score: int
    prosody_score: int
    advice: str | None
    phonemes: list[PhonemeResult] = field(default_factory=list)
    source: str = "iflytek_ise"
