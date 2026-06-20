"""User-configurable runtime settings."""

from fastapi import APIRouter, Depends
from pydantic import BaseModel, Field

from ..services.iflytek_tts_service import is_configured as iflytek_tts_configured
from ..services.iflytek_tts_service import set_runtime_credentials as set_iflytek_credentials
from ..services.llm_service import is_llm_configured, set_runtime_llm
from ..services.speechsuper_service import is_configured as speechsuper_configured
from ..services.speechsuper_service import set_runtime_credentials as set_speechsuper_credentials
from .dependencies import get_current_user

router = APIRouter(prefix="/settings", tags=["settings"])


class LlmSettingsRequest(BaseModel):
    provider: str = Field(..., min_length=1)
    api_key: str = Field(..., min_length=1)
    model: str = ""


class IflytekTtsSettingsRequest(BaseModel):
    app_id: str = Field(..., min_length=1)
    api_key: str = Field(..., min_length=1)
    api_secret: str = Field(..., min_length=1)


class SpeechSuperSettingsRequest(BaseModel):
    app_key: str = Field(..., min_length=1)
    secret_key: str = Field(..., min_length=1)


@router.get("/apis")
async def get_apis_status(_user=Depends(get_current_user)):
    return {
        "llm": {"configured": is_llm_configured()},
        "iflytek_tts": {"configured": iflytek_tts_configured()},
        "speechsuper": {"configured": speechsuper_configured()},
    }


@router.put("/llm")
async def update_llm_settings(
    body: LlmSettingsRequest,
    _user=Depends(get_current_user),
):
    set_runtime_llm(body.provider, body.api_key, body.model)
    return {"configured": is_llm_configured()}


@router.put("/iflytek-tts")
async def update_iflytek_tts_settings(
    body: IflytekTtsSettingsRequest,
    _user=Depends(get_current_user),
):
    set_iflytek_credentials(body.app_id, body.api_key, body.api_secret)
    return {"configured": iflytek_tts_configured()}


@router.get("/iflytek-tts")
async def get_iflytek_tts_settings(_user=Depends(get_current_user)):
    return {"configured": iflytek_tts_configured()}


@router.put("/speechsuper")
async def update_speechsuper_settings(
    body: SpeechSuperSettingsRequest,
    _user=Depends(get_current_user),
):
    set_speechsuper_credentials(body.app_key, body.secret_key)
    return {"configured": speechsuper_configured()}
