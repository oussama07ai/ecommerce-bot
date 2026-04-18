"""
إعدادات السيرفر — تُقرأ من ملف .env
"""
from pydantic_settings import BaseSettings
from functools import lru_cache


class Settings(BaseSettings):
    # ── اسم المتجر ──────────────────────────────
    STORE_NAME: str = "متجري"

    # ── Claude API ───────────────────────────────
    ANTHROPIC_API_KEY: str = ""

    # ── WhatsApp (Meta Cloud API) ────────────────
    WHATSAPP_ACCESS_TOKEN: str = ""
    WHATSAPP_PHONE_NUMBER_ID: str = ""
    WHATSAPP_VERIFY_TOKEN: str = "my_verify_token_2024"

    # ── Instagram (Meta Graph API) ───────────────
    INSTAGRAM_ACCESS_TOKEN: str = ""
    INSTAGRAM_VERIFY_TOKEN: str = "my_verify_token_2024"

    # ── Google Sheets ────────────────────────────
    GOOGLE_SHEETS_ID: str = ""
    # إما مسار الملف أو محتوى JSON مباشراً
    GOOGLE_SERVICE_ACCOUNT_JSON: str = "service_account.json"

    # ── رقم الأجون للتنبيهات ─────────────────────
    AGENT_PHONE: str = ""

    # ── السيرفر ──────────────────────────────────
    PORT: int = 8000
    DEBUG: bool = False

    class Config:
        env_file = ".env"
        env_file_encoding = "utf-8"
        extra = "ignore"


@lru_cache
def get_settings() -> Settings:
    return Settings()


settings = get_settings()
