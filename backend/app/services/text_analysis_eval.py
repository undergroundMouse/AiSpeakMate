"""Text-based pronunciation evaluation fallback (estimate, not audio)."""

from __future__ import annotations

from sqlalchemy.ext.asyncio import AsyncSession

from ..models.evaluation import PhonemeScore, PronunciationEvaluation
from ..models.session import Utterance

_DIFFICULT_PATTERNS: list[tuple[str, str]] = [
    ("th", "/θ/"), ("th", "/ð/"), ("v", "/v/"), ("r", "/r/"),
    ("zh", "/ʒ/"), ("sh", "/ʃ/"), ("ch", "/tʃ/"),
    ("tion", "/ʃən/"), ("sure", "/ʒər/"),
]

_PHONEME_MAP: dict[str, str] = {
    "a": "/eɪ/", "b": "/b/", "c": "/k/", "d": "/d/", "e": "/iː/",
    "f": "/f/", "g": "/ɡ/", "h": "/h/", "i": "/aɪ/", "j": "/dʒ/",
    "k": "/k/", "l": "/l/", "m": "/m/", "n": "/n/", "o": "/oʊ/",
    "p": "/p/", "q": "/kw/", "r": "/r/", "s": "/s/", "t": "/t/",
    "u": "/juː/", "v": "/v/", "w": "/w/", "x": "/eks/", "y": "/j/", "z": "/z/",
}


def _get_word_phonemes(word: str) -> list[tuple[str, bool]]:
    result: list[tuple[str, bool]] = []
    word_lower = word.lower()
    i = 0
    while i < len(word_lower):
        matched = False
        for pattern, ph in _DIFFICULT_PATTERNS:
            if word_lower[i:].startswith(pattern):
                result.append((ph, True))
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
    length_bonus = min(10, max(0, (len(word) - 3) * 1))
    return min(95, max(50, 75 + length_bonus))


def analyze_text(text: str) -> dict:
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

    word_count = len(clean_words)
    avg_word_len = sum(len(w) for w in clean_words) / max(word_count, 1)
    sentences = max(1, text.count('.') + text.count('!') + text.count('?') + text.count('\n'))
    wps = word_count / sentences
    unique_words = len(set(w.lower() for w in clean_words))
    ttr = unique_words / max(word_count, 1)

    speech_complexity = min(1.0, (avg_word_len - 2) / 6)
    pronunciation_score = max(45, min(92, 60 + int(wps * 2) + int(speech_complexity * 15)))
    fluency_score = max(40, min(90, 55 + int(wps * 3)))

    first_word = clean_words[0].lower()
    has_subject = first_word in {
        "i", "you", "he", "she", "it", "we", "they",
        "this", "that", "these", "those", "there", "the",
        "my", "your", "his", "her", "our", "their",
        "yes", "no", "well", "ok", "okay", "maybe", "sure",
        "what", "when", "where", "why", "how", "who",
        "can", "could", "would", "should", "will", "do", "does", "did",
        "please", "let", "thanks", "thank",
    }
    if word_count >= 8 and has_subject:
        completeness = 95
    elif word_count >= 5 and has_subject:
        completeness = 85
    elif word_count >= 3:
        completeness = 75
    else:
        completeness = 60

    has_comma = ',' in text
    has_period = any(c in text for c in '.!?')
    has_question = '?' in text
    prosody_score = 65 + (10 if has_comma else 0) + (8 if has_period else 0) + (7 if has_question else 0)
    prosody_score = min(92, prosody_score)

    overall = int(
        pronunciation_score * 0.30 + fluency_score * 0.30
        + completeness * 0.25 + prosody_score * 0.15
    )

    advice_parts = []
    if word_count < 5:
        advice_parts.append("尝试说更完整的句子")
    if ttr < 0.5 and word_count > 5:
        advice_parts.append("尝试使用更丰富的词汇")
    if fluency_score < 60:
        advice_parts.append("增加句子长度可以提高流利度")
    if overall >= 85:
        advice = "表现很棒！句子结构完整，表达流畅。"
    elif overall >= 70:
        advice = "继续加油，尝试使用更复杂的句型。"
    elif advice_parts:
        advice = "；".join(advice_parts[:2]) + "。"
    else:
        advice = "多练习，逐步提升表达的完整度。"

    return {
        "overall": overall,
        "pronunciation_score": pronunciation_score,
        "fluency_score": fluency_score,
        "completeness_score": completeness,
        "prosody_score": prosody_score,
        "advice": advice,
    }


def _clip_field(value: str | None, max_len: int) -> str | None:
    if not value:
        return None
    return value[:max_len]


async def store_text_analysis_evaluation(
    db: AsyncSession,
    utterance: Utterance,
    text: str,
    *,
    no_audio: bool = False,
) -> PronunciationEvaluation:
    """Persist a text-analysis-based pronunciation evaluation."""
    analysis = analyze_text(text)
    advice = analysis["advice"]
    if no_audio:
        advice = f"{advice}（基于文本估算，用麦克风录音可获得更准确的纠音）"

    evaluation = PronunciationEvaluation(
        utterance_id=utterance.id,
        overall_score=analysis["overall"],
        pronunciation_score=analysis["pronunciation_score"],
        fluency_score=analysis["fluency_score"],
        completeness_score=analysis["completeness_score"],
        prosody_score=analysis["prosody_score"],
        advice=advice,
        source="text_analysis",
    )
    db.add(evaluation)
    await db.flush()

    words = [w.strip(".,!?;:\"'()") for w in text.split()]
    words = [w for w in words[:10] if w]

    for word in words:
        phonemes = _get_word_phonemes(word)
        word_score = _score_word_pronunciation(word)
        for i, (ph, is_diff) in enumerate(phonemes):
            ph_score = max(40, min(100, word_score - (15 if is_diff else 0)))
            db.add(PhonemeScore(
                evaluation_id=evaluation.id,
                word=word[:100],
                word_score=word_score,
                phoneme=_clip_field(ph, 10) or ph[:10],
                phoneme_score=ph_score,
                is_error=is_diff,
                suggested_phoneme=_clip_field(ph, 10) if is_diff else None,
                start_time_ms=i * 200,
                end_time_ms=(i + 1) * 200,
            ))

    await db.commit()
    await db.refresh(evaluation)
    return evaluation
