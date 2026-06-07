import json
import uuid
from datetime import datetime, timezone

from fastapi import APIRouter, WebSocket, WebSocketDisconnect
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from ..core.config import settings
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
    """Generate and persist a text-analysis-based pronunciation evaluation.

    Scores are computed from the actual user text — analyzing word complexity,
    difficult phonemes for Chinese speakers, sentence structure, and completeness.
    No random values are used.
    """
    analysis = _analyze_text(text)

    evaluation = PronunciationEvaluation(
        utterance_id=utterance.id,
        overall_score=analysis["overall"],
        pronunciation_score=analysis["pronunciation_score"],
        fluency_score=analysis["fluency_score"],
        completeness_score=analysis["completeness_score"],
        prosody_score=analysis["prosody_score"],
        advice=analysis["advice"],
    )
    db.add(evaluation)
    await db.flush()

    # Generate per-word phoneme scores based on actual text analysis
    words = [w.strip(".,!?;:\"'()") for w in text.split()]
    words = [w for w in words[:10] if w]  # limit to first 10 real words

    for word in words:
        phonemes = _get_word_phonemes(word)
        word_score = _score_word_pronunciation(word)
        for i, (ph, is_diff) in enumerate(phonemes):
            ph_score = max(40, min(100, word_score - (15 if is_diff else 0)))
            db.add(PhonemeScore(
                evaluation_id=evaluation.id,
                word=word,
                word_score=word_score,
                phoneme=ph,
                phoneme_score=ph_score,
                is_error=is_diff,
                suggested_phoneme=f"{ph} (注意发音)" if is_diff else None,
                start_time_ms=i * 200,
                end_time_ms=(i + 1) * 200,
            ))

    await db.commit()
    await db.refresh(evaluation)
    return evaluation


# ── Text analysis helpers ────────────────────────────────────────────

# Phonemes that are challenging for Chinese English learners
_DIFFICULT_PATTERNS: list[tuple[str, str]] = [
    ("th", "/θ/"), ("th", "/ð/"), ("v", "/v/"), ("r", "/r/"),
    ("zh", "/ʒ/"), ("sh", "/ʃ/"), ("ch", "/tʃ/"),
    ("tion", "/ʃən/"), ("sure", "/ʒər/"),
]

# Mapping: first letter(s) → IPA phoneme for scoring
_PHONEME_MAP: dict[str, str] = {
    "a": "/eɪ/", "b": "/b/", "c": "/k/", "d": "/d/", "e": "/iː/",
    "f": "/f/", "g": "/ɡ/", "h": "/h/", "i": "/aɪ/", "j": "/dʒ/",
    "k": "/k/", "l": "/l/", "m": "/m/", "n": "/n/", "o": "/oʊ/",
    "p": "/p/", "q": "/kw/", "r": "/r/", "s": "/s/", "t": "/t/",
    "u": "/juː/", "v": "/v/", "w": "/w/", "x": "/eks/", "y": "/j/", "z": "/z/",
}


def _get_word_phonemes(word: str) -> list[tuple[str, bool]]:
    """Return phoneme representations for a word, marking difficult ones."""
    result: list[tuple[str, bool]] = []
    word_lower = word.lower()
    i = 0
    while i < len(word_lower):
        # Check multi-char patterns first
        matched = False
        for pattern, ph in _DIFFICULT_PATTERNS:
            if word_lower[i:].startswith(pattern):
                result.append((ph, True))  # difficult phoneme
                i += len(pattern)
                matched = True
                break
        if not matched:
            ch = word_lower[i]
            ph = _PHONEME_MAP.get(ch, f"/{ch}/")
            result.append((ph, False))
            i += 1
    if not result:
        result.append((f"/{word}/", False))
    return result


