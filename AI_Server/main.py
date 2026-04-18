"""
السيرفر الرئيسي — نقطة دخول كل الطلبات
تشغيل: uvicorn main:app --host 0.0.0.0 --port 8000
"""
import logging
import asyncio
from contextlib import asynccontextmanager
from fastapi import FastAPI, Request, HTTPException, BackgroundTasks
from fastapi.responses import PlainTextResponse, JSONResponse
from apscheduler.schedulers.asyncio import AsyncIOScheduler
from handlers.order_handler import handle_message
from handlers.delivery_handler import (
    check_and_notify_delivery_updates,
    check_and_send_feedback_requests,
)
from config import settings

# ── Logging ──────────────────────────────────────
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
)
logger = logging.getLogger(__name__)

# ── Scheduler ────────────────────────────────────
scheduler = AsyncIOScheduler()


@asynccontextmanager
async def lifespan(app: FastAPI):
    # تشغيل المهام المجدولة عند بدء السيرفر
    scheduler.add_job(
        check_and_notify_delivery_updates,
        "interval", minutes=30,
        id="delivery_check"
    )
    scheduler.add_job(
        check_and_send_feedback_requests,
        "interval", hours=24,
        id="feedback_check"
    )
    scheduler.start()
    logger.info("✅ Scheduler started")
    yield
    scheduler.shutdown()


app = FastAPI(
    title="AI E-Commerce Server",
    description="سيرفر الأتمتة الكامل للتجارة الإلكترونية",
    lifespan=lifespan,
)


# ══════════════════════════════════════
#  WhatsApp Webhook
# ══════════════════════════════════════

@app.get("/webhook/whatsapp")
async def whatsapp_verify(request: Request):
    """Meta Webhook Verification"""
    params = dict(request.query_params)
    mode      = params.get("hub.mode")
    token     = params.get("hub.verify_token")
    challenge = params.get("hub.challenge")

    if mode == "subscribe" and token == settings.WHATSAPP_VERIFY_TOKEN:
        logger.info("WhatsApp webhook verified ✅")
        return PlainTextResponse(challenge)
    raise HTTPException(status_code=403, detail="Verification failed")


@app.post("/webhook/whatsapp")
async def whatsapp_incoming(request: Request, background_tasks: BackgroundTasks):
    """استقبال رسائل WhatsApp"""
    try:
        body = await request.json()
        logger.debug(f"WhatsApp payload: {str(body)[:300]}")

        for entry in body.get("entry", []):
            for change in entry.get("changes", []):
                value = change.get("value", {})
                messages = value.get("messages", [])
                contacts = value.get("contacts", [])

                for msg in messages:
                    msg_type = msg.get("type")
                    phone    = msg.get("from", "")
                    name     = contacts[0].get("profile", {}).get("name", "") if contacts else ""

                    if msg_type == "text":
                        text = msg["text"]["body"]
                    elif msg_type == "audio":
                        # رسائل صوتية — Claude يعتذر ويطلب نص
                        text = "[رسالة صوتية]"
                    elif msg_type == "image":
                        text = "[صورة]"
                    else:
                        continue

                    background_tasks.add_task(
                        handle_message, "whatsapp", phone, text, name
                    )

        return JSONResponse({"status": "ok"})
    except Exception as e:
        logger.error(f"WhatsApp webhook error: {e}")
        return JSONResponse({"status": "error"}, status_code=200)  # Meta يحتاج 200 دائماً


# ══════════════════════════════════════
#  Instagram Webhook
# ══════════════════════════════════════

@app.get("/webhook/instagram")
async def instagram_verify(request: Request):
    """Meta Instagram Webhook Verification"""
    params = dict(request.query_params)
    mode      = params.get("hub.mode")
    token     = params.get("hub.verify_token")
    challenge = params.get("hub.challenge")

    if mode == "subscribe" and token == settings.INSTAGRAM_VERIFY_TOKEN:
        logger.info("Instagram webhook verified ✅")
        return PlainTextResponse(challenge)
    raise HTTPException(status_code=403, detail="Verification failed")


@app.post("/webhook/instagram")
async def instagram_incoming(request: Request, background_tasks: BackgroundTasks):
    """استقبال رسائل Instagram DM"""
    try:
        body = await request.json()
        logger.debug(f"Instagram payload: {str(body)[:300]}")

        for entry in body.get("entry", []):
            for messaging in entry.get("messaging", []):
                sender_id = messaging.get("sender", {}).get("id", "")
                message   = messaging.get("message", {})
                text      = message.get("text", "")

                if text and sender_id:
                    background_tasks.add_task(
                        handle_message, "instagram", sender_id, text
                    )

        return JSONResponse({"status": "ok"})
    except Exception as e:
        logger.error(f"Instagram webhook error: {e}")
        return JSONResponse({"status": "error"}, status_code=200)


# ══════════════════════════════════════
#  Health Check
# ══════════════════════════════════════

@app.get("/")
async def root():
    return {
        "status": "running ✅",
        "store": settings.STORE_NAME,
        "version": "1.0.0",
    }


@app.get("/health")
async def health():
    return {"status": "healthy", "scheduler": scheduler.running}


@app.post("/trigger/delivery-check")
async def manual_delivery_check(background_tasks: BackgroundTasks):
    """تشغيل تحقق التوصيل يدوياً"""
    background_tasks.add_task(check_and_notify_delivery_updates)
    return {"message": "Delivery check started"}


@app.post("/trigger/feedback-check")
async def manual_feedback_check(background_tasks: BackgroundTasks):
    """تشغيل تحقق الفيدباك يدوياً"""
    background_tasks.add_task(check_and_send_feedback_requests)
    return {"message": "Feedback check started"}


# ── تشغيل محلي ───────────────────────────────────
if __name__ == "__main__":
    import uvicorn
    uvicorn.run("main:app", host="0.0.0.0", port=settings.PORT,
                reload=settings.DEBUG, log_level="info")
