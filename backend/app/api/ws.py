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
        # Tense errors
        {"trigger": "i go to", "check": lambda t: "i go to" in t and "yesterday" in t, "error_type": "tense", "match": "i go to", "correction": "I went to", "explanation": "应使用过去时 'went'", "severity": "medium"},
        {"trigger": "i go", "check": lambda t: "i go" in t and "yesterday" in t, "error_type": "tense", "match": "i go", "correction": "I went", "explanation": "过去时应该用 'went'", "severity": "medium"},
        {"trigger": "yesterday i go", "check": lambda t: "yesterday" in t and "i go" in t, "error_type": "tense", "match": "i go", "correction": "I went", "explanation": "'yesterday' 表示过去，应使用 'went'", "severity": "medium"},
        # Subject-verb agreement
        {"trigger": "he go", "check": lambda t: "he go" in t and "he goes" not in t, "error_type": "subject-verb agreement", "match": "he go", "correction": "he goes", "explanation": "主语 he 为第三人称单数，动词需用 goes", "severity": "medium"},
        {"trigger": "she go", "check": lambda t: "she go" in t and "she goes" not in t, "error_type": "subject-verb agreement", "match": "she go", "correction": "she goes", "explanation": "第三人称单数动词需加 -es", "severity": "medium"},
        {"trigger": "it go", "check": lambda t: "it go" in t and "it goes" not in t, "error_type": "subject-verb agreement", "match": "it go", "correction": "it goes", "explanation": "第三人称单数动词需加 -es", "severity": "medium"},
        {"trigger": "i has", "check": lambda t: "i has" in t, "error_type": "subject-verb agreement", "match": "i has", "correction": "I have", "explanation": "第一人称应使用 'have' 而非 'has'", "severity": "low"},
        {"trigger": "they has", "check": lambda t: "they has" in t, "error_type": "subject-verb agreement", "match": "they has", "correction": "they have", "explanation": "they 后应使用 'have'", "severity": "low"},
        {"trigger": "we has", "check": lambda t: "we has" in t, "error_type": "subject-verb agreement", "match": "we has", "correction": "we have", "explanation": "we 后应使用 'have'", "severity": "low"},
        {"trigger": "you has", "check": lambda t: "you has" in t, "error_type": "subject-verb agreement", "match": "you has", "correction": "you have", "explanation": "you 后应使用 'have'", "severity": "low"},
        {"trigger": "he have", "check": lambda t: "he have" in t, "error_type": "subject-verb agreement", "match": "he have", "correction": "he has", "explanation": "第三人称单数应使用 'has'", "severity": "low"},
        {"trigger": "she have", "check": lambda t: "she have" in t, "error_type": "subject-verb agreement", "match": "she have", "correction": "she has", "explanation": "第三人称单数应使用 'has'", "severity": "low"},
        # Plural errors
        {"trigger": "two apple", "check": lambda t: "two apple" in t and "two apples" not in t, "error_type": "plural", "match": "two apple", "correction": "two apples", "explanation": "数量词后应使用复数形式", "severity": "medium"},
        {"trigger": "three book", "check": lambda t: "three book" in t and "three books" not in t, "error_type": "plural", "match": "three book", "correction": "three books", "explanation": "数量词后应使用复数形式", "severity": "medium"},
        {"trigger": "some apple", "check": lambda t: "some apple" in t and "some apples" not in t, "error_type": "plural", "match": "some apple", "correction": "some apples", "explanation": "'some' 后应用复数", "severity": "low"},
        {"trigger": "many book", "check": lambda t: "many book" in t and "many books" not in t, "error_type": "plural", "match": "many book", "correction": "many books", "explanation": "'many' 后应用复数", "severity": "low"},
        # Article errors
        {"trigger": "a apple", "check": lambda t: "a apple" in t, "error_type": "article", "match": "a apple", "correction": "an apple", "explanation": "元音前应使用 'an' 而非 'a'", "severity": "low"},
        {"trigger": "a orange", "check": lambda t: "a orange" in t, "error_type": "article", "match": "a orange", "correction": "an orange", "explanation": "元音前应使用 'an' 而非 'a'", "severity": "low"},
        {"trigger": "a egg", "check": lambda t: "a egg" in t, "error_type": "article", "match": "a egg", "correction": "an egg", "explanation": "元音前应使用 'an' 而非 'a'", "severity": "low"},
        # Preposition errors
        {"trigger": "go to home", "check": lambda t: "go to home" in t, "error_type": "preposition", "match": "go to home", "correction": "go home", "explanation": "'go home' 不需加 'to'", "severity": "low"},
        {"trigger": "go to there", "check": lambda t: "go to there" in t, "error_type": "preposition", "match": "go to there", "correction": "go there", "explanation": "'go there' 不需加 'to'", "severity": "low"},
        # Word order
        {"trigger": "i very like", "check": lambda t: "i very like" in t, "error_type": "word order", "match": "i very like", "correction": "I really like", "explanation": "中式英语，用 'really like' 替代 'very like'", "severity": "medium"},
        # Double negatives
        {"trigger": "don't have no", "check": lambda t: "don't have no" in t or "dont have no" in t, "error_type": "double negative", "match": "don't have no", "correction": "don't have any", "explanation": "双重否定，应用 'any' 替代 'no'", "severity": "medium"},
        # Missing 'to' in infinitive
        {"trigger": "i want go", "check": lambda t: "i want go" in t and "i want to go" not in t, "error_type": "infinitive", "match": "i want go", "correction": "I want to go", "explanation": "'want' 后需加 'to' + 动词原形", "severity": "medium"},
        # Common misspellings
        {"trigger": "tommorrow", "check": lambda t: "tommorrow" in t, "error_type": "spelling", "match": "tommorrow", "correction": "tomorrow", "explanation": "拼写应为 'tomorrow'", "severity": "low"},
        {"trigger": "becuase", "check": lambda t: "becuase" in t, "error_type": "spelling", "match": "becuase", "correction": "because", "explanation": "拼写应为 'because'", "severity": "low"},
        # Verb form errors (gerund vs infinitive)
        {"trigger": "enjoy to", "check": lambda t: "enjoy to" in t, "error_type": "gerund", "match": "enjoy to", "correction": "enjoy", "explanation": "'enjoy' 后接动名词 (-ing)，如 'enjoy doing'", "severity": "medium"},
        {"trigger": "finish to", "check": lambda t: "finish to" in t, "error_type": "gerund", "match": "finish to", "correction": "finish", "explanation": "'finish' 后接动名词 (-ing)，如 'finish doing'", "severity": "medium"},
        {"trigger": "practice to", "check": lambda t: "practice to" in t, "error_type": "gerund", "match": "practice to", "correction": "practice", "explanation": "'practice' 后接动名词 (-ing)，如 'practice speaking'", "severity": "medium"},
        {"trigger": "suggest to", "check": lambda t: "suggest to" in t, "error_type": "gerund", "match": "suggest to", "correction": "suggest", "explanation": "'suggest' 后接动名词 (-ing)，如 'suggest going'", "severity": "medium"},
        {"trigger": "avoid to", "check": lambda t: "avoid to" in t, "error_type": "gerund", "match": "avoid to", "correction": "avoid", "explanation": "'avoid' 后接动名词 (-ing)，如 'avoid doing'", "severity": "medium"},
        # Modal verb errors
        {"trigger": "can to", "check": lambda t: "can to" in t, "error_type": "modal verb", "match": "can to", "correction": "can", "explanation": "情态动词 'can' 后直接跟动词原形，不需 'to'", "severity": "medium"},
        {"trigger": "must to", "check": lambda t: "must to" in t, "error_type": "modal verb", "match": "must to", "correction": "must", "explanation": "情态动词 'must' 后直接跟动词原形", "severity": "medium"},
        {"trigger": "should to", "check": lambda t: "should to" in t, "error_type": "modal verb", "match": "should to", "correction": "should", "explanation": "情态动词后直接跟动词原形，不需 'to'", "severity": "medium"},
        {"trigger": "will to", "check": lambda t: "will to" in t and "willing" not in t, "error_type": "modal verb", "match": "will to", "correction": "will", "explanation": "'will' 后直接跟动词原形，不需 'to'", "severity": "medium"},
        # Comparative / Superlative errors
        {"trigger": "more better", "check": lambda t: "more better" in t, "error_type": "comparative", "match": "more better", "correction": "better", "explanation": "'better' 已经是比较级，不需加 'more'", "severity": "medium"},
        {"trigger": "more bigger", "check": lambda t: "more bigger" in t, "error_type": "comparative", "match": "more bigger", "correction": "bigger", "explanation": "单音节词加 -er 构成比较级，不需 'more'", "severity": "medium"},
        {"trigger": "more faster", "check": lambda t: "more faster" in t, "error_type": "comparative", "match": "more faster", "correction": "faster", "explanation": "'faster' 已经是比较级，不需加 'more'", "severity": "medium"},
        {"trigger": "most best", "check": lambda t: "most best" in t, "error_type": "superlative", "match": "most best", "correction": "best", "explanation": "'best' 已经是最高级，不需加 'most'", "severity": "medium"},
        # Countable / Uncountable errors
        {"trigger": "many money", "check": lambda t: "many money" in t, "error_type": "countable", "match": "many money", "correction": "much money", "explanation": "'money' 是不可数名词，应用 'much' 而非 'many'", "severity": "medium"},
        {"trigger": "many information", "check": lambda t: "many information" in t, "error_type": "countable", "match": "many information", "correction": "much information", "explanation": "'information' 是不可数名词，应用 'much'", "severity": "medium"},
        {"trigger": "many advice", "check": lambda t: "many advice" in t, "error_type": "countable", "match": "many advice", "correction": "much advice", "explanation": "'advice' 是不可数名词，应用 'much'", "severity": "medium"},
        {"trigger": "many furniture", "check": lambda t: "many furniture" in t, "error_type": "countable", "match": "many furniture", "correction": "much furniture", "explanation": "'furniture' 是不可数名词，应用 'much'", "severity": "medium"},
        {"trigger": "a furniture", "check": lambda t: "a furniture" in t, "error_type": "countable", "match": "a furniture", "correction": "a piece of furniture", "explanation": "'furniture' 是不可数名词，用 'a piece of furniture'", "severity": "low"},
        {"trigger": "a advice", "check": lambda t: "a advice" in t, "error_type": "countable", "match": "a advice", "correction": "a piece of advice", "explanation": "'advice' 是不可数名词，用 'a piece of advice'", "severity": "low"},
        # Pronoun errors
        {"trigger": "me go", "check": lambda t: "me go" in t, "error_type": "pronoun", "match": "me go", "correction": "I go", "explanation": "主语位置应使用主格 'I' 而非宾格 'me'", "severity": "medium"},
        {"trigger": "him go", "check": lambda t: "him go" in t, "error_type": "pronoun", "match": "him go", "correction": "he goes", "explanation": "主语位置应使用主格 'he' 而非宾格 'him'", "severity": "medium"},
        {"trigger": "her go", "check": lambda t: "her go" in t, "error_type": "pronoun", "match": "her go", "correction": "she goes", "explanation": "主语位置应使用主格 'she' 而非宾格 'her'", "severity": "medium"},
        {"trigger": "them go", "check": lambda t: "them go" in t, "error_type": "pronoun", "match": "them go", "correction": "they go", "explanation": "主语位置应使用主格 'they' 而非宾格 'them'", "severity": "medium"},
        # Adjective / Adverb confusion
        {"trigger": "drive careful", "check": lambda t: "drive careful" in t, "error_type": "adjective/adverb", "match": "drive careful", "correction": "drive carefully", "explanation": "修饰动词应用副词 'carefully' 而非形容词 'careful'", "severity": "medium"},
        {"trigger": "speak slow", "check": lambda t: "speak slow" in t, "error_type": "adjective/adverb", "match": "speak slow", "correction": "speak slowly", "explanation": "修饰动词应用副词 'slowly' 而非形容词 'slow'", "severity": "low"},
        {"trigger": "write good", "check": lambda t: "write good" in t, "error_type": "adjective/adverb", "match": "write good", "correction": "write well", "explanation": "修饰动词应用副词 'well' 而非形容词 'good'", "severity": "medium"},
        # Preposition errors (more)
        {"trigger": "arrive to", "check": lambda t: "arrive to" in t, "error_type": "preposition", "match": "arrive to", "correction": "arrive at/in", "explanation": "'arrive' 后接 'at'(小地方)或 'in'(大地方)，不用 'to'", "severity": "medium"},
        {"trigger": "discuss about", "check": lambda t: "discuss about" in t, "error_type": "preposition", "match": "discuss about", "correction": "discuss", "explanation": "'discuss' 直接接宾语，不需 'about'", "severity": "medium"},
        {"trigger": "enter into", "check": lambda t: "enter into" in t, "error_type": "preposition", "match": "enter into", "correction": "enter", "explanation": "'enter' 直接接地点，不需 'into'", "severity": "low"},
        {"trigger": "married with", "check": lambda t: "married with" in t, "error_type": "preposition", "match": "married with", "correction": "married to", "explanation": "'和某人结婚' 用 'married to' 而非 'married with'", "severity": "medium"},
        {"trigger": "look forward to", "check": lambda t: "look forward to" in t, "error_type": "gerund", "match": "look forward to", "correction": "look forward to", "explanation": "'look forward to' 中的 'to' 是介词，后接 -ing 形式", "severity": "low"},
        # More Chinese-English specific errors
        {"trigger": "according to me", "check": lambda t: "according to me" in t, "error_type": "expression", "match": "according to me", "correction": "in my opinion", "explanation": "用 'in my opinion' 比 'according to me' 更地道", "severity": "low"},
        {"trigger": "in my idea", "check": lambda t: "in my idea" in t, "error_type": "expression", "match": "in my idea", "correction": "in my opinion", "explanation": "应使用 'in my opinion' 表达观点", "severity": "low"},
        {"trigger": "according to my opinion", "check": lambda t: "according to my opinion" in t, "error_type": "expression", "match": "according to my opinion", "correction": "in my opinion", "explanation": "直接用 'in my opinion' 即可", "severity": "low"},
        {"trigger": "it's depend", "check": lambda t: "it's depend" in t or "it is depend" in t, "error_type": "verb form", "match": "depend", "correction": "it depends", "explanation": "主语 'it' 为第三人称单数，动词需加 -s", "severity": "medium"},
        {"trigger": "how to say", "check": lambda t: "how to say" in t, "error_type": "expression", "match": "how to say", "correction": "how do you say", "explanation": "询问表达方式应用 'how do you say...?'", "severity": "low"},
        {"trigger": "how to spell", "check": lambda t: "how to spell" in t, "error_type": "expression", "match": "how to spell", "correction": "how do you spell", "explanation": "询问拼写应用 'how do you spell...?'", "severity": "low"},
        {"trigger": "i am agree", "check": lambda t: "i am agree" in t, "error_type": "expression", "match": "i am agree", "correction": "I agree", "explanation": "'agree' 是动词，直接说 'I agree'，不需 'am'", "severity": "medium"},
        {"trigger": "i am not agree", "check": lambda t: "i am not agree" in t, "error_type": "expression", "match": "i am not agree", "correction": "I don't agree", "explanation": "'agree' 的否定形式用 'don't agree'", "severity": "medium"},
        {"trigger": "i very much like", "check": lambda t: "i very much like" in t, "error_type": "word order", "match": "i very much like", "correction": "I like ... very much", "explanation": "英语中 'very much' 通常放在句末", "severity": "low"},
        {"trigger": "for a long time", "check": lambda t: "i have not see you for a long time" in t, "error_type": "tense", "match": "have not see", "correction": "haven't seen", "explanation": "现在完成时应用过去分词 'seen'", "severity": "medium"},
        # Confusing word pairs
        {"trigger": "there is many", "check": lambda t: "there is many" in t, "error_type": "agreement", "match": "there is many", "correction": "there are many", "explanation": "'many' + 复数名词应用 'there are'", "severity": "medium"},
        {"trigger": "there is some", "check": lambda t: "there is some" in t and "there is some people" not in t and "there is some water" not in t, "error_type": "agreement", "match": "there is some", "correction": "there are some", "explanation": "可数名词复数前用 'there are'", "severity": "low"},
        {"trigger": "its a", "check": lambda t: "its a" in t, "error_type": "spelling", "match": "its a", "correction": "it's a", "explanation": "缩写 'it is' → 'it's'，'its' 表示所有格", "severity": "medium"},
        {"trigger": "there seats", "check": lambda t: "there seats" in t, "error_type": "spelling", "match": "there seats", "correction": "their seats", "explanation": "表示所有格应用 'their' 而非 'there'", "severity": "medium"},
        {"trigger": "your welcome", "check": lambda t: "your welcome" in t, "error_type": "spelling", "match": "your welcome", "correction": "you're welcome", "explanation": "应为 'you're' (you are) 而非 'your' (你的)", "severity": "medium"},
        {"trigger": "there going", "check": lambda t: "there going" in t, "error_type": "spelling", "match": "there going", "correction": "they're going", "explanation": "应为 'they're' (they are) 而非 'there' (那里)", "severity": "medium"},
        # Missing 'be' verb
        {"trigger": "i hungry", "check": lambda t: "i hungry" in t and "i am hungry" not in t, "error_type": "missing be", "match": "i hungry", "correction": "I am hungry", "explanation": "形容词前需要 be 动词：'I am hungry'", "severity": "medium"},
        {"trigger": "i tired", "check": lambda t: "i tired" in t and "i am tired" not in t, "error_type": "missing be", "match": "i tired", "correction": "I am tired", "explanation": "形容词前需要 be 动词：'I am tired'", "severity": "medium"},
        {"trigger": "he happy", "check": lambda t: "he happy" in t and "he is happy" not in t, "error_type": "missing be", "match": "he happy", "correction": "he is happy", "explanation": "形容词前需要 be 动词：'he is happy'", "severity": "medium"},
    ]

    # Helper: check word boundary
    def _word_match(text: str, phrase: str) -> bool:
        idx = text.find(phrase)
        if idx < 0:
            return False
        # Check character before match (if any) is not a letter
        if idx > 0 and text[idx - 1].isalpha():
            return False
        # Check character after match (if any) is not a letter
        end = idx + len(phrase)
        if end < len(text) and text[end].isalpha():
            return False
        return True

    for p in patterns:
        if p["check"](lower):
            idx = lower.find(p["match"])
            if not _word_match(lower, p["match"]):
                continue
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


