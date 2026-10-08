from pathlib import Path

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", env_file_encoding="utf-8", extra="ignore")

    output_dir: Path = Path("./out")
    log_level: str = "INFO"
    sinkhole_ip: str = "72.5.65.111"


settings = Settings()
settings.output_dir.mkdir(parents=True, exist_ok=True)
