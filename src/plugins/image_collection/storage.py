import hashlib
from datetime import datetime
from pathlib import Path
from urllib.parse import urlparse

import httpx

from .config import Config
from .models import ImageRecord
from .repository import ImageRepository

_ALLOWED_EXTENSIONS = {"jpg", "jpeg", "png", "gif", "webp", "bmp"}
_CONTENT_TYPE_EXTENSIONS = {
    "image/jpeg": "jpg",
    "image/png": "png",
    "image/gif": "gif",
    "image/webp": "webp",
    "image/bmp": "bmp",
}


class ImageStorageService:
    def __init__(self, config: Config, repository: ImageRepository) -> None:
        self.config = config
        self.repository = repository

    async def save_from_url(
        self, url: str, sender_qq: int, original_name: str | None = None
    ) -> tuple[ImageRecord, bool]:
        content, content_type = await self._download(url)
        file_hash = hashlib.sha256(content).hexdigest()
        existing = self.repository.get_by_hash(file_hash)
        if existing:
            return existing, False

        extension = self._determine_extension(url, content_type, original_name)
        image_id = self.repository.next_id()
        destination = self.config.images_dir / f"{image_id}.{extension}"
        self.config.images_dir.mkdir(parents=True, exist_ok=True)
        destination.write_bytes(content)

        image = ImageRecord(
            id=image_id,
            file_path=destination.resolve(),
            original_name=original_name,
            extension=extension,
            file_hash=file_hash,
            size_bytes=len(content),
            sender_qq=sender_qq,
            created_at=datetime.now(),
        )
        try:
            self.repository.add(image)
        except Exception:
            destination.unlink(missing_ok=True)
            raise
        return image, True

    def remove(self, image: ImageRecord) -> None:
        deleted = self.repository.delete(image.id)
        if deleted:
            deleted.file_path.unlink(missing_ok=True)

    async def _download(self, url: str) -> tuple[bytes, str]:
        max_size = self.config.image_collection_max_image_size_mb * 1024 * 1024
        timeout = httpx.Timeout(30.0, connect=10.0)
        async with httpx.AsyncClient(timeout=timeout, follow_redirects=True) as client:
            async with client.stream("GET", url) as response:
                response.raise_for_status()
                declared_size = int(response.headers.get("content-length", "0"))
                if declared_size > max_size:
                    raise ValueError(f"图片超过 {self.config.image_collection_max_image_size_mb} MB 限制")
                chunks: list[bytes] = []
                received_size = 0
                async for chunk in response.aiter_bytes():
                    received_size += len(chunk)
                    if received_size > max_size:
                        raise ValueError(f"图片超过 {self.config.image_collection_max_image_size_mb} MB 限制")
                    chunks.append(chunk)
        content_type = response.headers.get("content-type", "").split(";", 1)[0].lower()
        return b"".join(chunks), content_type

    @staticmethod
    def _determine_extension(url: str, content_type: str, original_name: str | None) -> str:
        for value in (original_name, urlparse(url).path):
            suffix = Path(value).suffix.lower().lstrip(".")
            if suffix in _ALLOWED_EXTENSIONS:
                return "jpg" if suffix == "jpeg" else suffix
        if content_type in _CONTENT_TYPE_EXTENSIONS:
            return _CONTENT_TYPE_EXTENSIONS[content_type]
        raise ValueError("只支持 jpg、png、gif、webp 或 bmp 格式的图片")