def _simulate_asr_from_audio() -> str:
    """Simulate ASR recognition from voice input.
    Returns a random plausible English practice phrase since no real ASR is integrated."""
    phrases = [
        "hello",
        "hi there",
        "I'd like to order a coffee please",
        "can I have the menu",
        "thank you very much",
        "how are you today",
        "I'm doing well thanks",
        "could you help me please",
        "what do you recommend",
        "that sounds great",
        "I have a question",
        "nice to meet you",
    ]
    import random as _rand
    return _rand.choice(phrases)


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


SCENE_KEYWORDS = {
    "coffee shop": {"coffee", "tea", "latte", "espresso", "cappuccino", "drink", "cup", "order", "size", "milk", "sugar", "menu", "takeaway", "hot", "cold", "cream", "sweet", "barista", "cafe"},
    "restaurant": {"food", "menu", "order", "steak", "chicken", "fish", "salad", "appetizer", "dessert", "wine", "drink", "reservation", "table", "bill", "check", "waiter", "meal", "dinner", "lunch", "course", "chef", "delicious", "taste", "cook", "restaurant"},
    "clothing store": {"size", "fit", "color", "wear", "clothes", "shirt", "pants", "dress", "price", "sale", "return", "exchange", "shop", "buy", "try", "fashion", "style", "shoes", "jacket", "store"},
    "airport": {"flight", "boarding", "luggage", "baggage", "passport", "ticket", "seat", "gate", "check-in", "departure", "arrival", "airport", "fly", "plane", "travel", "carry-on", "delay", "airline"},
    "hotel": {"room", "reservation", "check-in", "checkout", "night", "stay", "bed", "service", "amenities", "key", "floor", "hotel", "lobby", "breakfast", "wifi", "pool", "gym", "reception", "suite"},
    "street": {"where", "street", "turn", "left", "right", "straight", "block", "landmark", "direction", "find", "lost", "way", "map", "near", "far", "distance", "walk", "drive", "corner", "traffic"},
    "job interview": {"experience", "skill", "job", "work", "strength", "weakness", "career", "company", "team", "project", "resume", "interview", "position", "role", "salary", "hire", "manager", "goal", "qualification", "background"},
    "business meeting": {"project", "deadline", "meeting", "report", "team", "plan", "update", "task", "timeline", "budget", "agenda", "milestone", "stakeholder", "presentation", "discuss", "proposal", "review", "objective", "schedule", "action"},
}


