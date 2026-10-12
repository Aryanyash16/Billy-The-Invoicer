from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", extra="ignore")

    database_url: str = "sqlite:///./invoice_ai.db"
    groq_api_key: str | None = None
    groq_model: str = "openai/gpt-oss-120b"
    auto_approve_min_score: float = 0.99
    auto_approval_enabled: bool = False

    quickbooks_env: str = "sandbox"
    quickbooks_client_id: str | None = None
    quickbooks_client_secret: str | None = None
    quickbooks_realm_id: str | None = None
    quickbooks_access_token: str | None = None
    quickbooks_refresh_token: str | None = None
    quickbooks_redirect_uri: str = "http://localhost:8000/integrations/quickbooks/callback"


settings = Settings()
