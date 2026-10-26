from pydantic import model_validator
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    database_url: str = "postgresql+psycopg://parkea:parkea@localhost:5432/parkea"
    jwt_secret_key: str = ""
    jwt_expire_minutes: int = 480
    cors_origins: str = "http://localhost:4200"

    model_config = SettingsConfigDict(env_file=".env", extra="ignore")

    @model_validator(mode="after")
    def validate_jwt_secret(self):
        if len(self.jwt_secret_key.encode()) < 32:
            raise ValueError("JWT_SECRET_KEY debe tener al menos 32 bytes; configura backend/.env")
        return self

    @property
    def allowed_origins(self) -> list[str]:
        return [origin.strip() for origin in self.cors_origins.split(",") if origin.strip()]


settings = Settings()
