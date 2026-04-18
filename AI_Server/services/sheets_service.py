"""
خدمة Google Sheets — حفظ وقراءة البيانات
"""
import gspread
from google.oauth2.service_account import Credentials
from datetime import datetime
import logging
import json
import os
from config import settings

logger = logging.getLogger(__name__)

SCOPES = [
    "https://www.googleapis.com/auth/spreadsheets",
    "https://www.googleapis.com/auth/drive",
]

# أسماء الأوراق
SHEET_ORDERS    = "📦 الطلبات"
SHEET_PRODUCTS  = "🏷️ المنتجات"
SHEET_CUSTOMERS = "👤 العملاء"
SHEET_AI_LOG    = "🤖 سجل AI"


def _get_client():
    """إنشاء اتصال بـ Google Sheets"""
    creds_json = settings.GOOGLE_SERVICE_ACCOUNT_JSON
    if os.path.exists(creds_json):
        creds = Credentials.from_service_account_file(creds_json, scopes=SCOPES)
    else:
        # دعم JSON مباشر كـ environment variable
        creds = Credentials.from_service_account_info(json.loads(creds_json), scopes=SCOPES)
    return gspread.authorize(creds)


def _get_sheet(sheet_name: str):
    client = _get_client()
    spreadsheet = client.open_by_key(settings.GOOGLE_SHEETS_ID)
    return spreadsheet.worksheet(sheet_name)


def get_products_as_text() -> str:
    """جلب المنتجات كنص للـ Prompt"""
    try:
        ws = _get_sheet(SHEET_PRODUCTS)
        rows = ws.get_all_records()
        if not rows:
            return "لا توجد منتجات مضافة بعد."
        lines = []
        for r in rows:
            if str(r.get("متاح؟", "")).startswith("نعم"):
                lines.append(
                    f"- {r['اسم المنتج']} | السعر: {r['السعر (دج)']} دج | "
                    f"المتاح: {r['الأحجام/الألوان']} | الوصف: {r['الوصف']}"
                )
        return "\n".join(lines) if lines else "لا توجد منتجات متاحة حالياً."
    except Exception as e:
        logger.error(f"Sheets get_products error: {e}")
        return "خطأ في جلب المنتجات."


def _generate_order_id() -> str:
    from datetime import datetime
    return f"ORD-{datetime.now().strftime('%Y%m%d%H%M%S')}"


def add_order(order: dict) -> str:
    """إضافة طلب جديد وإرجاع رقم الطلب"""
    try:
        ws = _get_sheet(SHEET_ORDERS)
        order_id = _generate_order_id()
        now = datetime.now()
        row = [
            order_id,
            now.strftime("%Y-%m-%d"),
            now.strftime("%H:%M"),
            order.get("customer_name", ""),
            order.get("phone", ""),
            order.get("platform", ""),
            order.get("product", ""),
            order.get("quantity", 1),
            order.get("price", 0),
            order.get("quantity", 1) * order.get("price", 0),
            order.get("city", ""),
            order.get("address", ""),
            "في الانتظار ⏳",
            "لم يُرسل بعد",
            "",  # طريقة التأكيد
            "",  # الأجون
            "",  # ملاحظات AI
            "",  # تاريخ التسليم
            "",  # التقييم
        ]
        ws.append_row(row, value_input_option="USER_ENTERED")
        logger.info(f"Order added: {order_id}")
        return order_id
    except Exception as e:
        logger.error(f"Sheets add_order error: {e}")
        return ""


def update_order(order_id: str, updates: dict):
    """تحديث حقول طلب موجود"""
    col_map = {
        "حالة الطلب": 13,
        "حالة التوصيل": 14,
        "طريقة التأكيد": 15,
        "الأجون": 16,
        "ملاحظات AI": 17,
        "تاريخ التسليم": 18,
        "التقييم ⭐": 19,
    }
    try:
        ws = _get_sheet(SHEET_ORDERS)
        cell = ws.find(order_id, in_column=1)
        if not cell:
            logger.warning(f"Order {order_id} not found in sheets")
            return
        for field, value in updates.items():
            if field in col_map:
                ws.update_cell(cell.row, col_map[field], value)
        logger.info(f"Order {order_id} updated: {updates}")
    except Exception as e:
        logger.error(f"Sheets update_order error: {e}")


def get_pending_orders() -> list:
    """جلب الطلبات في الانتظار"""
    try:
        ws = _get_sheet(SHEET_ORDERS)
        rows = ws.get_all_records()
        return [r for r in rows if "الانتظار" in str(r.get("حالة الطلب", ""))]
    except Exception as e:
        logger.error(f"Sheets get_pending_orders error: {e}")
        return []


def get_confirmed_orders() -> list:
    """جلب الطلبات المؤكدة لتتبع التوصيل"""
    try:
        ws = _get_sheet(SHEET_ORDERS)
        rows = ws.get_all_records()
        return [r for r in rows if "مؤكد" in str(r.get("حالة الطلب", ""))]
    except Exception as e:
        logger.error(f"Sheets get_confirmed_orders error: {e}")
        return []


def get_delivered_orders_for_feedback() -> list:
    """جلب الطلبات المسلمة منذ 10+ أيام بدون تقييم"""
    from datetime import datetime, timedelta
    try:
        ws = _get_sheet(SHEET_ORDERS)
        rows = ws.get_all_records()
        result = []
        ten_days_ago = datetime.now() - timedelta(days=10)
        for r in rows:
            if "مُسلَّم" in str(r.get("حالة التوصيل", "")) and not r.get("التقييم ⭐"):
                delivery_date_str = str(r.get("تاريخ التسليم", ""))
                if delivery_date_str:
                    try:
                        delivery_date = datetime.strptime(delivery_date_str, "%Y-%m-%d")
                        if delivery_date <= ten_days_ago:
                            result.append(r)
                    except ValueError:
                        pass
        return result
    except Exception as e:
        logger.error(f"Sheets get_delivered_orders error: {e}")
        return []


def upsert_customer(phone: str, name: str, platform: str, city: str):
    """إضافة أو تحديث عميل"""
    try:
        ws = _get_sheet(SHEET_CUSTOMERS)
        rows = ws.get_all_records()
        phones = [str(r.get("رقم الهاتف", "")) for r in rows]
        if phone not in phones:
            client_id = f"CLT-{len(rows)+1:04d}"
            ws.append_row([client_id, name, phone, platform, city, 0, 0, datetime.now().strftime("%Y-%m-%d"), "عادي"])
    except Exception as e:
        logger.error(f"Sheets upsert_customer error: {e}")


def log_ai_interaction(phone: str, platform: str, message: str, reply: str, status: str):
    """تسجيل تفاعل في سجل AI"""
    try:
        ws = _get_sheet(SHEET_AI_LOG)
        ws.append_row([
            datetime.now().strftime("%Y-%m-%d %H:%M"),
            phone, platform, message, reply, status, ""
        ])
    except Exception as e:
        logger.error(f"Sheets log_ai error: {e}")