def _check_scene_drift(text: str, scene_name: str) -> str | None:
    """Check if user input drifts off-topic for the scene. Returns reminder or None."""
    keywords = SCENE_KEYWORDS.get(scene_name, set())
    if not keywords:
        return None

    words = set(text.lower().split())
    # Also check longer phrases
    text_lower = text.lower()
    match_count = sum(1 for kw in keywords if kw in text_lower)

    if match_count == 0:
        # Only warn for substantive messages (5+ words)
        if len(words) >= 5:
            reminders = {
                "coffee shop": "Let's stay focused on ordering at the café. What drink would you like?",
                "restaurant": "Let's keep our conversation about dining. What would you like to order?",
                "clothing store": "Let's get back to shopping. What are you looking for today?",
                "airport": "Let's focus on your flight. Do you have your travel documents ready?",
                "hotel": "Let's talk about your hotel stay. How can I assist with your reservation?",
                "street": "Let's get back to finding your way. Where are you trying to go?",
                "job interview": "Let's return to the interview. Can you tell me about your work experience?",
                "business meeting": "Let's get back to our meeting agenda. Any updates on your tasks?",
            }
            return reminders.get(scene_name, "Let's stay focused on our conversation topic. Can we get back to it?")
    return None


def _simulate_llm_response(
    text: str,
    scene_data: dict | None,
) -> str:
    """Generate a contextual AI response based on user input and scene context."""
    lower = text.strip().lower().rstrip(".!?")

    # Extract key words from user input for contextual response
    words = set(lower.split())
    keywords = [w for w in words if len(w) > 2]

    # Determine the scene role
    role = "a conversation partner"
    scene_name = ""
    if scene_data:
        role_prompt = scene_data.get("role_prompt", "")
        if "barista" in role_prompt:
            role = "the barista"
            scene_name = "coffee shop"
        elif "waiter" in role_prompt:
            role = "the waiter"
            scene_name = "restaurant"
        elif "sales assistant" in role_prompt:
            role = "the sales assistant"
            scene_name = "clothing store"
        elif "check-in agent" in role_prompt:
            role = "the check-in agent"
            scene_name = "airport"
        elif "receptionist" in role_prompt:
            role = "the receptionist"
            scene_name = "hotel"
        elif "local" in role_prompt:
            role = "a friendly local"
            scene_name = "street"
        elif "HR manager" in role_prompt or "interview" in role_prompt:
            role = "the HR manager"
            scene_name = "job interview"
        elif "team lead" in role_prompt or "meeting" in role_prompt:
            role = "the team lead"
            scene_name = "business meeting"

    # --- Greetings ---
    if lower in ("hello", "hi", "hey", "hi there", "good morning", "good afternoon", "good evening"):
        return f"Hello! I'm {role}. How are you doing today?"

    if lower in ("i'm fine", "i am fine", "fine thanks", "i'm good", "i am good", "doing well", "i'm doing well"):
        return f"Glad to hear that! So, what brings you here today? {_scene_prompt(scene_data)}"

    if lower in ("thank you", "thanks", "thank you very much", "thanks a lot"):
        return "You're very welcome! Is there anything else I can help you with?"

    if lower in ("bye", "goodbye", "see you", "see you later"):
        return "Goodbye! It was great talking with you. Keep practicing your English!"

    # --- Scene-specific contextual responses ---
    if "how are you" in lower:
        return f"I'm doing great, thanks for asking! Now, {_scene_prompt(scene_data)}"

    # Questions about self
    if any(w in words for w in ("name", "who", "your")):
        return f"I'm {role}, here to help you practice English in this {scene_name}. But let's focus on you — tell me about yourself!"

    # Scene drift check — run BEFORE topic keywords so off-topic gets caught
    if scene_name:
        drift_msg = _check_scene_drift(text, scene_name)
        if drift_msg:
            return drift_msg

    # Order/food related
    if any(w in words for w in ("want", "would like", "i'd like", "order", "have", "get", "buy")):
        item = _extract_keyword_after(text, ["want", "would like", "order", "have", "get", "buy", "i'd like"])
        if item:
            return f"Great choice! One {item} coming right up. Can I get you anything else?"
        return f"Sure! What exactly would you like? Tell me more about what you're looking for."

    # Food/drink specific
    if any(w in words for w in ("coffee", "tea", "latte", "espresso", "cappuccino", "drink", "water", "juice", "menu")):
        drink = next((w for w in ("coffee", "tea", "latte", "espresso", "cappuccino") if w in words), "that")
        size_q = "What size would you like — small, medium, or large?" if drink else ""
        return f"Ah, {drink}! Excellent choice. {size_q}"

    if any(w in words for w in ("food", "eat", "hungry", "meal", "lunch", "dinner", "breakfast", "appetizer", "steak", "chicken", "fish", "salad")):
        food = next((w for w in ("steak", "chicken", "fish", "salad", "meal") if w in words), "that dish")
        return f"{food.capitalize()} sounds perfect! How would you like it prepared?"

    # Shopping related
    if any(w in words for w in ("size", "medium", "large", "small", "fit", "try", "wear", "color", "price", "sale", "cheap", "expensive")):
        return f"Let me help you find the right size. What size do you normally wear?"

    # Travel/airport
    if any(w in words for w in ("flight", "fly", "airport", "boarding", "luggage", "baggage", "passport", "ticket", "seat")):
        return f"I'll help you with that. May I see your booking confirmation? Do you have any luggage to check in?"

    # Hotel
    if any(w in words for w in ("room", "hotel", "stay", "night", "reservation", "book", "check-in", "checkout")):
        return f"Let me check your reservation. How many nights will you be staying with us?"

    # Directions
    if any(w in words for w in ("where", "direction", "how do i get", "find", "lost", "way", "street", "road", "turn", "left", "right", "straight")):
        return f"Ah, let me help you find your way. Do you see that big building over there? Go straight for two blocks and turn left at the traffic light."

    # Interview
    if any(w in words for w in ("experience", "skill", "job", "work", "company", "resume", "cv", "strength", "weakness", "career", "salary")):
        return f"That's interesting! Tell me more about your experience. What would you say is your greatest strength?"

    # Meeting
    if any(w in words for w in ("project", "deadline", "meeting", "report", "team", "plan", "update", "task", "timeline", "budget")):
        return f"Good point. Could you elaborate on that? I'd like to hear more details about the timeline."

    # Recommendations / suggestions
    if any(w in words for w in ("recommend", "suggest", "suggestion", "popular", "best", "special")):
        return f"I'd recommend our house special. It's very popular! Would you like to try that?"

    # Opinions / I think / I believe
    if any(phrase in lower for phrase in ("i think", "i believe", "in my opinion", "i feel", "i guess")):
        return f"Interesting perspective! Why do you feel that way? Tell me more."

    # Likes / preferences
    if any(w in words for w in ("like", "love", "enjoy", "prefer", "favorite", "hate", "dislike")):
        return f"Oh really? That's fascinating! What do you like most about it?"

    # Weather
    if any(w in words for w in ("weather", "rain", "sunny", "hot", "cold", "warm", "cloudy", "snow")):
        return f"Yes, the weather has been quite interesting lately! How does it affect your plans?"

    # Time / schedule
    if any(w in words for w in ("time", "today", "tomorrow", "week", "month", "schedule", "plan", "busy", "free")):
        return f"I see. What time works best for you? Let's plan around your schedule."

    # Background / about self
    if any(w in words for w in ("student", "teacher", "engineer", "doctor", "work", "study", "learn", "school", "university", "college")):
        return f"That's great! Tell me more about what you do. What's the most challenging part?"

    # Hobbies / free time
    if any(w in words for w in ("hobby", "hobbies", "free time", "weekend", "fun", "sport", "music", "movie", "book", "read", "game", "play")):
        return f"Sounds like fun! How often do you do that?"

    # Yes/No short answers
    if lower in ("yes", "yeah", "yep", "sure", "ok", "okay"):
        return f"Great! {_scene_prompt(scene_data)}"

    if lower in ("no", "nope", "not really"):
        return f"I understand. Is there something else you'd prefer instead?"

    # Generic: reference the user's topic
    if keywords:
        topic = keywords[0] if len(keywords[0]) > 3 else (keywords[1] if len(keywords) > 1 else keywords[0])
        return f"That's interesting what you said about '{topic}'. Can you tell me more about that?"

    # Fallback with scene context
    return f"I see! Tell me more. {_scene_prompt(scene_data)}"


