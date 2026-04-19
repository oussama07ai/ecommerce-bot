"""
خدمة Shopify - جلب المنتجات مباشرة من المتجر
يتجدد تلقائياً كل 5 دقائق
"""
import httpx
import logging
import time
import re
from config import settings

logger = logging.getLogger(__name__)

_cache: dict = {"text": None, "timestamp": 0}
CACHE_TTL = 300  # 5 دقائق


def _clean_html(html: str) -> str:
      if not html:
                return ""
            text = re.sub(r'<[^>]+>', ' ', html)
    text = re.sub(r'&[a-zA-Z]+;', ' ', text)
    text = re.sub(r'\s+', ' ', text).strip()
    return text[:200]


async def get_shopify_products_as_text() -> str:
      global _cache
    now = time.time()
    if _cache["text"] and (now - _cache["timestamp"]) < CACHE_TTL:
              return _cache["text"]

    store_url = settings.SHOPIFY_STORE_URL.rstrip("/")
    url = f"{store_url}/products.json?limit=250"

    try:
              async with httpx.AsyncClient(timeout=15) as client:
                            response = await client.get(url)
                            response.raise_for_status()

        products = response.json().get("products", [])
        if not products:
                      return "لا توجد منتجات متاحة حالياً."

        lines = []
        for p in products:
                      variants = p.get("variants", [])
                      if not variants:
                                        continue
                                    variant = variants[0]
            price = float(variant.get("price", 0))
            compare_price = variant.get("compare_at_price")
            if not variant.get("available", True):
                              continue
                          price_text = f"{price:.0f} دج"
            if compare_price and float(compare_price) > price:
                              price_text = f"{price:.0f} دج (بدلاً من {float(compare_price):.0f} دج)"
                          desc = _clean_html(p.get("body_html", ""))
            lines.append(f"- {p['title']} | السعر: {price_text} | الوصف: {desc}")

        result = "\n".join(lines) if lines else "لا توجد منتجات متاحة."
        _cache["text"] = result
        _cache["timestamp"] = now
        logger.info(f"Shopify: loaded {len(lines)} products")
        return result

except Exception as e:
        logger.error(f"Shopify error: {e}")
        if _cache["text"]:
                      return _cache["text"]
        return "خطأ في جلب المنتجات من المتجر."
