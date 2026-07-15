import hashlib
import logging
import sqlite3
from pathlib import Path

logger = logging.getLogger(__name__)


class SegmentCache:
    """SQLite cache for LLM segment classifications."""

    def __init__(self, db_path: Path) -> None:
        self.db_path = db_path
        self.db_path.parent.mkdir(parents=True, exist_ok=True)
        self._init_db()

    def _init_db(self) -> None:
        with sqlite3.connect(self.db_path) as conn:
            conn.execute(
                """
                CREATE TABLE IF NOT EXISTS segment_cache (
                    content_hash TEXT PRIMARY KEY,
                    product_id TEXT NOT NULL,
                    segment TEXT NOT NULL,
                    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
                )
                """
            )
            conn.commit()

    @staticmethod
    def _hash(name: str, description: str) -> str:
        content = f"{name}|{description}"
        return hashlib.sha256(content.encode()).hexdigest()

    def get(self, product_id: str, name: str, description: str) -> str | None:
        content_hash = self._hash(name, description)
        with sqlite3.connect(self.db_path) as conn:
            row = conn.execute(
                "SELECT segment FROM segment_cache WHERE content_hash = ?",
                (content_hash,),
            ).fetchone()
        return row[0] if row else None

    def set(self, product_id: str, name: str, description: str, segment: str) -> None:
        content_hash = self._hash(name, description)
        with sqlite3.connect(self.db_path) as conn:
            conn.execute(
                """
                INSERT OR REPLACE INTO segment_cache (content_hash, product_id, segment)
                VALUES (?, ?, ?)
                """,
                (content_hash, product_id, segment),
            )
            conn.commit()
