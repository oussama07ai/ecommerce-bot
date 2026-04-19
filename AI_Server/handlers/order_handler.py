"""
الفلو 1: استقبال الرسائل والرد الذكي
"""
import logging
from services.claude_service import ask_claude
from services.shopify_service import get_shopify_products_as_text
from services.sheets_service import (
        add_order, upsert_customer, log_ai_interaction
)
from services.messaging_service import send_whatsapp, send_instagram_dm, alert_agent
from prompts.all_prompts import get_support_prompt
from config import settings

logger = logging.getLogger(__name__)

# حفظ سياق المحادثة مؤقتاً في الذاكرة
_conversation_state: dict[str, dict] = {}


async def handle_message(platform: str, sender_id: str, message_text: str,
                         sender_name: str = ""):
    """
    المدخل الرئيسي لمعالجة كل رسالة واردة
    platform: "whatsapp" أو "instagram"
    sender_id: رقم الهاتف أو Instagram user_id
    """
    logger.info(f"[{platform}] Message from {sender_id}: {message_text[:80]}")

    # تجاهل الرسائل الفارغة
    if not message_text or not message_text.strip():
        return

    # تحقق إذا هذا العميل في وضع تأكيد طلب → حوّل للـ confirmation handler
    state = _conversation_state.get(sender_id, {})
    if state.get("awaiting_confirmation"):
        from handlers.confirmation_handler import process_reply
        await process_reply(sender_id, message_text, platform, state.get("order_id"))
        return

    # تحقق إذا في وضع انتظار فيدباك
    if state.get("awaiting_feedback"):
        from handlers.delivery_handler import process_feedback
        await process_feedback(sender_id, message_text, state.get("order_id"))
        return

    # جلب المنتجات
        products_text = await get_shopify_products_as_text()

    # بناء الـ prompt
    system_prompt = get_support_prompt(settings.STORE_NAME, products_text)

    # سؤال Claude
    result = await ask_claude(system_prompt, message_text, model="haiku")
    status = result.get("status", "HANDOVER")
    reply  = result.get("reply", "سيتواصل معك أحد وكلائنا قريباً 🙏")

    # تسجيل في Google Sheets
    log_ai_interaction(sender_id, platform, message_text, reply, status)

    if status == "ANSWERED":
        await _send(platform, sender_id, reply)

    elif status == "ORDER":
        order_data = result.get("order", {})
        order_data["platform"] = platform

        # حفظ الطلب
        order_id = add_order(order_data)
        if order_id:
            upsert_customer(
                phone=order_data.get("phone", sender_id),
                name=order_data.get("customer_name", ""),
                platform=platform,
                city=order_data.get("city", ""),
            )
            # تأكيد للعميل
            await _send(platform, sender_id,
                        f"{reply}\nرقم طلبك: {order_id} 📋")

            # تسجيل الطلب في الـ state وانتظار تأكيده
            _conversation_state[sender_id] = {
                "awaiting_confirmation": True,
                "order_id": order_id,
                "order_data": order_data,
            }

            # إرسال رسالة تأكيد بعد 30 ثانية (عبر الـ scheduler)
            from handlers.confirmation_handler import schedule_confirmation
            await schedule_confirmation(
                phone=order_data.get("phone", sender_id),
                platform=platform,
                order_id=order_id,
                order_data=order_data,
            )
        else:
            await _send(platform, sender_id,
                        "حدث خطأ في تسجيل طلبك. سيتواصل معك فريقنا قريباً.")
            await alert_agent(f"فشل تسجيل طلب جديد!\nالعميل: {sender_id}\nالمنصة: {platform}")

    elif status == "HANDOVER":
        await _send(platform, sender_id, reply)
        await alert_agent(
            f"تحويل عميل للأجون!\n"
            f"المنصة: {platform}\n"
            f"المعرف: {sender_id}\n"
            f"الرسالة: {message_text[:100]}\n"
            f"السبب: {result.get('reason', '')}"
        )


async def _send(platform: str, sender_id: str, message: str):
    if platform == "whatsapp":
        await send_whatsapp(sender_id, message)
    elif platform == "instagram":
        await send_instagram_dm(sender_id, message)