def _scene_prompt(scene_data: dict | None) -> str:
    """Get a contextual prompt based on the scene."""
    if not scene_data:
        return "What would you like to talk about?"
    opening = scene_data.get("opening_line", "")
    if opening:
        return opening
    return "What would you like to talk about?"


def _extract_keyword_after(text: str, triggers: list[str]) -> str | None:
    """Extract the word(s) after a trigger phrase."""
    lower = text.lower()
    for trigger in triggers:
        idx = lower.find(trigger)
        if idx >= 0:
            after = text[idx + len(trigger):].strip()
            # Take up to 20 chars after the trigger
            return after[:30].strip(".,!?;: ")
    return None


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
                        started_at=datetime.utcnow(),
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

                # Negotiate config from client request
                client_config = payload.get("config", {})
                negotiated = {
                    "audio_format": client_config.get("audio_format", "pcm_s16le"),
                    "tts_voice": client_config.get("tts_voice", "en-US-female"),
                }

                active_connections[session.id] = {
                    "websocket": websocket,
                    "user_id": user_id,
                    "interrupted_responses": set(),
                    "tts_voice": negotiated["tts_voice"],
                }

                # Resolve the session's scene to get the opening line
                session_scene = None
                if session.scene_id:
                    scene_result = await db.execute(
                        select(Scene).where(Scene.id == session.scene_id)
                    )
                    session_scene = scene_result.scalar_one_or_none()

                # Check for custom scene data from client
                custom_scene = payload.get("custom_scene")
                if custom_scene and isinstance(custom_scene, dict):
                    opening_line = custom_scene.get("opening_line") or (
                        session_scene.opening_line if session_scene
                        else "Hello! Let's practice English. What would you like to talk about?"
                    )
                else:
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
                    "type": "session_ready",
                    "payload": {
                        "session_id": str(session.id),
                        "ai_first_message": {
                            "utterance_id": str(ai_utt.id) if ai_utt else "",
                            "text": opening_line,
                        },
                        "negotiated_config": {
                            "audio_format": negotiated["audio_format"],
                            "tts_voice": negotiated["tts_voice"],
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
                audio_base64 = payload.get("audio_base64", "")

                if not is_end and asr_text:
                    # send partial ASR
                    await websocket.send_json({
                        "type": "asr_partial",
                        "payload": {
                            "session_id": str(current_session_id),
                            "text": asr_text,
                            "is_final": False,
                            "timestamp": datetime.utcnow().isoformat(),
                        },
                    })

                if is_end:
                    # If audio was provided but no ASR text, simulate recognition
                    if not asr_text and audio_base64:
                        asr_text = _simulate_asr_from_audio()
                    if asr_text:
                        try:
                            await _process_user_message(
                                websocket, db, current_session_id, asr_text, sequence_counter
                            )
                            sequence_counter += 2
                        except Exception as e:
                            import traceback
                            traceback.print_exc()
                            await websocket.send_json({
                                "type": "error",
                                "payload": {"code": 2001, "message": f"Internal error: {e}"},
                            })

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
                    try:
                        await _process_user_message(
                            websocket, db, current_session_id, text, sequence_counter
                        )
                        sequence_counter += 2
                    except Exception as e:
                        import traceback
                        traceback.print_exc()
                        await websocket.send_json({
                            "type": "error",
                            "payload": {"code": 2001, "message": f"Internal error: {e}"},
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
                now = datetime.utcnow()
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
            "timestamp": datetime.utcnow().isoformat(),
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

    # send pronunciation feedback with V1.1 enhanced data
    detail_level = "full"  # default; could be configured per session
    fb_payload = {
        "session_id": str(current_session_id),
        "utterance_id": str(user_utt.id),
        "sentence_text": asr_text,
        "overall_score": evaluation.overall_score,
        "pronunciation_score": evaluation.pronunciation_score,
        "fluency_score": evaluation.fluency_score,
        "completeness_score": evaluation.completeness_score,
        "brief_tip": evaluation.advice or "Keep practicing!",
    }

    if detail_level == "full" and word_scores:
        # Include phoneme-level detail
        fb_payload["word_scores"] = word_scores
        # Add reference audio URL for the most problematic word
        worst_word = min(word_scores, key=lambda w: w["score"]) if word_scores else None
        if worst_word and worst_word["score"] < 60:
            fb_payload["reference_audio_url"] = (
                f"https://dict.youdao.com/dictvoice?audio={worst_word['word']}&type=0"
            )

    await websocket.send_json({
        "type": "pronunciation_feedback",
        "payload": fb_payload,
    })

    # persist and send grammar hints with V1.1 enhanced fields
    grammar_errors = await _store_grammar_errors(db, user_utt, asr_text)
    for ge in grammar_errors:
        await websocket.send_json({
            "type": "grammar_hint",
            "payload": {
                "session_id": str(current_session_id),
                "utterance_id": str(user_utt.id),
                "original_text": ge.original_text,
                "error_span": {"start": ge.error_span_start, "end": ge.error_span_end},
                "correction": ge.correction,
                "corrected_sentence": ge.corrected_sentence,
                "hint": ge.explanation or "",
                "severity": ge.severity or "medium",
                "hint_type": "expression" if ge.is_expression_issue else "grammar",
            },
        })

    # generate LLM response — try Groq first, fall back to simulated
    data = await _get_session_data(db, current_session_id)
    scene_data = data["scene_data"] if data else None
    session_obj = data["session"] if data else None

    # Build conversation history for LLM
    history = []
    if session_obj:
        utt_result = await db.execute(
            select(Utterance)
            .where(Utterance.session_id == current_session_id)
            .order_by(Utterance.sequence)
        )
        for u in utt_result.scalars().all():
            role = "assistant" if u.speaker == "ai" else "user"
            history.append({"role": role, "content": u.text})

    # Try Groq LLM
    system_prompt = scene_data.get("role_prompt", "") if scene_data else ""
    from ..services.llm_service import generate_response
    ai_text = await generate_response(asr_text, system_prompt, history)

    # Fall back to simulated response if Groq unavailable
    if not ai_text:
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

    # TTS audio — generate real audio via Edge-TTS
    from ..services.tts_service import text_to_speech_base64, VOICES as TTS_VOICES
    # Use negotiated voice from session config; default to female if not set
    tts_voice_key = "en-US-female"
    if current_session_id and current_session_id in active_connections:
        tts_voice_key = active_connections[current_session_id].get("tts_voice", "en-US-female")
    print(f"[TTS] Voice key: {tts_voice_key} -> Edge-TTS: {TTS_VOICES.get(tts_voice_key, 'en-US-JennyNeural')}")
    tts_base64 = await text_to_speech_base64(ai_text, voice=tts_voice_key)
    if tts_base64:
        await websocket.send_json({
            "type": "tts_audio",
            "payload": {
                "session_id": str(current_session_id),
                "stream_id": f"tts_{resp_id}",
                "interrupt_id": resp_id,
                "is_end": True,
                "text": ai_text,
                "audio_base64": tts_base64,
                "audio_mime": "audio/mp3",
            },
        })
    else:
        # Fallback: stub without audio
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
