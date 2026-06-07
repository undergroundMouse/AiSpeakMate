import json
import random
import uuid
from datetime import datetime, timezone

from fastapi import APIRouter, WebSocket, WebSocketDisconnect
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from ..core.database import get_db
from ..core.security import decode_access_token
from ..models.evaluation import (
    GrammarError,
    PhonemeScore,
    PronunciationEvaluation,
)
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


async def _store_pronunciation_evaluation(
    db: AsyncSession,
    utterance: Utterance,
    text: str,
) -> PronunciationEvaluation:
    """Generate and persist a simulated pronunciation evaluation for a user utterance."""
    words = text.split()
    overall = random.randint(55, 95)
    pronunciation_score = random.randint(50, 100)
    fluency_score = random.randint(50, 100)
    completeness_score = random.randint(80, 100)
    prosody_score = random.randint(50, 100)

    evaluation = PronunciationEvaluation(
        utterance_id=utterance.id,
        overall_score=overall,
        pronunciation_score=pronunciation_score,
        fluency_score=fluency_score,
        completeness_score=completeness_score,
        prosody_score=prosody_score,
        advice=_generate_pronunciation_advice(overall),
    )
    db.add(evaluation)
    await db.flush()

    # Generate per-word phoneme scores
    for word in words[:10]:  # limit to first 10 words
        clean_word = word.strip(".,!?;:\"'")
        if not clean_word:
            continue
        word_score = random.randint(50, 100)
        # Simulate 1-4 phonemes per word
        phoneme_count = min(len(clean_word), 4)
        for i, ch in enumerate(clean_word[:phoneme_count]):
            ps = random.randint(40, 100)
            is_err = ps < 60
            db.add(PhonemeScore(
                evaluation_id=evaluation.id,
                word=clean_word,
                word_score=word_score,
                phoneme=f"/{ch}/",
                phoneme_score=ps,
                is_error=is_err,
                suggested_phoneme=f"/{ch}/" if is_err else None,
                start_time_ms=i * 200,
                end_time_ms=(i + 1) * 200,
            ))

    await db.commit()
    await db.refresh(evaluation)
    return evaluation


async def _store_grammar_errors(
    db: AsyncSession,
    utterance: Utterance,
    text: str,
) -> list[GrammarError]:
    """Detect and persist grammar errors for a user utterance."""
    errors: list[GrammarError] = []
    lower = text.strip().lower()

    patterns = [
        {
            "trigger": "i go to",
            "check": lambda t: "i go to" in t and "yesterday" in t,
            "error_type": "tense",
            "match": "i go to",
            "correction": "I went to",
            "explanation": "应使用过去时 'went'",
            "severity": "medium",
        },
        {
            "trigger": "he go",
            "check": lambda t: "he go" in t and "he goes" not in t,
            "error_type": "subject-verb agreement",
            "match": "he go",
            "correction": "he goes",
            "explanation": "主语 he 为第三人称单数，动词需用 goes",
            "severity": "medium",
        },
        {
            "trigger": "i has",
            "check": lambda t: "i has" in t,
            "error_type": "subject-verb agreement",
            "match": "i has",
            "correction": "I have",
            "explanation": "第一人称应使用 'have' 而非 'has'",
            "severity": "low",
        },
        {
            "trigger": "two apple",
            "check": lambda t: "two apple" in t,
            "error_type": "plural",
            "match": "two apple",
            "correction": "two apples",
            "explanation": "'two' 后应使用复数形式 'apples'",
            "severity": "medium",
        },
    ]

    for p in patterns:
        if p["check"](lower):
            idx = lower.find(p["match"])
            if idx >= 0:
                match_len = len(p["match"])
                corrected_sentence = text[:idx] + p["correction"] + text[idx + match_len:]
                error = GrammarError(
                    utterance_id=utterance.id,
                    error_type=p["error_type"],
                    error_span_start=idx,
                    error_span_end=idx + match_len,
                    original_text=text[idx:idx + match_len],
                    correction=p["correction"],
                    corrected_sentence=corrected_sentence,
                    explanation=p["explanation"],
                    severity=p["severity"],
                    is_expression_issue=False,
                )
                db.add(error)
                errors.append(error)

    if errors:
        await db.commit()

    return errors


