from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", env_file_encoding="utf-8")

    DATABASE_URL: str = "sqlite:///./chemrepro.db"
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
    ADMIN_SECRET_TOKEN: str = "change-this-before-production"

    LINKEDIN_CLIENT_ID: str = ""
    LINKEDIN_CLIENT_SECRET: str = ""
    LINKEDIN_REDIRECT_URI: str = "http://localhost:8000/auth/linkedin/callback"

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