def _score_word_pronunciation(word: str) -> int:
    """Score pronunciation difficulty for a word (higher = easier for Chinese speaker)."""
    word_lower = word.lower()
    difficulty_penalty = 0
    for pattern, _ in _DIFFICULT_PATTERNS:
        if pattern in word_lower:
            difficulty_penalty += 12
    length_penalty = max(0, (len(word) - 5) * 3)
    return max(40, min(100, 90 - difficulty_penalty - length_penalty))


def _analyze_text(text: str) -> dict:
    """Analyze English text for pronunciation/fluency characteristics."""
    raw_words = text.strip().split()
    clean_words = [w.strip(".,!?;:\"'()") for w in raw_words]
    clean_words = [w for w in clean_words if w]

    if not clean_words:
        return {
            "overall": 65, "pronunciation_score": 65, "fluency_score": 65,
            "completeness_score": 70, "prosody_score": 65,
            "advice": "试着说点什么吧！从简单的句子开始练习。",
        }

    # Count difficult phonemes across all words
    difficult_count = 0
    for word in clean_words:
        for pattern, _ in _DIFFICULT_PATTERNS:
            if pattern in word.lower():
                difficult_count += 1

    # Pronunciation: penalized by difficult phoneme density
    diff_density = difficult_count / max(len(clean_words), 1)
    pronunciation_score = max(40, min(95, 85 - int(diff_density * 35)))

    # Fluency: longer words + reasonable sentence complexity → higher fluency
    avg_word_len = sum(len(w) for w in clean_words) / max(len(clean_words), 1)
    sentences = max(1, text.count('.') + text.count('!') + text.count('?') + text.count('\n'))
    wps = len(clean_words) / sentences  # words per sentence
    fluency_score = max(40, min(95, 50 + int(wps * 3) + int(avg_word_len * 2)))

    # Completeness: response forms a complete thought
    first_word = clean_words[0].lower() if clean_words else ""
    has_subject = first_word in {
        "i", "you", "he", "she", "it", "we", "they",
        "this", "that", "these", "those", "there", "the", "a", "an",
        "my", "your", "his", "her", "our", "their",
        "yes", "no", "well", "ok", "okay", "maybe", "sure",
        "what", "when", "where", "why", "how", "who",
        "can", "could", "would", "should", "will", "do", "does", "did",
        "please", "let", "thanks", "thank",
    }
    word_count = len(clean_words)
    if word_count >= 6 and has_subject:
        completeness = 95
    elif word_count >= 3:
        completeness = 80
    else:
        completeness = 65

    # Prosody: based on punctuation variety and sentence structure
    has_comma = ',' in text
    has_period = any(c in text for c in '.!?')
    prosody_score = 65 + (10 if has_comma else 0) + (10 if has_period else 0)
    prosody_score = min(90, prosody_score)

    # Overall weighted score
    overall = int(pronunciation_score * 0.35 + fluency_score * 0.30
                  + completeness * 0.20 + prosody_score * 0.15)

    # Generate advice
    advice_parts = []
    if pronunciation_score < 65:
        advice_parts.append("注意 /θ/ /ð/ /v/ 等音素的发音位置")
    if fluency_score < 65:
        advice_parts.append("尝试使用更长的句子，增加表达流畅度")
    if completeness < 75:
        advice_parts.append("尽量说完整的句子")
    if overall >= 80:
        advice = "发音和流畅度都很棒！继续保持。"
    elif advice_parts:
        advice = "；".join(advice_parts[:2]) + "。"
    else:
        advice = "表现不错，继续练习提升流利度。"

    return {
        "overall": overall,
        "pronunciation_score": pronunciation_score,
        "fluency_score": fluency_score,
        "completeness_score": completeness,
        "prosody_score": prosody_score,
        "advice": advice,
    }


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
    """Return empty string when no ASR text could be recognized from audio.
    The frontend provides ASR text via browser SpeechRecognition in normal operation,
    so this fallback is only reached when both recognition and audio upload fail."""
    return ""


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
        scene_result = await db.execute(
            select(Scene)
            .where(Scene.id == session.scene_id)
            .options(
                selectinload(Scene.vocabulary),
                selectinload(Scene.sentence_patterns),
            )
        )
        scene = scene_result.scalar_one_or_none()
        if scene:
            vocab_list = [
                {"word": v.word, "translation": v.translation or "", "phonetic": v.phonetic or ""}
                for v in (scene.vocabulary or [])
            ]
            pattern_list = [
                {"pattern": p.pattern, "translation": p.translation or ""}
                for p in (scene.sentence_patterns or [])
            ]
            scene_data = {
                "role_prompt": scene.role_prompt,
                "opening_line": scene.opening_line,
                "difficulty_settings": scene.difficulty_settings or {},
                "scene_name": scene.name or "",
                "description": scene.description or "",
                "vocab_list": vocab_list,
                "sentence_patterns": pattern_list,
            }

    # Load custom scene data — first from active_connections (live session), then from DB
    conn_info = active_connections.get(session_id, {})
    custom_role = conn_info.get("custom_role_prompt", "")
    custom_desc = conn_info.get("custom_description", "")
    custom_scene_name = conn_info.get("custom_scene_name", "")
    custom_vocab: list = conn_info.get("custom_vocab_list", []) or []
    custom_patterns: list = conn_info.get("custom_sentence_patterns", []) or []

    # Fallback: look up custom_scene from DB if session has custom_scene_id
    if session.custom_scene_id:
        from ..models.custom_scene import CustomScene as CustomSceneModel
        cs_result = await db.execute(
            select(CustomSceneModel).where(CustomSceneModel.id == session.custom_scene_id)
        )
        custom_scene_row = cs_result.scalar_one_or_none()
        if custom_scene_row and custom_scene_row.prompt_snapshot:
            try:
                import json as _cs_json
                cs_data = _cs_json.loads(custom_scene_row.prompt_snapshot)
                if not custom_role:
                    custom_role = cs_data.get("role_prompt", "")
                if not custom_desc:
                    custom_desc = cs_data.get("description", "")
                if not custom_scene_name:
                    custom_scene_name = cs_data.get("topic", "")
                if not custom_vocab:
                    custom_vocab = cs_data.get("vocab_list", []) or cs_data.get("vocabulary", []) or []
                if not custom_patterns:
                    custom_patterns = cs_data.get("sentence_patterns", []) or cs_data.get("patterns", []) or []
            except Exception:
                pass
        # Also use DB columns as fallback
        if not custom_vocab and custom_scene_row and custom_scene_row.focus_vocab:
            custom_vocab = [{"word": w, "translation": ""} for w in custom_scene_row.focus_vocab if w]
        if not custom_patterns and custom_scene_row and custom_scene_row.focus_grammar:
            custom_patterns = [{"pattern": p, "translation": ""} for p in custom_scene_row.focus_grammar if p]

    # Override scene_data with custom scene info
    if custom_role or custom_vocab or custom_patterns:
        if not scene_data:
            scene_data = {}
        if custom_role:
            scene_data["role_prompt"] = custom_role
        if custom_desc:
            scene_data["description"] = custom_desc
        if custom_scene_name:
            scene_data["scene_name"] = custom_scene_name
        if custom_vocab:
            scene_data["vocab_list"] = custom_vocab
        if custom_patterns:
            scene_data["sentence_patterns"] = custom_patterns

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


