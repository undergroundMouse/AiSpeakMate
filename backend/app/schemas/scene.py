from typing import Optional

from pydantic import BaseModel


class VocabItem(BaseModel):
    word: str
    phonetic: Optional[str] = None
    audio_url: Optional[str] = None
    translation: Optional[str] = None


class SentencePatternItem(BaseModel):
    pattern: str
    translation: Optional[str] = None
    example: Optional[str] = None


class SceneBrief(BaseModel):
    scene_id: int
    name: str
    description: Optional[str] = None
    thumbnail_url: Optional[str] = None
    difficulty_levels: list[str]
    tags: Optional[list[str]] = None


class SceneDetail(BaseModel):
    scene_id: int
    name: str
    role_prompt: str
    opening_line: str
    vocab_list: list[VocabItem]
    sentence_patterns: list[SentencePatternItem]
    difficulty_settings: Optional[dict] = None
    suggested_duration_minutes: Optional[int] = None


class CategoryWithScenes(BaseModel):
    category_id: int
    category_name: str
    icon_url: Optional[str] = None
    scenes: list[SceneBrief]


class SceneListResponse(BaseModel):
    categories: list[CategoryWithScenes]


class CustomSceneRequest(BaseModel):
    topic: str
    description: Optional[str] = None
    role: Optional[str] = None
    difficulty: str = "intermediate"
    focus_grammar: Optional[list[str]] = None
    focus_vocab: Optional[list[str]] = None