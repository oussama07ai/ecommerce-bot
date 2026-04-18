"""
خدمة Claude API — كل تواصل مع الذكاء الاصطناعي
"""
import json
import re
import httpx
from config import settings
import logging

logger = logging.getLogger(__name__)

CLAUDE_URL = "https://api.anthropic.com/v1/messages"
HEADERS = {
    "x-api-key": settings.ANTHROPIC_API_KEY,
    "anthropic-version": "2023-06-01",
    "content-type": "application/json",
}


async def ask_claude(system_prompt: str, user_message: str, model: str = "haiku") -> dict:
    """
    يرسل رسالة لـ Claude ويرجع JSON محلل
    model: "haiku" (سريع/رخيص) أو "sonnet" (أقوى)
    """
    model_id = (
        "claude-haiku-4-5-20251001" if model == "haiku"
        else "claude-sonnet-4-6"
    )

    payload = {
        "model": model_id,
        "max_tokens": 1024,
        "system": system_prompt,
        "messages": [{"role": "user", "content": user_message}],
    }

    try:
        async with httpx.AsyncClient(timeout=30) as client:
            response = await client.post(CLAUDE_URL, headers=HEADERS, json=payload)
            response.raise_for_status()

        raw_text = response.json()["content"][0]["text"].strip()
        logger.info(f"Claude raw response: {raw_text[:200]}")

        # تنظيف إذا كان فيه markdown
        cleaned = re.sub(r"```(?:json)?\s*|\s*```", "", raw_text).strip()
        return json.loads(cleaned)

    except json.JSONDecodeError as e:
        logger.error(f"Claude JSON parse error: {e} | Response: {raw_text}")
        return {"status": "HANDOVER", "reply": "سيتواصل معك أحد وكلائنا قريباً 🙏", "reason": "خطأ في تحليل الرد"}

    except httpx.HTTPStatusError as e:
        logger.error(f"Claude API HTTP error: {e.response.status_code}")
        return {"status": "HANDOVER", "reply": "سيتواصل معك أحد وكلائنا قريباً 🙏", "reason": "خطأ في الاتصال"}

    except Exception as e:
        logger.error(f"Claude unexpected error: {e}")
        return {"status": "HANDOVER", "reply": "سيتواصل معك أحد وكلائنا قريباً 🙏", "reason": str(e)}
