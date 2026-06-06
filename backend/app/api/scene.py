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
        is_temporary=True,
    )
    db.add(custom)
    await db.commit()
    await db.refresh(custom)

    # Generate role_prompt and opening_line based on topic/role
    role_name = body.role or "an English conversation partner"
    role_prompt = f"You are {role_name}. Talk about: {body.topic}. Keep the conversation at {body.difficulty} level. Correct the user's grammar gently and encourage them."
    opening_line = f"Hi! Let's talk about {body.topic}. What do you think about this topic?"

    return {
        "custom_scene_id": str(custom.id),
        "topic": body.topic,
        "role_prompt": role_prompt,
        "opening_line": opening_line,
    }