def _check_scene_drift(text: str, scene_data: dict | None) -> str | None:
    """Check if user input drifts off-topic for the scene. Returns reminder or None."""
    if not scene_data:
        return None
    scene_name = scene_data.get("scene_name", "")
    text_lower = text.lower()
    words = set(text_lower.split())

    # Build keywords: known scene keywords + dynamic from vocab/description
    keywords: set[str] = set()
    # Known scene keywords
    known_kw = SCENE_KEYWORDS.get(scene_name, set())
    keywords.update(known_kw)
    # Dynamic keywords from vocab_list
    for v in scene_data.get("vocab_list", []):
        if isinstance(v, dict):
            w = (v.get("word", "") or "").lower()
        else:
            w = str(v).lower()
        if w and len(w) > 2:
            keywords.add(w)
    # Dynamic keywords from description (extract nouns/noun phrases)
    desc = (scene_data.get("description", "") or "").lower()
    for word in desc.split():
        w = word.strip(".,!?;:()\"'，。！？；：（）")
        if len(w) > 3 and w not in {"this", "that", "with", "from", "your", "about", "practice", "scene", "conversation"}:
            keywords.add(w)

    if not keywords:
        return None

    match_count = sum(1 for kw in keywords if kw in text_lower)

    if match_count == 0:
        # Only warn for substantive messages (5+ words)
        if len(words) >= 5:
            topic = scene_name or desc or "our conversation"
            return f"Let's stay focused on {topic}. Can we get back to it?"
    return None


