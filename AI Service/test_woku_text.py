import asyncio
from openai import AsyncOpenAI
from infrastructure.config import get_settings

async def test():
    s = get_settings()
    c = AsyncOpenAI(api_key=s.WOKU_API_KEY, base_url=s.WOKU_BASE_URL)
    print(f"Model: {s.WOKU_MODEL}")
    # text only
    r = await c.chat.completions.create(
        model=s.WOKU_MODEL,
        messages=[{"role": "user", "content": "Reply with just: pong"}],
        max_tokens=10,
    )
    print("Text OK:", r.choices[0].message.content)

asyncio.run(test())
