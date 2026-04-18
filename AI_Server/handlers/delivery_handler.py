"""
الفلو 3: تتبع التوصيل وما بعد البيع
"""
import logging
from services.claude_service import ask_claude
from services.sheets_service import (
    get_confirmed_orders, get_delivered_orders_for_feedback,
    update_order, log_ai_interaction
)
from services.messaging_service import send_whatsapp, alert_agent
from prompts.all_prompts import get_delivery_prompt, get_feedback_prompt

logger = logging.getLogger(__name__)

# تتبع آخر حالة أُرسل إشعار لها
_notified_statuses: dict[str, str] = {}
# تتبع طلبات الفيدباك المرسلة
_feedback_sent: set = set()


async def check_and_notify_delivery_updates():
    """
    يُنفَّذ كل 30 دقيقة — يبحث عن تغييرات في حالة التوصيل
    """
    logger.info("Running delivery check...")
    orders = get_confirmed_orders()

    for order in orders:
        order_id       = str(order.get("Order ID", ""))
        phone          = str(order.get("رقم الهاتف", ""))
        customer_name  = str(order.get("اسم العميل", ""))
        product        = str(order.get("المنتج", ""))
        current_status = str(order.get("حالة التوصيل", ""))
        last_notified  = _notified_statuses.get(order_id, "")

        # أرسل إشعار فقط إذا تغيرت الحالة
        if current_status != last_notified and current_status not in ("لم يُرسل بعد", ""):
            system_prompt = get_delivery_prompt(customer_name, product, order_id, current_status)
            result = await ask_claude(system_prompt,
                                      f"الحالة: {current_status}", model="haiku")

            message = result.get("message", f"تحديث طلبك رقم {order_id}: {current_status}")
            image   = result.get("include_image", False)

            product_image_url = str(order.get("رابط_الصورة", "")) if image else None
            await send_whatsapp(phone, message,
                                image_url=product_image_url if product_image_url else None)

            _notified_statuses[order_id] = current_status

            # إذا تم التسليم، حفظ تاريخ التسليم
            if "مُسلَّم" in current_status:
                from datetime import date
                update_order(order_id, {"تاريخ التسليم": str(date.today())})

    logger.info(f"Delivery check done. Checked {len(orders)} orders.")


async def check_and_send_feedback_requests():
    """
    يُنفَّذ يومياً — يبحث عن طلبات مسلمة منذ 10+ أيام بدون تقييم
    """
    logger.info("Running feedback check...")
    orders = get_delivered_orders_for_feedback()

    for order in orders:
        order_id      = str(order.get("Order ID", ""))
        phone         = str(order.get("رقم الهاتف", ""))
        customer_name = str(order.get("اسم العميل", ""))
        product       = str(order.get("المنتج", ""))

        if order_id in _feedback_sent:
            continue

        message = (
            f"مرحباً {customer_name}! 😊\n"
            f"كيف وجدت منتجنا '{product}'؟\n"
            f"رأيك يهمنا كثيراً!\n\n"
            f"⭐ = سيء جداً\n"
            f"⭐⭐⭐ = متوسط\n"
            f"⭐⭐⭐⭐⭐ = ممتاز\n\n"
            f"شكراً لثقتك بنا 🙏"
        )
        await send_whatsapp(phone, message)
        _feedback_sent.add(order_id)
        update_order(order_id, {"ملاحظات AI": "تم إرسال طلب التقييم"})

    logger.info(f"Feedback check done. Sent {len(orders)} requests.")


async def process_feedback(sender_id: str, feedback_text: str, order_id: str):
    """معالجة رد التقييم من العميل"""
    # جلب اسم العميل والمنتج من الطلب
    orders = get_confirmed_orders()
    order = next((o for o in orders if str(o.get("Order ID", "")) == order_id), {})
    customer_name = str(order.get("اسم العميل", ""))
    product       = str(order.get("المنتج", ""))

    system_prompt = get_feedback_prompt(customer_name, product)
    result = await ask_claude(system_prompt, feedback_text, model="haiku")

    rating         = result.get("rating", 3)
    sentiment      = result.get("sentiment", "")
    needs_followup = result.get("needs_followup", False)
    summary        = result.get("summary", "")

    # حفظ التقييم
    stars = "⭐" * rating
    update_order(order_id, {
        "التقييم ⭐": stars,
        "ملاحظات AI": summary,
    })

    # شكر العميل
    thanks = (
        f"شكراً جزيلاً على تقييمك {stars} 🙏\n"
        "رأيك يساعدنا على التحسين المستمر!"
    )
    await send_whatsapp(sender_id, thanks)

    # تنبيه الأجون في حالة تقييم سلبي
    if needs_followup:
        await alert_agent(
            f"⚠️ تقييم سلبي!\n"
            f"العميل: {customer_name} ({sender_id})\n"
            f"المنتج: {product}\n"
            f"التقييم: {stars} ({rating}/5)\n"
            f"الملخص: {summary}\n"
            f"يحتاج متابعة فورية!"
        )

    log_ai_interaction(sender_id, "feedback", feedback_text, thanks, f"FEEDBACK_{rating}★")
