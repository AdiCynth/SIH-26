from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", extra="ignore")

    database_url: str = "postgresql+psycopg://vibeguard:vibeguard@localhost:5432/vibeguard"
    jwt_secret: str = "dev-secret-change-me"
    openai_api_key: str = ""
    openai_model: str = "gpt-4o-mini"
    github_client_id: str = ""
    github_client_secret: str = ""
    frontend_url: str = "http://localhost:3000"


settings = Settings()