def _extract_role_from_scene(scene_data: dict | None) -> tuple[str, str]:
    """Extract a human-readable role name and scene name from scene data."""
    if not scene_data:
        return "a conversation partner", ""

    role_prompt = (scene_data.get("role_prompt", "") or "").lower()
    scene_name = scene_data.get("scene_name", "") or ""
    description = scene_data.get("description", "") or ""

    # Known role patterns
    role_patterns = [
        ("barista", "the barista", "coffee shop"),
        ("waiter", "the waiter", "restaurant"),
        ("waitress", "the waitress", "restaurant"),
        ("sales assistant", "the sales assistant", "clothing store"),
        ("shop assistant", "the shop assistant", "clothing store"),
        ("check-in agent", "the check-in agent", "airport"),
        ("receptionist", "the receptionist", "hotel"),
        ("front desk", "the front desk agent", "hotel"),
        ("local", "a friendly local", "street"),
        ("tour guide", "the tour guide", "street"),
        ("hr manager", "the HR manager", "job interview"),
        ("interviewer", "the interviewer", "job interview"),
        ("team lead", "the team lead", "business meeting"),
        ("doctor", "the doctor", "hospital"),
        ("nurse", "the nurse", "hospital"),
        ("pharmacist", "the pharmacist", "pharmacy"),
        ("teacher", "the teacher", "classroom"),
        ("librarian", "the librarian", "library"),
        ("bank teller", "the bank teller", "bank"),
        ("police officer", "the police officer", "police station"),
        ("travel agent", "the travel agent", "travel agency"),
        ("customer service", "the customer service agent", "customer support"),
        ("coworker", "your coworker", "office"),
        ("friend", "your friend", "casual conversation"),
    ]

    for pattern, role_label, scene_label in role_patterns:
        if pattern in role_prompt:
            return role_label, scene_label

    # Fallback: extract from scene description
    if scene_name:
        return f"the {scene_name} partner", scene_name
    if description:
        return "a conversation partner", description[:30]
    return "a conversation partner", scene_name


