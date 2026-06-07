import uuid

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from ..core.database import get_db
from ..models.custom_scene import CustomScene
from ..models.scene import Scene, SceneCategory, SceneSentencePattern, SceneVocabulary
from ..models.user import User
from ..schemas.scene import (
    CategoryWithScenes,
    CustomSceneRequest,
    SceneBrief,
    SceneDetail,
    SceneListResponse,
    SentencePatternItem,
    VocabItem,
)
from .dependencies import get_current_user

router = APIRouter(prefix="/scenes", tags=["scenes"])


async def _build_scene_list(db: AsyncSession) -> SceneListResponse:
    result = await db.execute(
        select(SceneCategory)
        .where(SceneCategory.id.in_(
            select(Scene.category_id).where(Scene.is_active == True).distinct()
        ))
        .order_by(SceneCategory.sort_order)
        .options(selectinload(SceneCategory.scenes))
    )
    categories = result.scalars().all()

    cat_list: list[CategoryWithScenes] = []
    for cat in categories:
        scenes = [
            SceneBrief(
                scene_id=s.id,
                name=s.name,
                description=s.description,
                thumbnail_url=s.thumbnail_url,
                difficulty_levels=s.get_difficulty_levels(),
                tags=s.get_tags(),
            )
            for s in cat.scenes
            if s.is_active
        ]
        if scenes:
            cat_list.append(
                CategoryWithScenes(
                    category_id=cat.id,
                    category_name=cat.name,
                    icon_url=cat.icon_url,
                    scenes=scenes,
                )
            )
    return SceneListResponse(categories=cat_list)


@router.get("", response_model=SceneListResponse)
async def list_scenes(db: AsyncSession = Depends(get_db)):
    return await _build_scene_list(db)


@router.get("/random", response_model=SceneDetail)
async def get_random_scene(
    difficulty: str | None = None,
    db: AsyncSession = Depends(get_db),
):
    """Return a random active scene, optionally filtered by difficulty level."""
    import random

    # Load all active scenes with relationships for cross-DB compatibility
    result = await db.execute(
        select(Scene)
        .where(Scene.is_active == True)
        .options(
            selectinload(Scene.vocabulary),
            selectinload(Scene.sentence_patterns),
        )
    )
    all_scenes = result.scalars().all()

    if difficulty:
        all_scenes = [
            s for s in all_scenes
            if s.get_difficulty_levels() and difficulty in s.get_difficulty_levels()
        ]

    if not all_scenes:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="No active scene found",
        )

    scene = random.choice(all_scenes)

    vocab_list = [
        VocabItem(
            word=v.word,
            phonetic=v.phonetic,
            audio_url=v.audio_url,
            translation=v.translation,
        )
        for v in scene.vocabulary
    ]
    pattern_list = [
        SentencePatternItem(
            pattern=p.pattern,
            translation=p.translation,
            example=p.example,
        )
        for p in scene.sentence_patterns
    ]

    duration = None
    if scene.suggested_duration:
        duration = scene.suggested_duration // 60

    return SceneDetail(
        scene_id=scene.id,
        name=scene.name,
        role_prompt=scene.role_prompt,
        opening_line=scene.opening_line,
        vocab_list=vocab_list,
        sentence_patterns=pattern_list,
        difficulty_settings=scene.difficulty_settings,
        suggested_duration_minutes=duration,
    )


@router.get("/{scene_id}", response_model=SceneDetail)
async def get_scene_detail(
    scene_id: int,
    db: AsyncSession = Depends(get_db),
):
    result = await db.execute(
        select(Scene)
        .where(Scene.id == scene_id, Scene.is_active == True)
        .options(
            selectinload(Scene.vocabulary),
            selectinload(Scene.sentence_patterns),
        )
    )
    scene = result.scalar_one_or_none()
    if scene is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Scene not found",
        )

    vocab_list = [
        VocabItem(
            word=v.word,
            phonetic=v.phonetic,
            audio_url=v.audio_url,
            translation=v.translation,
        )
        for v in scene.vocabulary
    ]
    pattern_list = [
        SentencePatternItem(
            pattern=p.pattern,
            translation=p.translation,
            example=p.example,
        )
        for p in scene.sentence_patterns
    ]

    duration = None
    if scene.suggested_duration:
        duration = scene.suggested_duration // 60
    return SceneDetail(
        scene_id=scene.id,
        name=scene.name,
        role_prompt=scene.role_prompt,
        opening_line=scene.opening_line,
        vocab_list=vocab_list,
        sentence_patterns=pattern_list,
        difficulty_settings=scene.difficulty_settings,
        suggested_duration_minutes=duration,
    )


