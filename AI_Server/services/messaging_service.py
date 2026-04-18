"""
خدمة الرسائل — إرسال عبر WhatsApp و Instagram DM
"""
import httpx
import logging
from config import settings

logger = logging.getLogger(__name__)


async def send_whatsapp(phone: str, message: str, image_url: str = None):
    """إرسال رسالة WhatsApp عبر Meta Cloud API"""
    url = f"https://graph.facebook.com/v18.0/{settings.WHATSAPP_PHONE_NUMBER_ID}/messages"
    headers = {
        "Authorization": f"Bearer {settings.WHATSAPP_ACCESS_TOKEN}",
        "Content-Type": "application/json",
    }

    # تأكد من صيغة الرقم الصحيحة
    clean_phone = phone.replace("+", "").replace(" ", "").replace("-", "")

    payloads = []

    # إرسال صورة أولاً إذا طُلبت
    if image_url:
        payloads.append({
            "messaging_product": "whatsapp",
            "to": clean_phone,
            "type": "image",
            "image": {"link": image_url},
        })

    # رسالة النص
    payloads.append({
        "messaging_product": "whatsapp",
        "to": clean_phone,
        "type": "text",
        "text": {"body": message, "preview_url": False},
    })

    async with httpx.AsyncClient(timeout=15) as client:
        for payload in payloads:
            try:
                resp = await client.post(url, headers=headers, json=payload)
                if resp.status_code != 200:
                    logger.error(f"WhatsApp send error {resp.status_code}: {resp.text[:200]}")
                else:
                    logger.info(f"WhatsApp sent to {clean_phone}")
            except Exception as e:
                logger.error(f"WhatsApp exception: {e}")


async def send_instagram_dm(user_id: str, message: str):
    """إرسال Instagram DM عبر Meta Graph API"""
    url = f"https://graph.facebook.com/v18.0/me/messages"
    headers = {
        "Authorization": f"Bearer {settings.INSTAGRAM_ACCESS_TOKEN}",
        "Content-Type": "application/json",
    }
    payload = {
        "recipient": {"id": user_id},
        "message": {"text": message},
    }
    try:
        async with httpx.AsyncClient(timeout=15) as client:
            resp = await client.post(url, headers=headers, json=payload)
            if resp.status_code != 200:
                logger.error(f"Instagram DM error {resp.status_code}: {resp.text[:200]}")
            else:
                logger.info(f"Instagram DM sent to {user_id}")
    except Exception as e:
        logger.error(f"Instagram DM exception: {e}")


async def alert_agent(message: str):
    """إرسال تنبيه للأجون عبر WhatsApp"""
    if settings.AGENT_PHONE:
        await send_whatsapp(settings.AGENT_PHONE, f"🔔 تنبيه من النظام:\n{message}")