def _simulate_llm_response(
    text: str,
    scene_data: dict | None,
) -> str:
    """Generate a contextual AI response based on user input and scene context.

    Uses scene vocabulary, patterns, and description to stay on-topic even
    when the LLM API is unavailable.
    """
    lower = text.strip().lower().rstrip(".!?")

    # Determine the scene role
    role, scene_name = _extract_role_from_scene(scene_data)

    # Get scene vocab for contextual responses
    vocab_words: list[str] = []
    if scene_data:
        for v in scene_data.get("vocab_list", []):
            if isinstance(v, dict):
                w = v.get("word", "")
            else:
                w = str(v)
            if w and len(w) > 1:
                vocab_words.append(w.lower())

    # Get scene patterns for template usage
    patterns: list[str] = []
    if scene_data:
        for p in scene_data.get("sentence_patterns", []):
            if isinstance(p, dict):
                pt = p.get("pattern", "")
            else:
                pt = str(p)
            if pt:
                patterns.append(pt)

    # --- Greetings ---
    if lower in ("hello", "hi", "hey", "hi there", "good morning", "good afternoon", "good evening"):
        return f"Hello! I'm {role}. How are you doing today?"

    if lower in ("i'm fine", "i am fine", "fine thanks", "i'm good", "i am good", "doing well", "i'm doing well"):
        return f"Glad to hear that! So, what brings you here today? {_scene_prompt(scene_data)}"

    if lower in ("thank you", "thanks", "thank you very much", "thanks a lot"):
        return "You're very welcome! Is there anything else I can help you with?"

    if lower in ("bye", "goodbye", "see you", "see you later"):
        return "Goodbye! It was great talking with you. Keep practicing your English!"

    # --- Scene drift check ---
    drift_msg = _check_scene_drift(text, scene_data)
    if drift_msg:
        return drift_msg

    # --- Scene-specific contextual responses ---
    if "how are you" in lower:
        return f"I'm doing great, thanks for asking! Now, {_scene_prompt(scene_data)}"

    # Questions about self / who are you
    if any(w in lower.split() for w in ("who", "name", "your")) and "you" in lower.split():
        return f"I'm {role}, here to help you practice English. But let's focus on you — {_scene_prompt(scene_data)}"

    # Scene-specific ordering/requesting (only for service-oriented scenes)
    order_words = {"order", "buy", "purchase", "book", "reserve"}
    request_phrases = ["i'd like", "i would like", "can i get", "could i have", "may i have"]
    is_order_scene = scene_name in ("coffee shop", "restaurant", "hotel", "airport", "clothing store")

    if any(w in lower.split() for w in order_words) or any(ph in lower for ph in request_phrases):
        if is_order_scene:
            item = _extract_keyword_after(text, ["order", "buy", "i'd like", "i would like", "can i get", "could i have", "may i have"])
            if item:
                return f"Great choice! One {item} coming right up. Can I get you anything else?"
            return f"Sure! What exactly would you like? Tell me more about what you're looking for."
        else:
            # Non-service scene — acknowledge request without restaurant framing
            return f"I'd be happy to help with that. {_scene_prompt(scene_data)}"

    # Scene vocabulary matches — respond with contextual acknowledgment
    matched_vocab = [w for w in vocab_words if w in lower]
    if matched_vocab:
        word = matched_vocab[0]
        # Use a scene pattern if available
        if patterns:
            import random
            pattern = random.choice(patterns)
            return f"Ah, {word} — great word! {pattern}. What else can you tell me?"
        return f"Ah, '{word}' — that's relevant to our conversation! Tell me more about that."

    # Opinions / I think
    if any(phrase in lower for phrase in ("i think", "i believe", "in my opinion", "i feel", "i guess")):
        return f"Interesting perspective! Why do you feel that way? Tell me more."

    # Likes / preferences
    if any(w in lower.split() for w in ("like", "love", "enjoy", "prefer", "favorite", "hate", "dislike")):
        return f"Oh really? That's fascinating! What do you like most about it?"

    # Yes/No short answers
    if lower in ("yes", "yeah", "yep", "sure", "ok", "okay"):
        return f"Great! {_scene_prompt(scene_data)}"

    if lower in ("no", "nope", "not really"):
        return f"I understand. Is there something else you'd prefer instead?"

    # Generic: reference the user's topic
    topic_words = [w for w in lower.split() if len(w) > 3]
    if topic_words:
        topic = topic_words[0]
        return f"That's interesting what you said about '{topic}'. Can you tell me more about that?"

    # Fallback with scene description
    desc = scene_data.get("description", "") if scene_data else ""
    if desc:
        return f"I see! Let's keep practicing — {desc}. What would you like to say next?"
    return f"I see! Tell me more. {_scene_prompt(scene_data)}"