@router.get("/custom")
async def list_custom_scenes(
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """List all custom scenes created by the current user."""
    result = await db.execute(
        select(CustomScene)
        .where(CustomScene.user_id == user.id)
        .order_by(CustomScene.created_at.desc())
        .limit(20)
    )
    scenes = result.scalars().all()
    return [
        {
            "custom_scene_id": str(s.id),
            "topic": s.topic,
            "role_prompt": s.prompt_snapshot or f"You are {s.role or 'a conversation partner'}. Topic: {s.topic}.",
            "opening_line": f"Let's talk about {s.topic}. What do you think?",
            "difficulty": s.difficulty or "intermediate",
            "created_at": s.created_at.isoformat() if s.created_at else None,
        }
        for s in scenes
    ]


@router.post("/custom", status_code=status.HTTP_201_CREATED)
async def create_custom_scene(
    body: CustomSceneRequest,
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    custom = CustomScene(
        user_id=user.id,
        name=body.topic[:100],
        topic=body.topic,
        role=body.role,
        difficulty=body.difficulty,
        focus_grammar=body.focus_grammar,
        focus_vocab=body.focus_vocab,
        is_temporary=False,
    )
    db.add(custom)
    await db.commit()
    await db.refresh(custom)

    # Try to generate scene with AI
    role_prompt = ""
    opening_line = ""
    vocab_list = []
    pattern_list = []

    try:
        from ..services.llm_service import generate_response as llm_generate
        desc_text = body.description or ""
        desc_line = f"\nDescription: {desc_text}" if desc_text else ""
        prompt = f"""Create an English conversation practice scene about: {body.topic}{desc_line}
Role: {body.role or 'conversation partner'}
Difficulty: {body.difficulty}

Return ONLY a JSON object with these fields (no markdown, no explanation):
{{
  "role_prompt": "You are [role description]. [How to behave, tone, accent]. Keep response under 2 sentences.",
  "opening_line": "[First thing the AI says to start the conversation. Must be in English.]",
  "vocabulary": [{{"word": "...", "translation": "中文"}}, ... 5 words max],
  "sentence_patterns": [{{"pattern": "...", "translation": "中文含义"}}, ... 3 patterns max]
}}"""

        ai_response = await llm_generate(prompt, "You are a JSON API. Return valid JSON only.")
        if ai_response:
            import json as _json
            # Clean markdown fences if present
            ai_response = ai_response.strip().removeprefix("```json").removesuffix("```").strip()
            data = _json.loads(ai_response)
            role_prompt = data.get("role_prompt", "")
            opening_line = data.get("opening_line", "")
            for v in data.get("vocabulary", []):
                vocab_list.append({"word": v.get("word", ""), "translation": v.get("translation", "")})
            for p in data.get("sentence_patterns", []):
                pattern_list.append({"pattern": p.get("pattern", ""), "translation": p.get("translation", "")})
    except Exception as e:
        print(f"AI scene generation failed: {e}")

    # Save AI-generated prompt to DB
    if role_prompt:
        custom.prompt_snapshot = role_prompt
        await db.commit()

    # Fallback if AI failed
    if not role_prompt:
        role_name = body.role or "an English conversation partner"
        role_prompt = f"You are {role_name}. Talk about: {body.topic}. Keep the conversation at {body.difficulty} level."
    if not opening_line:
        opening_line = f"Hi! Let's talk about {body.topic}. What do you think about this topic?"

    return {
        "custom_scene_id": str(custom.id),
        "topic": body.topic,
        "role_prompt": role_prompt,
        "opening_line": opening_line,
        "vocab_list": vocab_list,
        "sentence_patterns": pattern_list,
    }
