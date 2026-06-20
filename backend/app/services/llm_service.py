"""LLM service — supports Groq, DeepSeek, and any OpenAI-compatible API."""

from openai import AsyncOpenAI

from ..core.config import settings

_client: AsyncOpenAI | None = None
_client_sig: str = ""

_runtime_llm: dict[str, str] = {}

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


def set_runtime_llm(provider: str, api_key: str, model: str = "") -> None:
    global _client, _client_sig
    _runtime_llm["provider"] = provider.strip()
    _runtime_llm["api_key"] = api_key.strip()
    _runtime_llm["model"] = model.strip()
    _client = None
    _client_sig = ""


def _resolved_provider() -> str:
    return _runtime_llm.get("provider") or settings.llm_provider or "groq"


def _resolved_api_key() -> str:
    return _runtime_llm.get("api_key") or settings.llm_api_key or settings.groq_api_key


def _resolved_model() -> str:
    if _runtime_llm.get("model"):
        return _runtime_llm["model"]
    if settings.llm_model:
        return settings.llm_model
    provider = _resolved_provider()
    return PROVIDERS.get(provider, PROVIDERS["groq"])["model"]


def is_llm_configured() -> bool:
    return bool(_resolved_api_key())


def _get_client() -> AsyncOpenAI | None:
    """Lazy-init OpenAI-compatible client based on LLM_PROVIDER config."""
    global _client, _client_sig

    provider = _resolved_provider()
    api_key = _resolved_api_key()
    if not api_key:
        return None

    sig = f"{provider}:{api_key}"
    if _client is None or _client_sig != sig:
        preset = PROVIDERS.get(provider, PROVIDERS["groq"])
        _client = AsyncOpenAI(
            api_key=api_key,
            base_url=preset["base_url"],
        )
        _client_sig = sig

    return _client


def _get_model() -> str:
    return _resolved_model()


async def generate_response(
    user_message: str,
    system_prompt: str,
    conversation_history: list[dict] | None = None,
    temperature: float = 0.7,
    max_tokens: int = 500,
) -> str | None:
    """Generate AI response via configured LLM provider.

    Falls back to None if no API key configured.

    Args:
        user_message: The user's input text
        system_prompt: System-level instructions for the AI
        conversation_history: Previous messages in the conversation
        temperature: 0.0–2.0; lower = more focused/deterministic (0.6–0.7 for scene roleplay)
        max_tokens: Maximum response length
    """
    client = _get_client()
    if client is None:
        return None

    messages = [{"role": "system", "content": system_prompt}]

    if conversation_history:
        # Include more history for better context
        for msg in conversation_history[-20:]:
            messages.append({"role": msg["role"], "content": msg["content"]})

    messages.append({"role": "user", "content": user_message})

    try:
        response = await client.chat.completions.create(
            model=_get_model(),
            messages=messages,
            max_tokens=max_tokens,
            temperature=temperature,
        )
        return response.choices[0].message.content
    except Exception as e:
        print(f"LLM error ({_resolved_provider()}): {e}")
        return None


async def generate_response_stream(
    user_message: str,
    system_prompt: str,
    conversation_history: list[dict] | None = None,
    temperature: float = 0.7,
    max_tokens: int = 500,
):
    """Stream LLM tokens. Yields text delta strings."""
    client = _get_client()
    if client is None:
        return

    messages = [{"role": "system", "content": system_prompt}]
    if conversation_history:
        for msg in conversation_history[-20:]:
            messages.append({"role": msg["role"], "content": msg["content"]})
    messages.append({"role": "user", "content": user_message})

    try:
        stream = await client.chat.completions.create(
            model=_get_model(),
            messages=messages,
            max_tokens=max_tokens,
            temperature=temperature,
            stream=True,
        )
        async for chunk in stream:
            delta = chunk.choices[0].delta.content if chunk.choices else None
            if delta:
                yield delta
    except Exception as e:
        print(f"LLM stream error ({_resolved_provider()}): {e}")
