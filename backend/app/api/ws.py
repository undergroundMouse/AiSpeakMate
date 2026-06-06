import json
import uuid
from datetime import datetime, timezone

from fastapi import APIRouter, WebSocket, WebSocketDisconnect
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from ..core.database import get_db
from ..core.security import decode_access_token
from ..models.scene import Scene
from ..models.session import Session, Utterance

router = APIRouter()

# in-memory active session store
active_connections: dict[uuid.UUID, dict] = {}


async def _authenticate(websocket: WebSocket) -> uuid.UUID:
    token = websocket.query_params.get("token")
    if not token:
        await websocket.close(code=4001, reason="Missing token")
        return None
    payload = decode_access_token(token)
    if payload is None:
        await websocket.close(code=4001, reason="Invalid token")
        return None
    user_id = payload.get("sub")
    if not user_id:
        await websocket.close(code=4001, reason="Invalid token payload")
        return None
    try:
        return uuid.UUID(user_id)
    except ValueError:
        await websocket.close(code=4001, reason="Invalid user id in token")
        return None


async def _store_utterance(
    session_id: uuid.UUID,
    speaker: str,
    text: str,
    seq: int,
    audio_url: str | None = None,
):
    db_gen = get_db()
    db: AsyncSession = await anext(db_gen)
    utterance = Utterance(
        session_id=session_id,
        speaker=speaker,
        text=text,
        sequence=seq,
        audio_url=audio_url,
    )
    db.add(utterance)
    await db.commit()
    await db.refresh(utterance)
    return utterance


async def _get_session_data(db: AsyncSession, session_id: uuid.UUID):
    result = await db.execute(select(Session).where(Session.id == session_id))
    session = result.scalar_one_or_none()
    if session is None:
        return None

    scene_data = None
    if session.scene_id:
        scene_result = await db.execute(select(Scene).where(Scene.id == session.scene_id))
        scene = scene_result.scalar_one_or_none()
        if scene:
            scene_data = {
                "role_prompt": scene.role_prompt,
                "opening_line": scene.opening_line,
                "difficulty_settings": scene.difficulty_settings or {},
            }

    # count existing utterances for sequence
    stmt = select(Utterance).where(Utterance.session_id == session_id)
    utt_result = await db.execute(stmt)
    utterances = utt_result.scalars().all()

    return {
        "session": session,
        "scene_data": scene_data,
        "utterance_count": len(utterances),
    }


def _simulate_llm_response(text: str, scene_data: dict | None) -> str:
    responses = {
        "hello": "Hello! How are you today?",
        "hi": "Hi there! How can I help you practice your English today?",
        "i'm fine": "That's great to hear! What would you like to talk about?",
        "thank you": "You're welcome! Keep up the good practice.",
        "bye": "Goodbye! It was nice talking with you. See you next time!",
        "goodbye": "Goodbye! Great job with your English practice today!",
    }
    lower = text.strip().lower().rstrip(".!?")
    if lower in responses:
        return responses[lower]
    if scene_data and scene_data.get("opening_line"):
        return f"Good! Now, {scene_data['opening_line']}"
    return f"I see! That's interesting. Can you tell me more about that?"


