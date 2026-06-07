from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from .api.auth import router as auth_router
from .api.scene import router as scene_router
from .api.session import router as session_router
from .api.evaluation import router as evaluation_router
from .api.summary import router as summary_router
from .api.dictionary import router as dictionary_router
from .api.translate import router as translate_router
from .api.ws import router as ws_router
from .core.config import settings
from .core.database import get_db, init_db
from .services.seed_data import seed_scenes


@asynccontextmanager
async def lifespan(app: FastAPI):
    await init_db()
    async for db in get_db():
        await seed_scenes(db)
        break
    yield


app = FastAPI(
    title=settings.app_name,
    debug=settings.debug,
    lifespan=lifespan,
)

app.add_middleware(
    CORSMiddleware,
    allow_origin_regex=r"https?://(localhost|127\.0\.0\.1)(:\d+)?",
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(auth_router, prefix="/api/v1")
app.include_router(scene_router, prefix="/api/v1")
app.include_router(session_router, prefix="/api/v1")
app.include_router(evaluation_router, prefix="/api/v1")
app.include_router(summary_router, prefix="/api/v1")
app.include_router(dictionary_router, prefix="/api/v1")
app.include_router(translate_router, prefix="/api/v1")
app.include_router(ws_router, prefix="/api/v1")


@app.get("/api/health")
async def health():
    return {"status": "ok", "app": settings.app_name}
