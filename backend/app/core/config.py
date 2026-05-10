from pathlib import Path
from pydantic_settings import BaseSettings


class Settings(BaseSettings):
    APP_NAME: str = "Tablo"
    VERSION: str = "0.1.0"
    DEBUG: bool = False

    CORS_ORIGINS: list[str] = [
        "http://localhost:3000",
        "http://localhost:5173",
    ]

    UPLOAD_DIR: Path = Path("/tmp/tablo_uploads")
    MAX_UPLOAD_SIZE_MB: int = 50

    model_config = {
        "env_file": ".env",
        "env_file_encoding": "utf-8",
    }


settings = Settings()

# Ensure upload directory exists
settings.UPLOAD_DIR.mkdir(parents=True, exist_ok=True)