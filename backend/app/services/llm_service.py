"""LLM service — supports Groq, DeepSeek, and any OpenAI-compatible API."""

from openai import AsyncOpenAI

from ..core.config import settings

_client: AsyncOpenAI | None = None
_provider: str = ""

# Provider presets
PROVIDERS = {
    "groq": {
        "base_url": "https://api.groq.com/openai/v1",
        "model": "llama-3.1-70b-versatile",
    },
    "deepseek": {
        "base_url": "https://api.deepseek.com/v1",
        "model": "deepseek-chat",
    },
    "glm": {
        "base_url": "https://open.bigmodel.cn/api/paas/v4",
        "model": "glm-4-flash",
    },
    "moonshot": {
        "base_url": "https://api.moonshot.cn/v1",
        "model": "moonshot-v1-8k",
    },
    "dashscope": {
        "base_url": "https://dashscope.aliyuncs.com/compatible-mode/v1",
        "model": "qwen-plus",
    },
}


def _get_client() -> AsyncOpenAI | None:
    """Lazy-init OpenAI-compatible client based on LLM_PROVIDER config."""
    global _client, _provider

    provider = settings.llm_provider or "groq"
    api_key = settings.llm_api_key or settings.groq_api_key
    if not api_key:
        return None

    if _client is None or _provider != provider:
        preset = PROVIDERS.get(provider, PROVIDERS["groq"])
        _client = AsyncOpenAI(
            api_key=api_key,
            base_url=preset["base_url"],
        )
        _provider = provider

    return _client


def _get_model() -> str:
    provider = settings.llm_provider or "groq"
    return settings.llm_model or PROVIDERS.get(provider, PROVIDERS["groq"])["model"]


async def generate_response(
    user_message: str,
    system_prompt: str,
    conversation_history: list[dict] | None = None,
) -> str | None:
    """Generate AI response via configured LLM provider.

    Falls back to None if no API key configured.
    """
    client = _get_client()
    if client is None:
        return None

    messages = [{"role": "system", "content": system_prompt}]

    if conversation_history:
        for msg in conversation_history[-10:]:
            messages.append({"role": msg["role"], "content": msg["content"]})

    messages.append({"role": "user", "content": user_message})

    try:
        response = await client.chat.completions.create(
            model=_get_model(),
            messages=messages,
            max_tokens=300,
            temperature=0.7,
        )
        return response.choices[0].message.content
    except Exception as e:
        print(f"LLM error ({_provider}): {e}")
        return None
