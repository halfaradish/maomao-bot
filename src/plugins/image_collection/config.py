from pathlib import Path

from pydantic_settings import BaseSettings, SettingsConfigDict


class Config(BaseSettings):
    """Plugin settings loaded from the NoneBot .env file."""

    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore",
    )

    image_collection_storage_dir: Path = Path("data/image_collection")
    image_collection_max_image_size_mb: int = 20
    image_collection_list_page_size: int = 10

    @property
    def images_dir(self) -> Path:
        return self.image_collection_storage_dir / "images"

    @property
    def database_path(self) -> Path:
        return self.image_collection_storage_dir / "image_collection.db"


plugin_config = Config()