def _scene_prompt(scene_data: dict | None) -> str:
    """Get a contextual prompt based on the scene."""
    if not scene_data:
        return "What would you like to talk about?"
    desc = scene_data.get("description", "")
    if desc:
        return f"Let's continue with: {desc}"
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
                    # Store ALL custom scene data so LLM uses the AI-generated role & description
                    custom_role = custom_scene.get("role_prompt", "")
                    custom_desc = custom_scene.get("description", "")
                    custom_scene_name = custom_scene.get("topic") or custom_scene.get("name") or ""
                    custom_vocab = custom_scene.get("vocab_list", []) or custom_scene.get("vocabulary", []) or []
                    custom_sentence_patterns = custom_scene.get("sentence_patterns", []) or custom_scene.get("patterns", []) or []
                    custom_scene_id = custom_scene.get("custom_scene_id") or payload.get("custom_scene_id")
                else:
                    opening_line = (
                        session_scene.opening_line if session_scene
                        else "Hello! Let's practice English. What would you like to talk about?"
                    )
                    custom_role = ""
                    custom_desc = ""
                    custom_scene_name = ""
                    custom_vocab = []
                    custom_sentence_patterns = []
                    custom_scene_id = None

                active_connections[session.id] = {
                    "websocket": websocket,
                    "user_id": user_id,
                    "interrupted_responses": set(),
                    "tts_voice": negotiated["tts_voice"],
                    "custom_role_prompt": custom_role,
                    "custom_description": custom_desc,
                    "custom_scene_name": custom_scene_name,
                    "custom_vocab_list": custom_vocab,
                    "custom_sentence_patterns": custom_sentence_patterns,
                    "custom_scene_id": custom_scene_id,
                    "scene_name": custom_scene_name or (session_scene.name if session_scene else ""),
                }

                # If custom_scene_id wasn't saved to the session during creation, update it now
                if custom_scene_id and session and not session.custom_scene_id:
                    try:
                        session.custom_scene_id = uuid.UUID(str(custom_scene_id))
                        await db.commit()
                    except (ValueError, TypeError):
                        pass

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


# ── System prompt builder ─────────────────────────────────────────────

DIFFICULTY_INSTRUCTIONS: dict[str, str] = {
    "beginner": (
        "Use simple vocabulary (CEFR A1-A2 level). Keep sentences short (8-12 words). "
        "Speak at a slow, clear pace. Be very patient and encouraging. "
        "When the user makes a grammar error, gently include the corrected form in your response "
        "without lengthy explanation. Ask simple follow-up questions to keep the conversation going."
    ),
    "intermediate": (
        "Use everyday vocabulary with occasional B1-B2 level words. Use natural conversational pace. "
        "Encourage longer responses with follow-up questions. "
        "Gently correct major grammar or vocabulary errors by modeling the correct form in your reply. "
        "Use a mix of short and medium-length sentences (10-20 words)."
    ),
    "advanced": (
        "Use rich vocabulary including C1-C2 level expressions and idioms. "
        "Use complex sentence structures where natural. Challenge the user with nuanced follow-up questions. "
        "Only correct significant errors — allow minor mistakes to flow naturally. "
        "Push for detailed, well-reasoned responses. Use authentic, native-like expressions."
    ),
}


