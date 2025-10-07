from pathlib import Path
from typing import Optional

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    """Application configuration loaded from env vars or defaults."""

    model_config = SettingsConfigDict(
        env_file=".env",
        case_sensitive=False,
        arbitrary_types_allowed=True,
    )

    base_dir: Path = Path(__file__).resolve().parents[2]
    data_dir: Path = base_dir / "data"
    upload_dir: Path = data_dir / "uploads"
    result_dir: Path = data_dir / "results"

    libreoffice_path: str = "soffice"
    poppler_path: Optional[Path] = None
    convert_timeout_seconds: int = 300
    worker_poll_interval: float = 2.0
    max_worker_threads: int = 2
    cleanup_hours: int = 24

    default_dpi: int = 144
    background_color_threshold: int = 235

    strapi_base_url: str = "http://localhost:1337"
    strapi_timeout_seconds: int = 5
    strapi_dev_tokens: dict[str, dict[str, object]] = {}


settings = Settings()
settings.data_dir.mkdir(parents=True, exist_ok=True)
settings.upload_dir.mkdir(parents=True, exist_ok=True)
settings.result_dir.mkdir(parents=True, exist_ok=True)
