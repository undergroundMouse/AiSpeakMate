from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from .api.auth import router as auth_router
from .api.scene import router as scene_router
from .api.session import router as session_router
from .api.ws import router as ws_router
from .core.config import settings

app = FastAPI(title=settings.app_name, debug=settings.debug)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["http://localhost:5173", "http://127.0.0.1:5173"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(auth_router, prefix="/api/v1")
app.include_router(scene_router, prefix="/api/v1")
app.include_router(session_router, prefix="/api/v1")
app.include_router(ws_router, prefix="/api/v1")


@app.get("/api/health")
async def health():
    return {"status": "ok", "app": settings.app_name}
