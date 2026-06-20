"""iFlytek Online TTS (WebSocket v2) integration."""

from __future__ import annotations

import asyncio
import base64
import hashlib
import hmac
import json
import logging
from datetime import datetime
from pathlib import Path
from time import mktime
from urllib.parse import urlencode
from wsgiref.handlers import format_date_time

import websockets

from ..core.config import settings

logger = logging.getLogger(__name__)

VOICE_MAP: dict[str, str] = {
    "en-US-female": "x4_enus_lila_assist",
    "en-US-male": "x4_enus_cassius_assist",
    "en-GB-female": "x4_enus_lila_assist",
    "en-GB-male": "x4_enus_cassius_assist",
}

DEFAULT_VOICE_KEY = "en-US-female"
DEFAULT_SPEED = 50
TTS_TIMEOUT_SECONDS = 30

_runtime_credentials: dict[str, str] = {}
_CREDENTIALS_FILE = Path(__file__).resolve().parents[2] / ".runtime_iflytek.json"


def _load_persisted_credentials() -> None:
    if not _CREDENTIALS_FILE.exists():
        return
    try:
        data = json.loads(_CREDENTIALS_FILE.read_text(encoding="utf-8"))
        for key in ("app_id", "api_key", "api_secret"):
            value = (data.get(key) or "").strip()
            if value:
                _runtime_credentials[key] = value
        if _runtime_credentials:
            logger.info("Loaded iFlytek credentials from %s", _CREDENTIALS_FILE.name)
    except Exception as exc:
        logger.warning("Failed to load persisted iFlytek credentials: %s", exc)


def _persist_credentials() -> None:
    if not _runtime_credentials:
        return
    try:
        _CREDENTIALS_FILE.write_text(
            json.dumps(_runtime_credentials, ensure_ascii=False, indent=2),
            encoding="utf-8",
        )
    except Exception as exc:
        logger.warning("Failed to persist iFlytek credentials: %s", exc)


def load_persisted_credentials() -> None:
    _load_persisted_credentials()


def set_runtime_credentials(app_id: str, api_key: str, api_secret: str) -> None:
    _runtime_credentials["app_id"] = app_id.strip()
    _runtime_credentials["api_key"] = api_key.strip()
    _runtime_credentials["api_secret"] = api_secret.strip()
    _persist_credentials()


_load_persisted_credentials()


def _app_id() -> str:
    return _runtime_credentials.get("app_id") or settings.iflytek_app_id


def _api_key() -> str:
    return _runtime_credentials.get("api_key") or settings.iflytek_api_key


def _api_secret() -> str:
    return _runtime_credentials.get("api_secret") or settings.iflytek_api_secret


def is_configured() -> bool:
    return bool(_app_id() and _api_key() and _api_secret())


def resolve_vcn(voice_key: str) -> str:
    return VOICE_MAP.get(voice_key, VOICE_MAP[DEFAULT_VOICE_KEY])


def build_auth_url(
    host: str | None = None,
    path: str | None = None,
) -> str:
    host = host or settings.iflytek_tts_host
    path = path or settings.iflytek_tts_path
    date = format_date_time(mktime(datetime.now().timetuple()))

    signature_origin = (
        f"host: {host}\n"
        f"date: {date}\n"
        f"GET {path} HTTP/1.1"
    )
    signature_sha = hmac.new(
        _api_secret().encode("utf-8"),
        signature_origin.encode("utf-8"),
        digestmod=hashlib.sha256,
    ).digest()
    signature = base64.b64encode(signature_sha).decode("utf-8")

    authorization_origin = (
        f'api_key="{_api_key()}", '
        f'algorithm="hmac-sha256", '
        f'headers="host date request-line", '
        f'signature="{signature}"'
    )
    authorization = base64.b64encode(authorization_origin.encode("utf-8")).decode("utf-8")

    query = urlencode({"authorization": authorization, "date": date, "host": host})
    return f"wss://{host}{path}?{query}"


def _build_request_frame(text: str, voice_key: str, speed: int) -> dict:
    return {
        "common": {"app_id": _app_id()},
        "business": {
            "aue": "lame",
            "vcn": resolve_vcn(voice_key),
            "speed": max(0, min(100, speed)),
            "volume": 50,
            "pitch": 50,
            "tte": "UTF8",
        },
        "data": {
            "status": 2,
            "text": base64.b64encode(text.encode("utf-8")).decode("utf-8"),
        },
    }


async def _synthesize_once(text: str, voice_key: str, speed: int) -> bytes | None:
    if not text.strip():
        return None

    url = build_auth_url()
    frame = json.dumps(_build_request_frame(text, voice_key, speed))
    audio_parts: list[bytes] = []

    async with websockets.connect(url, open_timeout=TTS_TIMEOUT_SECONDS) as ws:
        await ws.send(frame)
        async for message in ws:
            payload = json.loads(message)
            code = payload.get("code", -1)
            if code != 0:
                msg = payload.get("message", "unknown error")
                raise RuntimeError(f"iFlytek TTS error {code}: {msg}")

            audio_b64 = payload.get("data", {}).get("audio")
            if audio_b64:
                audio_parts.append(base64.b64decode(audio_b64))

            if payload.get("data", {}).get("status") == 2:
                break

    if not audio_parts:
        return None
    return b"".join(audio_parts)


async def synthesize_mp3(
    text: str,
    voice_key: str = DEFAULT_VOICE_KEY,
    speed: int = DEFAULT_SPEED,
) -> bytes | None:
    """Synthesize text to MP3 bytes via iFlytek WebSocket TTS."""
    if not is_configured():
        return None

    try:
        return await asyncio.wait_for(
            _synthesize_once(text, voice_key, speed),
            timeout=TTS_TIMEOUT_SECONDS,
        )
    except asyncio.TimeoutError:
        logger.warning("iFlytek TTS timed out after %ss", TTS_TIMEOUT_SECONDS)
        return None
    except Exception as exc:
        logger.warning("iFlytek TTS failed: %s", exc)
        return None
