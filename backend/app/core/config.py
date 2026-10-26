from functools import lru_cache

from pydantic import Field, model_validator
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", env_file_encoding="utf-8", extra="ignore")

    app_env: str = "development"
    database_url: str = "sqlite:///./udyamai.db"
    cors_origins: str = "http://localhost:5173,http://127.0.0.1:5173"
    auth_secret_key: str = "dev-auth-secret-change-before-deployment"
    auth_access_token_minutes: int = Field(default=15, gt=0, le=60)
    auth_refresh_token_days: int = Field(default=30, gt=0, le=90)
    frontend_url: str = "http://localhost:5173"
    smtp_host: str = ""
    smtp_port: int = Field(default=587, ge=1, le=65535)
    smtp_username: str = ""
    smtp_password: str = ""
    smtp_from_email: str = ""
    merchant_tokens: str = '{"personal":"dev-personal-token","coconut":"dev-coconut-token","kirana":"dev-kirana-token"}'
    llm_base_url: str = "https://api.openai.com/v1"
    llm_api_key: str = ""
    llm_model: str = ""
    ai_timeout_seconds: float = Field(default=15, gt=0, le=60)
    ai_requests_per_minute: int = Field(default=20, gt=0, le=600)
    sarvam_api_key: str = ""
    sarvam_chat_model: str = "sarvam-105b"
    sarvam_stt_model: str = "saaras:v4"
    sarvam_tts_model: str = "bulbul:v4-flash"
    sarvam_tts_speaker: str = "shubh_enhi_ads"
    sarvam_tts_enabled: bool = True
    sarvam_max_audio_bytes: int = Field(default=5_000_000, gt=0, le=10_000_000)
    intelligence_change_threshold: float = Field(default=0.25, gt=0, le=1)
    max_request_bytes: int = Field(default=65_536, gt=0, le=1_048_576)

    @model_validator(mode="after")
    def validate_merchant_tokens(self):
        self.token_map
        if self.app_env.lower() == "production" and (
            len(self.auth_secret_key) < 32
            or self.auth_secret_key.startswith("dev-")
            or self.auth_secret_key == "dev-auth-secret-change-before-deployment"
        ):
            raise ValueError("Configure a unique AUTH_SECRET_KEY of at least 32 characters in production")
        return self

    @property
    def allowed_origins(self) -> list[str]:
        return [origin.strip() for origin in self.cors_origins.split(",") if origin.strip()]

    @property
    def token_map(self) -> dict[str, str]:
        import json

        try:
            value = json.loads(self.merchant_tokens)
        except json.JSONDecodeError as exc:
            raise ValueError("MERCHANT_TOKENS must be a JSON object") from exc
        if not isinstance(value, dict) or not all(isinstance(k, str) and isinstance(v, str) and v for k, v in value.items()):
            raise ValueError("MERCHANT_TOKENS must map merchant IDs to tokens")
        if len(set(value.values())) != len(value):
            raise ValueError("Configure a distinct bearer token for each merchant")
        return value


@lru_cache
def get_settings() -> Settings:
    return Settings()