def _build_system_prompt(scene_data: dict | None, difficulty: str = "intermediate") -> str:
    """Build a comprehensive system prompt that keeps the AI in character and on-topic.

    Combines role definition, scene context, difficulty-appropriate behavior,
    suggested vocabulary, sentence patterns, and strict scene-adherence rules.
    """
    if not scene_data:
        return (
            "You are a friendly English conversation partner. "
            "Respond naturally in English. Keep your responses to 1-3 sentences. "
            "Gently correct any English errors by modeling the correct form. "
            "Ask follow-up questions to keep the conversation going."
        )

    parts: list[str] = []

    # 1. Role definition (from AI-generated or built-in scene)
    role_prompt = scene_data.get("role_prompt", "")
    if role_prompt:
        parts.append(role_prompt)
    else:
        parts.append("You are a friendly English conversation partner. Respond naturally in English.")

    # 2. Scene context
    scene_name = scene_data.get("scene_name", "")
    description = scene_data.get("description", "")
    if scene_name or description:
        ctx_parts = []
        if scene_name:
            ctx_parts.append(f"Scene: {scene_name}")
        if description:
            ctx_parts.append(description)
        parts.append(" — ".join(ctx_parts))

    # 3. Difficulty-level behavioral instructions
    difficulty = difficulty or "intermediate"
    diff_instruction = DIFFICULTY_INSTRUCTIONS.get(
        difficulty, DIFFICULTY_INSTRUCTIONS["intermediate"]
    )
    parts.append(f"Conversation level: {difficulty}. {diff_instruction}")

    # 4. Vocabulary to naturally incorporate (when contextually relevant)
    vocab_list = scene_data.get("vocab_list", [])
    if vocab_list:
        words = []
        for v in vocab_list:
            if isinstance(v, dict):
                w = v.get("word", "") or v.get("pattern", "")
            else:
                w = str(v)
            if w and len(w) > 1:
                words.append(w)
        if words:
            parts.append(
                f"Try to naturally use these vocabulary words when relevant to the conversation: "
                f"{', '.join(words[:8])}. Do NOT force all of them — only use what fits the flow."
            )

    # 5. Sentence patterns to use as templates
    patterns = scene_data.get("sentence_patterns", [])
    if patterns:
        pattern_texts = []
        for p in patterns:
            if isinstance(p, dict):
                pt = p.get("pattern", "") or p.get("word", "")
            else:
                pt = str(p)
            if pt and len(pt) > 3:
                pattern_texts.append(pt)
        if pattern_texts:
            parts.append(
                f"Reference sentence structures to use naturally: {'; '.join(pattern_texts[:5])}"
            )

    # 6. Scene adherence + error correction + response length
    parts.append(
        "CRITICAL RULES:\n"
        "- Stay strictly in character for this scene at all times.\n"
        "- If the user goes off-topic, politely steer the conversation back to the scene.\n"
        "- Gently correct English grammar, vocabulary, or pronunciation errors "
        "by naturally using the correct form in your response.\n"
        "- Keep responses to 1-3 sentences. Do NOT write essays.\n"
        "- Always end with a question or prompt to encourage the user to continue.\n"
        "- Respond in English only."
    )

    return "\n\n".join(parts)


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

    # Build comprehensive system prompt from scene data
    session_difficulty = session_obj.difficulty if session_obj else "intermediate"
    system_prompt = _build_system_prompt(scene_data, difficulty=session_difficulty)

    # Scene context prefix for the user message (reinforces scene awareness)
    scene_name = scene_data.get("scene_name", "") if scene_data else ""
    scene_desc = scene_data.get("description", "") if scene_data else ""
    context_prefix = ""
    if scene_name or scene_desc:
        ctx_parts = []
        if scene_name:
            ctx_parts.append(scene_name)
        if scene_desc:
            ctx_parts.append(scene_desc)
        context_prefix = f"[Current scene: {' — '.join(ctx_parts)}]\n"

    # Include difficulty hint in user message for additional reinforcement
    diff_hint = f"[Difficulty: {session_difficulty}]\n" if session_difficulty else ""
    contextualized_message = f"{context_prefix}{diff_hint}User says: \"{asr_text}\""

    # Choose temperature based on difficulty: lower for beginners (more predictable),
    # slightly higher for advanced (more creative/natural)
    difficulty_temperature = {
        "beginner": 0.6,
        "intermediate": 0.7,
        "advanced": 0.75,
    }
    llm_temperature = difficulty_temperature.get(session_difficulty, 0.7)

    from ..services.llm_service import generate_response
    ai_text = await generate_response(
        contextualized_message,
        system_prompt,
        history,
        temperature=llm_temperature,
        max_tokens=300,
    )
    if not ai_text:
        print(f"[WS] LLM returned None — falling back to simulated response. Provider: {settings.llm_provider}")

    # Fall back to simulated response if LLM unavailable
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
