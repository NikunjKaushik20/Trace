from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    # Database
    database_url: str = "sqlite+aiosqlite:///./trace.db"
    
    # Supabase (For Auth) — required, no defaults; app will fail to start if missing
    supabase_url: str
    supabase_key: str
    supabase_jwt_secret: str
    
    # Razorpay — required, no defaults
    razorpay_key_id: str
    razorpay_key_secret: str
    razorpay_webhook_secret: str
    
    # CORS
    cors_origins: str = "http://localhost:3000,http://localhost:8000,http://127.0.0.1:8000"
    
    # Rate Limits
    rate_limit_default: str = "60/minute"
    rate_limit_auth: str = "10/minute"
    rate_limit_events: str = "120/minute"
    rate_limit_benchmark: str = "5/minute"
    
    # Worker config
    celery_broker_url: str = "redis://localhost:6379/0"
    redis_url: str = "redis://localhost:6379/1"

    # x402 facilitator settlement webhook — optional. Empty means the
    # facilitator-verification rail isn't wired up yet; /v1/webhooks/x402
    # fails closed (503) rather than silently accepting unsigned events.
    x402_facilitator_webhook_secret: str = ""

    # Request timeout (seconds)
    request_timeout: int = 30

    # External API retry config
    external_api_max_retries: int = 3
    external_api_timeout: int = 10

    model_config = SettingsConfigDict(env_file=".env", env_file_encoding="utf-8", extra="ignore")

settings = Settings()
