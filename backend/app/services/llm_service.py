"""LLM service using Groq API (Llama 3 70B)."""

from groq import AsyncGroq

from ..core.config import settings

# Lazy-initialized client
_client: AsyncGroq | None = None


def _get_client() -> AsyncGroq | None:
    global _client
    if not settings.groq_api_key:
        return None
    if _client is None:
        _client = AsyncGroq(api_key=settings.groq_api_key)
    return _client


async def generate_response(
    user_message: str,
    system_prompt: str,
    conversation_history: list[dict] | None = None,
) -> str | None:
    """Generate a contextual AI response using Groq LLM.

    Args:
        user_message: The user's latest message
        system_prompt: Scene role prompt defining AI behavior
        conversation_history: Previous messages [{"role":"user"/"assistant","content":"..."}]

    Returns:
        AI response text, or None if Groq is unavailable
    """
    client = _get_client()
    if client is None:
        return None  # No API key configured — caller should fall back

    messages = [{"role": "system", "content": system_prompt}]

    # Include recent conversation context (last 10 messages)
    if conversation_history:
        for msg in conversation_history[-10:]:
            messages.append({
                "role": msg["role"],
                "content": msg["content"],
            })

    messages.append({"role": "user", "content": user_message})

    try:
        response = await client.chat.completions.create(
            model=settings.groq_model,
            messages=messages,
            max_tokens=300,
            temperature=0.7,
        )
        return response.choices[0].message.content
    except Exception as e:
        print(f"Groq API error: {e}")
        return None
