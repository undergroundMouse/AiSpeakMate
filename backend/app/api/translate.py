"""Translation endpoint using free MyMemory API (no key required)."""

import httpx
from fastapi import APIRouter
from pydantic import BaseModel, Field

router = APIRouter(prefix="/translate", tags=["translate"])

MYMEMORY_URL = "https://api.mymemory.translated.net/get"


class TranslateRequest(BaseModel):
    text: str = Field(..., min_length=1, max_length=2000)
    source_lang: str = "en"
    target_lang: str = "zh-CN"


class TranslateResponse(BaseModel):
    original: str
    translated: str
    source_lang: str
    target_lang: str


@router.post("", response_model=TranslateResponse)
async def translate_text(req: TranslateRequest):
    """Translate text using MyMemory free API."""
    # Try MyMemory first
    async with httpx.AsyncClient(timeout=10.0) as client:
        try:
            resp = await client.get(MYMEMORY_URL, params={
                "q": req.text,
                "langpair": f"{req.source_lang}|{req.target_lang}",
            })
            if resp.status_code == 200:
                data = resp.json()
                translated = (
                    data.get("responseData", {})
                    .get("translatedText", "")
                )
                if translated and translated != req.text:
                    return TranslateResponse(
                        original=req.text,
                        translated=translated,
                        source_lang=req.source_lang,
                        target_lang=req.target_lang,
                    )
        except Exception:
            pass

    # Fallback: simple word-by-word dictionary
    fallback = _dictionary_translate(req.text)
    return TranslateResponse(
        original=req.text,
        translated=fallback,
        source_lang=req.source_lang,
        target_lang=req.target_lang,
    )


def _dictionary_translate(text: str) -> str:
    """Simple EN→ZH dictionary fallback."""
    DICT = {
        "hello": "你好",
        "hi": "嗨",
        "good morning": "早上好",
        "good afternoon": "下午好",
        "good evening": "晚上好",
        "thank you": "谢谢",
        "thanks": "谢谢",
        "you're welcome": "不客气",
        "goodbye": "再见",
        "bye": "再见",
        "please": "请",
        "sorry": "对不起",
        "yes": "是的",
        "no": "不",
        "how are you": "你好吗",
        "i'm fine": "我很好",
        "nice to meet you": "很高兴认识你",
        "what": "什么",
        "where": "哪里",
        "when": "什么时候",
        "why": "为什么",
        "how": "怎么",
        "who": "谁",
        "welcome": "欢迎",
        "great": "太好了",
        "good": "好的",
        "bad": "坏的",
        "today": "今天",
        "tomorrow": "明天",
        "yesterday": "昨天",
        "coffee": "咖啡",
        "tea": "茶",
        "water": "水",
        "food": "食物",
        "menu": "菜单",
        "order": "点餐",
        "help": "帮助",
        "like": "喜欢",
        "love": "爱",
        "want": "想要",
        "need": "需要",
        "can": "可以",
        "weather": "天气",
        "time": "时间",
        "talk": "谈话",
        "practice": "练习",
        "english": "英语",
        "question": "问题",
        "answer": "回答",
        "interesting": "有趣",
        "difficult": "困难",
        "easy": "简单",
        "important": "重要",
        "beautiful": "美丽",
        "delicious": "美味",
        "friend": "朋友",
        "family": "家庭",
        "work": "工作",
        "school": "学校",
        "home": "家",
        "restaurant": "餐厅",
        "hotel": "酒店",
        "airport": "机场",
        "flight": "航班",
        "room": "房间",
        "reservation": "预订",
        "recommend": "推荐",
        "suggestion": "建议",
        "i think": "我认为",
        "i believe": "我相信",
        "in my opinion": "在我看来",
    }

    result = text
    # Replace known phrases (longer matches first)
    sorted_phrases = sorted(DICT.keys(), key=len, reverse=True)
    for phrase in sorted_phrases:
        if phrase in result.lower():
            result = result.replace(phrase, DICT[phrase])
    return result