def _generate_pronunciation_advice(score: int) -> str:
    if score >= 85:
        return "发音非常好！继续保持。"
    elif score >= 70:
        return "发音不错，注意个别元音的发声位置。"
    elif score >= 55:
        return "重点练习元音发音，注意单词的重音位置。"
    else:
        return "建议多听原声并跟读，从基础音素开始练习。"


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
                client_session_id = payload.get("session_id")

                # If the client already created a session via HTTP, reuse it
                if client_session_id:
                    try:
                        existing_session_id = uuid.UUID(client_session_id)
                        session_result = await db.execute(
                            select(Session).where(
                                Session.id == existing_session_id,
                                Session.user_id == user_id,
                                Session.status == "active",
                            )
                        )
                        session = session_result.scalar_one_or_none()
                    except (ValueError, TypeError):
                        session = None
                else:
                    session = None

                # If no existing session or scene_id provided, look up the scene
                if session is None and scene_id_raw:
                    try:
                        scene_result = await db.execute(
                            select(Scene).where(Scene.id == int(scene_id_raw))
                        )
                        scene = scene_result.scalar_one_or_none()
                    except (ValueError, TypeError):
                        await websocket.send_json({
                            "type": "error",
                            "payload": {"code": 1001, "message": "Invalid scene_id"},
                        })
                        continue

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

                if session is None:
                    await websocket.send_json({
                        "type": "error",
                        "payload": {"code": 1001, "message": "Missing scene_id and no valid session_id"},
                    })
                    continue

                current_session_id = session.id
                sequence_counter = 0

                active_connections[session.id] = {
                    "websocket": websocket,
                    "user_id": user_id,
                    "interrupted_responses": set(),
                }

                # Resolve the session's scene to get the opening line
                session_scene = None
                if session.scene_id:
                    scene_result = await db.execute(
                        select(Scene).where(Scene.id == session.scene_id)
                    )
                    session_scene = scene_result.scalar_one_or_none()

                opening_line = (
                    session_scene.opening_line if session_scene
                    else "Hello! Let's practice English. What would you like to talk about?"
                )

                # Count existing utterances so sequence starts correctly
                existing_seq_result = await db.execute(
                    select(Utterance).where(Utterance.session_id == session.id)
                )
                existing_utt_count = len(existing_seq_result.scalars().all())

                # Only store AI opening line if this is a fresh session (no utterances yet)
                ai_utt = None
                if existing_utt_count == 0:
                    sequence_counter = 1
                    ai_utt = await _store_utterance(session.id, "ai", opening_line, sequence_counter)
                else:
                    sequence_counter = existing_utt_count
                    # Retrieve the first AI utterance if available
                    first_ai = await db.execute(
                        select(Utterance)
                        .where(Utterance.session_id == session.id, Utterance.speaker == "ai")
                        .order_by(Utterance.sequence)
                        .limit(1)
                    )
                    ai_utt = first_ai.scalar_one_or_none()
                    if ai_utt is None:
                        # Fallback: create an opening
                        sequence_counter += 1
                        ai_utt = await _store_utterance(session.id, "ai", opening_line, sequence_counter)

                await websocket.send_json({
                    "type": "session_started",
                    "payload": {
                        "session_id": str(session.id),
                        "ai_first_message": {
                            "utterance_id": str(ai_utt.id) if ai_utt else "",
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
                    await _process_user_message(
                        websocket, db, current_session_id, asr_text, sequence_counter
                    )
                    sequence_counter += 2

            # --- USER MESSAGE (text-only, no audio) ---
            elif msg_type == "user_message":
                if not current_session_id:
                    await websocket.send_json({
                        "type": "error",
                        "payload": {"code": 1001, "message": "No active session"},
                    })
                    continue

                text = (payload.get("text") or "").strip()
                if text:
                    await _process_user_message(
                        websocket, db, current_session_id, text, sequence_counter
                    )
                    sequence_counter += 2

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

                    # Generate progress snapshot and weakness records
                    from ..services.progress_service import (
                        generate_progress_snapshot,
                        update_weakness_records,
                    )
                    await generate_progress_snapshot(db, current_session_id)
                    await update_weakness_records(db, current_session_id)

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


async def _process_user_message(
    websocket: WebSocket,
    db: AsyncSession,
    current_session_id: uuid.UUID,
    asr_text: str,
    sequence_counter: int,
):
    """Process a final user utterance: store, evaluate, and generate AI response."""
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
    user_utt = await _store_utterance(current_session_id, "user", asr_text, sequence_counter + 1)

    # persist pronunciation evaluation
    evaluation = await _store_pronunciation_evaluation(db, user_utt, asr_text)

    # build word scores for the feedback message
    word_scores = []
    if evaluation.id:
        from sqlalchemy import select as _sel
        ps_result = await db.execute(
            _sel(PhonemeScore).where(PhonemeScore.evaluation_id == evaluation.id)
        )
        phoneme_scores = ps_result.scalars().all()
        # group phoneme scores by word
        word_map: dict[str, list[PhonemeScore]] = {}
        for ps in phoneme_scores:
            word_map.setdefault(ps.word, []).append(ps)
        for w, plist in word_map.items():
            word_scores.append({
                "word": w,
                "score": sum(p.phoneme_score for p in plist) // len(plist),
                "error_phonemes": [
                    p.suggested_phoneme for p in plist if p.is_error
                ],
            })

    # send pronunciation feedback with real data
    await websocket.send_json({
        "type": "pronunciation_feedback",
        "payload": {
            "sentence_text": asr_text,
            "overall_score": evaluation.overall_score,
            "word_scores": word_scores,
            "brief_tip": evaluation.advice or "Keep practicing!",
        },
    })

    # persist and send grammar hints
    grammar_errors = await _store_grammar_errors(db, user_utt, asr_text)
    for ge in grammar_errors:
        await websocket.send_json({
            "type": "grammar_hint",
            "payload": {
                "original_text": ge.original_text,
                "error_span": {"start": ge.error_span_start, "end": ge.error_span_end},
                "correction": ge.correction,
                "hint": ge.explanation or "",
            },
        })

    # generate LLM response
    data = await _get_session_data(db, current_session_id)
    scene_data = data["scene_data"] if data else None
    ai_text = _simulate_llm_response(asr_text, scene_data)

    ai_utt = await _store_utterance(current_session_id, "ai", ai_text, sequence_counter + 2)

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
