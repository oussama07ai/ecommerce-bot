"""
الفلو 2: تأكيد الطلب تلقائياً
"""
import asyncio
import logging
from services.claude_service import ask_claude
from services.sheets_service import update_order, get_pending_orders
from services.messaging_service import send_whatsapp, alert_agent
from prompts.all_prompts import get_confirmation_prompt
from config import settings

logger = logging.getLogger(__name__)

# تتبع الطلبات التي أُرسل لها تأكيد
_pending_confirmations: dict[str, dict] = {}


async def schedule_confirmation(phone: str, platform: str, order_id: str, order_data: dict):
    """جدولة إرسال رسالة التأكيد بعد 30 ثانية"""
    _pending_confirmations[order_id] = {
        "phone": phone,
        "platform": platform,
        "order_data": order_data,
        "attempts": 0,
    }
    await asyncio.sleep(30)
    await send_confirmation_message(order_id)


async def send_confirmation_message(order_id: str):
    """إرسال رسالة التأكيد الرسمية للعميل"""
    info = _pending_confirmations.get(order_id)
    if not info:
        return

    od = info["order_data"]
    total = od.get("quantity", 1) * od.get("price", 0)

    message = (
        f"مرحباً {od.get('customer_name', '')} 👋\n"
        f"طلبك رقم {order_id}\n"
        f"المنتج: {od.get('product', '')} ({od.get('quantity', 1)} قطعة)\n"
        f"القيمة: {total} دج\n"
        f"إلى: {od.get('city', '')} — {od.get('address', '')}\n\n"
        f"هل تأكد الطلب؟ اكتب: نعم ✅ أو لا ❌"
    )

    await send_whatsapp(info["phone"], message)
    info["attempts"] += 1
    info["awaiting_reply"] = True
    logger.info(f"Confirmation sent for {order_id}")


async def process_reply(sender_id: str, reply_text: str, platform: str, order_id: str):
    """معالجة رد العميل على رسالة التأكيد"""
    info = _pending_confirmations.get(order_id, {})
    od = info.get("order_data", {})

    system_prompt = get_confirmation_prompt(
        customer_name=od.get("customer_name", ""),
        order_id=order_id,
        product=od.get("product", ""),
        quantity=od.get("quantity", 1),
        total=od.get("quantity", 1) * od.get("price", 0),
        city=od.get("city", ""),
        address=od.get("address", ""),
    )

    result = await ask_claude(system_prompt, reply_text, model="haiku")
    status = result.get("status", "NO_ANSWER")
    reply  = result.get("reply")

    if status == "CONFIRMED":
        update_order(order_id, {"حالة الطلب": "مؤكد ✅", "حالة التوصيل": "قيد التوصيل 🚚"})
        if reply:
            await send_whatsapp(info.get("phone", sender_id), reply)
        _pending_confirmations.pop(order_id, None)
        logger.info(f"Order {order_id} CONFIRMED")

    elif status == "CANCELED":
        update_order(order_id, {"حالة الطلب": "ملغى ❌", "حالة التوصيل": "ملغى ❌"})
        if reply:
            await send_whatsapp(info.get("phone", sender_id), reply)
        _pending_confirmations.pop(order_id, None)
        logger.info(f"Order {order_id} CANCELED")

    elif status == "NO_ANSWER":
        attempts = info.get("attempts", 1)
        if attempts < 2:
            # متابعة بعد 15 دقيقة
            await asyncio.sleep(900)
            await send_whatsapp(
                info.get("phone", sender_id),
                "مرحباً مجدداً 😊 هل تريد تأكيد طلبك؟ اكتب نعم ✅ أو لا ❌"
            )
            info["attempts"] = 2
        else:
            # تنبيه الأجون بعد فشل المتابعة
            await alert_agent(
                f"🔔 عميل لم يرد على تأكيد الطلب!\n"
                f"👤 {od.get('customer_name', '')}\n"
                f"📞 {info.get('phone', sender_id)}\n"
                f"📦 {od.get('product', '')}\n"
                f"رقم الطلب: {order_id}"
            )
            update_order(order_id, {"ملاحظات AI": "لم يرد على التأكيد — بحاجة لمتابعة"})
