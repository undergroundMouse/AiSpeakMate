from datetime import datetime
from typing import Optional
from uuid import UUID

from pydantic import BaseModel


class StartSessionRequest(BaseModel):
    scene_id: Optional[int] = None
    custom_scene_id: Optional[UUID] = None
    difficulty: str = "intermediate"


class SessionResponse(BaseModel):
    session_id: UUID
    scene_id: Optional[int] = None
    custom_scene_id: Optional[UUID] = None
    difficulty: str
    status: str
    started_at: datetime


class UtteranceBrief(BaseModel):
    utterance_id: UUID
    speaker: str
    text: str
    sequence: int


class EndSessionResponse(BaseModel):
    session_id: UUID
    status: str
    duration_seconds: int


class SessionHistory(BaseModel):
    session_id: UUID
    scene_id: Optional[int] = None
    scene_name: Optional[str] = None
    difficulty: str
    status: str
    started_at: datetime
    ended_at: Optional[datetime] = None
    utterance_count: int = 0