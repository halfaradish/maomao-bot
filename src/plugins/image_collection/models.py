from dataclasses import dataclass
from datetime import datetime
from pathlib import Path


@dataclass(slots=True)
class ImageRecord:
    """A locally saved image and the metadata used to retrieve it."""

    id: str
    file_path: Path
    original_name: str | None
    extension: str
    file_hash: str
    size_bytes: int
    sender_qq: int
    created_at: datetime
    tags: tuple[str, ...] = ()
    description: str | None = None

    @property
    def formatted_tags(self) -> str:
        return ", ".join(self.tags) if self.tags else "无"
