from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", env_file_encoding="utf-8")

    DATABASE_URL: str = "sqlite:///./chemrepro.db"
    PUBLIC_DATABASE_URL: str = ""
    SECRET_KEY: str = "dev-secret-change-in-production"

    ORCID_CLIENT_ID: str = ""
    ORCID_CLIENT_SECRET: str = ""
    ORCID_REDIRECT_URI: str = "http://localhost:8000/auth/callback"
    ORCID_ENV: str = "sandbox"  # "sandbox" or "production"

    GMAIL_ADDRESS: str = ""
    GMAIL_APP_PASSWORD: str = ""
    FEEDBACK_NOTIFY_EMAIL: str = ""

    ANTHROPIC_API_KEY: str = ""
    AUTHOR_NOTIFY_ENABLED: bool = False
    ADMIN_NOTIFY_ENABLED: bool = True
    ADMIN_SECRET_TOKEN: str = "change-this-before-production"
    SITE_URL: str = "http://127.0.0.1:8000"

    LINKEDIN_CLIENT_ID: str = ""
    LINKEDIN_CLIENT_SECRET: str = ""
    LINKEDIN_REDIRECT_URI: str = "http://localhost:8000/auth/linkedin/callback"

    RESEND_API_KEY: str = ""
    MAIL_FROM: str = "ChemRepro <noreply@chemrepro.org>"

    @property
    def orcid_base_url(self) -> str:
        if self.ORCID_ENV == "production":
            return "https://orcid.org"
        return "https://sandbox.orcid.org"

    @property
    def orcid_api_url(self) -> str:
        if self.ORCID_ENV == "production":
            return "https://api.orcid.org/v3.0"
        return "https://api.sandbox.orcid.org/v3.0"


settings = Settings()

if settings.ORCID_ENV == "production":
    _insecure = [
        name for name, value, default in (
            ("SECRET_KEY", settings.SECRET_KEY, "dev-secret-change-in-production"),
            ("ADMIN_SECRET_TOKEN", settings.ADMIN_SECRET_TOKEN, "change-this-before-production"),
        ) if not value or value == default
    ]
    if _insecure:
        raise RuntimeError(
            "Refusing to start in production with default or empty secrets: " + ", ".join(_insecure)
        )
