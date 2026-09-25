from pydantic_settings import BaseSettings
from pydantic import Field
from functools import lru_cache
from typing import Optional


class Settings(BaseSettings):
    APP_NAME: str = "GoldenYolk Farms - Cashback System"
    APP_ENV: str = "development"
    DEBUG: bool = True
    PORT: int = 8000
    HOST: str = "0.0.0.0"

    SECRET_KEY: str = "super-secret-egg-cashback-key-change-in-production"

    # Database
    DATABASE_URL: str = "sqlite:///./cashback.db"

    # Campaign
    DEFAULT_CASHBACK_AMOUNT: float = 20.0
    CAMPAIGN_NAME: str = "GoldenYolk Fresh Egg Tray Promotion"
    CAMPAIGN_ID: str = "CAMPAIGN_2026_EGG"
    DEFAULT_EXPIRY_DAYS: int = 30

    # OTP
    DEMO_MODE: bool = True
    OTP_EXPIRY_MINUTES: int = 5
    OTP_RESEND_COOLDOWN_SECONDS: int = 30
    MAX_OTP_ATTEMPTS: int = 5
    MAX_OTP_REQUESTS_PER_WINDOW: int = 3
    RATE_LIMIT_WINDOW_MINUTES: int = 10

    # SMS Provider
    SMS_API_KEY: Optional[str] = Field(None, alias="TWOFACTOR")

    # Front URL
    FRONTEND_BASE_URL: str = "http://localhost:5173"

    model_config = {
        "env_file": ".env",
        "env_file_encoding": "utf-8",
        "extra": "ignore"
    }


@lru_cache()
def get_settings() -> Settings:
    return Settings()
