"""Dictionary endpoint — proxies to 金山词霸 (iciba) for rich definitions."""

import httpx
from fastapi import APIRouter
from pydantic import BaseModel

router = APIRouter(prefix="/dictionary", tags=["dictionary"])


class DictResponse(BaseModel):
    word: str
    phonetic: str = ""
    audio_url: str = ""
    meanings: list[dict] = []
    phrases: list[dict] = []


@router.get("/{word}", response_model=DictResponse)
async def lookup_word(word: str):
    """Look up a word using 金山词霸 (iciba) public API."""
    result = DictResponse(word=word)

    async with httpx.AsyncClient(timeout=8.0) as client:
        # Try iciba API first (richest Chinese-English dictionary)
        try:
            resp = await client.get(
                "https://dict.iciba.com/dictionary/word/query/web",
                params={"word": word, "client": "6"},
                headers={"User-Agent": "Mozilla/5.0"},
            )
            if resp.status_code == 200:
                data = resp.json()
                result = _parse_iciba(word, data)
                if result.meanings:
                    return result
        except Exception:
            pass

        # Fallback: Free Dictionary API
        try:
            resp = await client.get(
                f"https://api.dictionaryapi.dev/api/v2/entries/en/{word}",
                headers={"User-Agent": "Mozilla/5.0"},
            )
            if resp.status_code == 200:
                data = resp.json()
                result = _parse_free_dict(word, data)
                return result
        except Exception:
            pass

    return result


def _parse_iciba(word: str, data: dict) -> DictResponse:
    """Parse 金山词霸 API response."""
    result = DictResponse(word=word)

    # Phonetic
    baidu_trans = data.get("baidu_translate", {}) or {}
    result.phonetic = baidu_trans.get("uk_phonetic", "") or baidu_trans.get("us_phonetic", "")

    # Audio
    symbols = data.get("symbols", []) or []
    if symbols:
        parts = symbols[0].get("parts", [])
        if parts:
            for part in parts:
                means = ", ".join(part.get("means", [])) if isinstance(part.get("means"), list) else part.get("means", "")
                result.meanings.append({
                    "partOfSpeech": part.get("part", ""),
                    "definitions": [{
                        "definition": means,
                        "example": "",
                    }],
                })

    # Exchange (word forms)
    exchange = data.get("exchange", {}) or {}
    if exchange:
        forms = []
        for k, v in exchange.items():
            if v:
                label = {"word_pl": "复数", "word_past": "过去式", "word_done": "过去分词", "word_ing": "现在分词", "word_third": "三单"}.get(k, k)
                if isinstance(v, list):
                    forms.append(f"{label}: {', '.join(v)}")
                else:
                    forms.append(f"{label}: {v}")
        if forms:
            result.meanings.insert(0, {
                "partOfSpeech": "形态",
                "definitions": [{"definition": "; ".join(forms), "example": ""}],
            })

    # Phrases from iciba
    phrs = data.get("phrs", []) or []
    for phr in phrs[:5]:
        result.phrases.append({
            "phrase": phr.get("en", ""),
            "meaning": phr.get("cn", ""),
        })

    # If no meanings from symbols, try from baidu_translate
    if not result.meanings:
        means = baidu_translate.get("means", []) or []
        for m in means[:5]:
            result.meanings.append({
                "partOfSpeech": m.get("part", ""),
                "definitions": [{
                    "definition": ", ".join(m.get("means", [])) if isinstance(m.get("means"), list) else m.get("means", ""),
                    "example": "",
                }],
            })

    return result


def _parse_free_dict(word: str, data: list) -> DictResponse:
    """Parse Free Dictionary API response."""
    result = DictResponse(word=word)
    entry = data[0] if data else {}
    result.phonetic = entry.get("phonetic", "") or (entry.get("phonetics", [{}])[0].get("text", "") if entry.get("phonetics") else "")
    result.meanings = []
    for m in (entry.get("meanings", []) or [])[:5]:
        result.meanings.append({
            "partOfSpeech": m.get("partOfSpeech", ""),
            "definitions": [
                {"definition": d.get("definition", ""), "example": d.get("example", "")}
                for d in (m.get("definitions", []) or [])[:3]
            ],
        })
    return result
