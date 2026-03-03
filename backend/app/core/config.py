from pydantic_settings import BaseSettings, SettingsConfigDict

class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", extra="ignore")

    database_url: str
    jwt_secret: str
    jwt_algorithm: str = "HS256"
    access_token_expire_minutes: int = 60

    bootstrap_org_name: str = "Mi Escuela"
    bootstrap_branch_name: str = "Matriz"
    bootstrap_admin_email: str = "admin@escuela.com"
    bootstrap_admin_password: str = "Admin12345*"

    cors_origins: str = "http://localhost:5173"

settings = Settings()