@router.websocket("/ws")
async def websocket_endpoint(websocket: WebSocket):
    user_id = await _authenticate(websocket)
    if user_id is None:
        return

    await websocket.accept()

    current_session_id: uuid.UUID | None = None
    sequence_counter = 0
    db_gen = get_db()
    db: AsyncSession = await anext(db_gen)

    try:
        while True:
            raw = await websocket.receive_text()
            try:
                msg = json.loads(raw)
            except json.JSONDecodeError:
                await websocket.send_json({
                    "type": "error",
                    "payload": {"code": 1001, "message": "Invalid JSON"},
                })
                continue

            msg_type = msg.get("type")
            payload = msg.get("payload", {})

            # --- START SESSION ---
            if msg_type == "start_session":
                scene_id_raw = payload.get("scene_id")
                difficulty = payload.get("difficulty", "beginner")

                if not scene_id_raw:
                    await websocket.send_json({
                        "type": "error",
                        "payload": {"code": 1001, "message": "Missing scene_id"},
                    })
                    continue

                # Look up the scene to get role_prompt and opening_line
                scene_result = await db.execute(
                    select(Scene).where(Scene.id == int(scene_id_raw))
                )
                scene = scene_result.scalar_one_or_none()
                if scene is None:
                    await websocket.send_json({
                        "type": "error",
                        "payload": {"code": 1004, "message": "Scene not found"},
                    })
                    continue

                # Create a new session server-side
                session = Session(
                    user_id=user_id,
                    scene_id=scene.id,
                    difficulty=difficulty,
                    status="active",
                    started_at=datetime.now(timezone.utc),
                )
                db.add(session)
                await db.commit()
                await db.refresh(session)

                current_session_id = session.id
                sequence_counter = 0

                active_connections[session.id] = {
                    "websocket": websocket,
                    "user_id": user_id,
                    "interrupted_responses": set(),
                }

                opening_line = scene.opening_line or "Hello! Let's practice English. What would you like to talk about?"

                # store AI opening
                sequence_counter += 1
                ai_utt = await _store_utterance(session.id, "ai", opening_line, sequence_counter)

                await websocket.send_json({
                    "type": "session_ready",
                    "payload": {
                        "session_id": str(session.id),
                        "ai_first_message": {
                            "utterance_id": str(ai_utt.id),
                            "text": opening_line,
                        },
                    },
                })

            # --- AUDIO DATA ---
            elif msg_type == "audio_data":
                if not current_session_id:
                    await websocket.send_json({
                        "type": "error",
                        "payload": {"code": 1001, "message": "No active session"},
                    })
                    continue

                asr_text = payload.get("text", "")
                is_end = payload.get("is_end", False)

                if not is_end and asr_text:
                    # send partial ASR
                    await websocket.send_json({
                        "type": "asr_partial",
                        "payload": {
                            "session_id": str(current_session_id),
                            "text": asr_text,
                            "is_final": False,
                            "timestamp": datetime.now(timezone.utc).isoformat(),
                        },
                    })

                if is_end and asr_text:
                    # send final ASR result
                    await websocket.send_json({
                        "type": "asr_final",
                        "payload": {
                            "session_id": str(current_session_id),
                            "text": asr_text,
                            "confidence": 0.95,
                            "timestamp": datetime.now(timezone.utc).isoformat(),
                        },
                    })

                    # store user utterance
                    sequence_counter += 1
                    await _store_utterance(current_session_id, "user", asr_text, sequence_counter)

                    # pronunciation feedback (simulated)
                    await websocket.send_json({
                        "type": "pronunciation_feedback",
                        "payload": {
                            "sentence_text": asr_text,
                            "overall_score": 75,
                            "word_scores": [],
                            "brief_tip": "Good effort! Keep practicing your intonation.",
                        },
                    })

                    # grammar hint (simulated - only for obvious patterns)
                    grammar_hint = _get_grammar_hint(asr_text)
                    if grammar_hint:
                        await websocket.send_json({
                            "type": "grammar_hint",
                            "payload": grammar_hint,
                        })

                    # generate LLM response
                    data = await _get_session_data(db, current_session_id)
                    scene_data = data["scene_data"] if data else None
                    ai_text = _simulate_llm_response(asr_text, scene_data)

                    sequence_counter += 1
                    ai_utt = await _store_utterance(current_session_id, "ai", ai_text, sequence_counter)

                    resp_id = str(uuid.uuid4())
                    await websocket.send_json({
                        "type": "llm_response_text",
                        "payload": {
                            "session_id": str(current_session_id),
                            "text": ai_text,
                            "utterance_id": str(ai_utt.id),
                            "is_final": True,
                            "interrupt_id": resp_id,
                        },
                    })

                    # TTS audio stub
                    await websocket.send_json({
                        "type": "tts_audio",
                        "payload": {
                            "session_id": str(current_session_id),
                            "stream_id": f"tts_{resp_id}",
                            "interrupt_id": resp_id,
                            "is_end": True,
                            "text": ai_text,
                        },
                    })

            # --- INTERRUPT ---
            elif msg_type == "interrupt":
                interrupt_id = payload.get("interrupt_id", "")
                if current_session_id and current_session_id in active_connections:
                    active_connections[current_session_id].setdefault(
                        "interrupted_responses", set()
                    ).add(interrupt_id)
                await websocket.send_json({
                    "type": "interrupt_ack",
                    "payload": {"interrupt_id": interrupt_id},
                })

            # --- END SESSION ---
            elif msg_type == "end_session":
                if not current_session_id:
                    await websocket.send_json({
                        "type": "error",
                        "payload": {"code": 1001, "message": "No active session"},
                    })
                    continue

                # mark session completed
                now = datetime.now(timezone.utc)
                session_result = await db.execute(
                    select(Session).where(Session.id == current_session_id)
                )
                session = session_result.scalar_one_or_none()
                if session and session.status == "active":
                    session.status = "completed"
                    session.ended_at = now
                    session.duration_seconds = int(
                        (now - session.started_at).total_seconds()
                    )
                    await db.commit()

                await websocket.send_json({
                    "type": "session_ended",
                    "payload": {
                        "session_id": str(current_session_id),
                        "summary_report_id": str(current_session_id),
                    },
                })
                break

            # --- PING ---
            elif msg_type == "ping":
                await websocket.send_json({"type": "pong"})

            else:
                await websocket.send_json({
                    "type": "error",
                    "payload": {"code": 1001, "message": f"Unknown message type: {msg_type}"},
                })

    except WebSocketDisconnect:
        pass
    finally:
        if current_session_id:
            active_connections.pop(current_session_id, None)
        await db.close()


def _get_grammar_hint(text: str) -> dict | None:
    lower = text.strip().lower()
    if "i go to" in lower and "yesterday" in lower:
        return {
            "original_text": text,
            "error_span": {"start": 0, "end": len("i go to")},
            "correction": "I went to",
            "hint": "建议使用过去时 'went'",
        }
    if "he go" in lower:
        return {
            "original_text": text,
            "error_span": {"start": text.lower().find("he go"), "end": text.lower().find("he go") + 6},
            "correction": "goes",
            "hint": "主语 he 为第三人称单数，动词需用 goes",
        }
    if "i has" in lower:
        return {
            "original_text": text,
            "error_span": {"start": text.lower().find("i has"), "end": text.lower().find("i has") + 5},
            "correction": "I have",
            "hint": "第一人称应使用 'have' 而非 'has'",
        }
    return None