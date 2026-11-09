"""Settings loaded from environment / .env (SPEC §14.3)."""
from functools import lru_cache

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=(".env", "../.env"), extra="ignore")

    app_env: str = "dev"
    app_base_url: str = "http://localhost:8000"
    web_base_url: str = "http://localhost:3000"
    jwt_secret: str = "change-me"
    database_url: str = "sqlite:///./briefpay_dev.db"
    database_ssl_ca: str | None = None

    paypal_env: str = "sandbox"
    paypal_client_id: str = ""
    paypal_client_secret: str = ""
    paypal_webhook_id: str = ""

    ai_provider: str = "replay_or_real"
    gemini_api_key: str = ""
    ai_model: str = ""
    github_token: str = ""

    image_provider: str = "local"
    cloudinary_url: str = ""
    local_images_dir: str = "./local_images"
    image_max_bytes: int = 5_000_000
    image_url_ttl_seconds: int = 300

    fee_reserve_per_item_cents: int = 0
    payout_max_cents: int = 100000
    payout_max_per_hour: int = 10
    pledge_max_hours: int = 72
    honor_safety_margin_hours: int = 2
    pledge_min_cents: int = 500
    default_close_policy: str = "EARLY_ON_GOAL"
    clock_interval_seconds: int = 60
    ba_target_score: int = 90
    ba_max_rounds: int = 5
    demo_mode: bool = True
    cors_origins: str = "http://localhost:3000"

    @property
    def cors_origin_list(self) -> list[str]:
        return [o.strip() for o in self.cors_origins.split(",") if o.strip()]


@lru_cache
def get_settings() -> Settings:
    return Settings()
