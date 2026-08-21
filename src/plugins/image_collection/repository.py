import sqlite3
from datetime import datetime
from pathlib import Path

from .models import ImageRecord


class ImageRepository:
    def __init__(self, database_path: Path) -> None:
        self.database_path = database_path

    def initialize(self) -> None:
        self.database_path.parent.mkdir(parents=True, exist_ok=True)
        with self._connect() as connection:
            connection.execute(
                """
                CREATE TABLE IF NOT EXISTS images (
                    id TEXT PRIMARY KEY,
                    file_path TEXT NOT NULL,
                    original_name TEXT,
                    extension TEXT NOT NULL,
                    file_hash TEXT NOT NULL UNIQUE,
                    size_bytes INTEGER NOT NULL,
                    sender_qq INTEGER NOT NULL,
                    created_at TEXT NOT NULL,
                    tags TEXT NOT NULL DEFAULT '',
                    description TEXT
                )
                """
            )
            connection.execute(
                "CREATE INDEX IF NOT EXISTS idx_images_created_at ON images(created_at DESC)"
            )

    def add(self, image: ImageRecord) -> None:
        with self._connect() as connection:
            connection.execute(
                """
                INSERT INTO images (
                    id, file_path, original_name, extension, file_hash, size_bytes,
                    sender_qq, created_at, tags, description
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    image.id,
                    str(image.file_path),
                    image.original_name,
                    image.extension,
                    image.file_hash,
                    image.size_bytes,
                    image.sender_qq,
                    image.created_at.isoformat(timespec="seconds"),
                    ",".join(image.tags),
                    image.description,
                ),
            )

    def get(self, image_id: str) -> ImageRecord | None:
        with self._connect() as connection:
            row = connection.execute("SELECT * FROM images WHERE id = ?", (image_id,)).fetchone()
        return self._record_from_row(row) if row else None

    def get_by_hash(self, file_hash: str) -> ImageRecord | None:
        with self._connect() as connection:
            row = connection.execute(
                "SELECT * FROM images WHERE file_hash = ?", (file_hash,)
            ).fetchone()
        return self._record_from_row(row) if row else None

    def list_recent(self, page: int, page_size: int) -> tuple[list[ImageRecord], int]:
        offset = (page - 1) * page_size
        with self._connect() as connection:
            total = connection.execute("SELECT COUNT(*) FROM images").fetchone()[0]
            rows = connection.execute(
                "SELECT * FROM images ORDER BY created_at DESC LIMIT ? OFFSET ?", (page_size, offset)
            ).fetchall()
        return [self._record_from_row(row) for row in rows], total

    def search(self, keyword: str, limit: int = 30) -> list[ImageRecord]:
        pattern = f"%{keyword}%"
        with self._connect() as connection:
            rows = connection.execute(
                """
                SELECT * FROM images
                WHERE id LIKE ? OR tags LIKE ? OR COALESCE(description, '') LIKE ?
                ORDER BY created_at DESC LIMIT ?
                """,
                (pattern, pattern, pattern, limit),
            ).fetchall()
        return [self._record_from_row(row) for row in rows]

    def update_tags(self, image_id: str, tags: tuple[str, ...]) -> bool:
        with self._connect() as connection:
            cursor = connection.execute(
                "UPDATE images SET tags = ? WHERE id = ?", (",".join(tags), image_id)
            )
        return cursor.rowcount > 0

    def delete(self, image_id: str) -> ImageRecord | None:
        image = self.get(image_id)
        if image is None:
            return None
        with self._connect() as connection:
            connection.execute("DELETE FROM images WHERE id = ?", (image_id,))
        return image

    def next_id(self) -> str:
        prefix = datetime.now().strftime("%Y%m%d")
        with self._connect() as connection:
            count = connection.execute(
                "SELECT COUNT(*) FROM images WHERE id LIKE ?", (f"{prefix}_%",)
            ).fetchone()[0]
        return f"{prefix}_{count + 1:03d}"

    def _connect(self) -> sqlite3.Connection:
        connection = sqlite3.connect(self.database_path)
        connection.row_factory = sqlite3.Row
        return connection

    @staticmethod
    def _record_from_row(row: sqlite3.Row) -> ImageRecord:
        tags = tuple(tag for tag in row["tags"].split(",") if tag)
        return ImageRecord(
            id=row["id"],
            file_path=Path(row["file_path"]),
            original_name=row["original_name"],
            extension=row["extension"],
            file_hash=row["file_hash"],
            size_bytes=row["size_bytes"],
            sender_qq=row["sender_qq"],
            created_at=datetime.fromisoformat(row["created_at"]),
            tags=tags,
            description=row["description"],
        )
