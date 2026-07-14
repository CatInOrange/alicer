from __future__ import annotations

import json
import sqlite3
import time
from contextlib import contextmanager
from pathlib import Path
from typing import Iterator


class Database:
    def __init__(self, path: Path) -> None:
        self.path = path

    @contextmanager
    def connect(self) -> Iterator[sqlite3.Connection]:
        conn = sqlite3.connect(self.path)
        conn.row_factory = sqlite3.Row
        try:
            conn.execute("PRAGMA journal_mode=WAL")
            conn.execute("PRAGMA foreign_keys=ON")
            yield conn
            conn.commit()
        finally:
            conn.close()

    def ensure_schema(self) -> None:
        with self.connect() as conn:
            conn.executescript(
                """
                CREATE TABLE IF NOT EXISTS app_settings (
                    id TEXT PRIMARY KEY,
                    json TEXT NOT NULL,
                    updated_at REAL NOT NULL
                );

                CREATE TABLE IF NOT EXISTS messages (
                    id TEXT PRIMARY KEY,
                    role TEXT NOT NULL,
                    content TEXT NOT NULL,
                    created_at REAL NOT NULL,
                    metadata_json TEXT NOT NULL DEFAULT '{}'
                );
                CREATE INDEX IF NOT EXISTS idx_messages_created ON messages(created_at, id);

                CREATE TABLE IF NOT EXISTS memories (
                    id TEXT PRIMARY KEY,
                    kind TEXT NOT NULL,
                    content TEXT NOT NULL,
                    tags_json TEXT NOT NULL DEFAULT '[]',
                    enabled INTEGER NOT NULL DEFAULT 1,
                    created_at REAL NOT NULL,
                    updated_at REAL NOT NULL
                );

                CREATE TABLE IF NOT EXISTS diary_entries (
                    id TEXT PRIMARY KEY,
                    kind TEXT NOT NULL,
                    period_key TEXT NOT NULL,
                    title TEXT NOT NULL DEFAULT '',
                    content TEXT NOT NULL DEFAULT '',
                    status TEXT NOT NULL,
                    source TEXT NOT NULL DEFAULT '',
                    summary_json TEXT NOT NULL DEFAULT '{}',
                    error TEXT NOT NULL DEFAULT '',
                    created_at REAL NOT NULL,
                    updated_at REAL NOT NULL,
                    generated_at REAL,
                    UNIQUE(kind, period_key)
                );
                CREATE INDEX IF NOT EXISTS idx_diary_entries_period
                ON diary_entries(kind, period_key DESC);

                CREATE TABLE IF NOT EXISTS moments (
                    id TEXT PRIMARY KEY,
                    author TEXT NOT NULL,
                    content TEXT NOT NULL,
                    image_url TEXT NOT NULL DEFAULT '',
                    image_prompt TEXT NOT NULL DEFAULT '',
                    created_at REAL NOT NULL,
                    metadata_json TEXT NOT NULL DEFAULT '{}'
                );
                CREATE INDEX IF NOT EXISTS idx_moments_created ON moments(created_at DESC, id DESC);

                CREATE TABLE IF NOT EXISTS moment_likes (
                    moment_id TEXT NOT NULL,
                    user_name TEXT NOT NULL,
                    created_at REAL NOT NULL,
                    PRIMARY KEY(moment_id, user_name)
                );

                CREATE TABLE IF NOT EXISTS moment_comments (
                    id TEXT PRIMARY KEY,
                    moment_id TEXT NOT NULL,
                    author TEXT NOT NULL,
                    content TEXT NOT NULL,
                    parent_id TEXT NOT NULL DEFAULT '',
                    created_at REAL NOT NULL
                );
                CREATE INDEX IF NOT EXISTS idx_moment_comments
                ON moment_comments(moment_id, created_at, id);
                """
            )

    def get_settings(self) -> dict | None:
        with self.connect() as conn:
            row = conn.execute("SELECT json FROM app_settings WHERE id = 'default'").fetchone()
        return json.loads(row["json"]) if row else None

    def save_settings(self, payload: dict) -> dict:
        now = time.time()
        with self.connect() as conn:
            conn.execute(
                """
                INSERT INTO app_settings(id, json, updated_at)
                VALUES('default', ?, ?)
                ON CONFLICT(id) DO UPDATE SET json=excluded.json, updated_at=excluded.updated_at
                """,
                (json.dumps(payload, ensure_ascii=False), now),
            )
        return payload

    def list_messages(self, limit: int = 80) -> list[dict]:
        with self.connect() as conn:
            rows = conn.execute(
                """
                SELECT id, role, content, created_at, metadata_json
                FROM messages
                ORDER BY created_at DESC, id DESC
                LIMIT ?
                """,
                (max(1, min(limit, 300)),),
            ).fetchall()
        items = [
            {
                "id": row["id"],
                "role": row["role"],
                "content": row["content"],
                "createdAt": row["created_at"],
                "metadata": json.loads(row["metadata_json"] or "{}"),
            }
            for row in rows
        ]
        return list(reversed(items))

    def add_message(self, *, message_id: str, role: str, content: str, metadata: dict | None = None) -> dict:
        now = time.time()
        item = {
            "id": message_id,
            "role": role,
            "content": content,
            "createdAt": now,
            "metadata": metadata or {},
        }
        with self.connect() as conn:
            conn.execute(
                """
                INSERT INTO messages(id, role, content, created_at, metadata_json)
                VALUES(?, ?, ?, ?, ?)
                """,
                (message_id, role, content, now, json.dumps(metadata or {}, ensure_ascii=False)),
            )
        return item

    def update_message(self, *, message_id: str, content: str, metadata: dict | None = None) -> dict | None:
        with self.connect() as conn:
            row = conn.execute(
                "SELECT metadata_json FROM messages WHERE id = ?",
                (message_id,),
            ).fetchone()
            if row is None:
                return None
            current_meta = json.loads(row["metadata_json"] or "{}")
            next_meta = metadata if metadata is not None else current_meta
            conn.execute(
                "UPDATE messages SET content = ?, metadata_json = ? WHERE id = ?",
                (content, json.dumps(next_meta, ensure_ascii=False), message_id),
            )
        return self.get_message(message_id)

    def get_message(self, message_id: str) -> dict | None:
        with self.connect() as conn:
            row = conn.execute(
                """
                SELECT id, role, content, created_at, metadata_json
                FROM messages
                WHERE id = ?
                """,
                (message_id,),
            ).fetchone()
        if row is None:
            return None
        return {
            "id": row["id"],
            "role": row["role"],
            "content": row["content"],
            "createdAt": row["created_at"],
            "metadata": json.loads(row["metadata_json"] or "{}"),
        }

    def list_memories(self, kind: str | None = None, limit: int = 30) -> list[dict]:
        query = "SELECT * FROM memories WHERE enabled = 1"
        params: list[object] = []
        if kind:
            query += " AND kind = ?"
            params.append(kind)
        query += " ORDER BY updated_at DESC LIMIT ?"
        params.append(max(1, min(limit, 100)))
        with self.connect() as conn:
            rows = conn.execute(query, params).fetchall()
        return [
            {
                "id": row["id"],
                "kind": row["kind"],
                "content": row["content"],
                "tags": json.loads(row["tags_json"] or "[]"),
                "enabled": bool(row["enabled"]),
                "createdAt": row["created_at"],
                "updatedAt": row["updated_at"],
            }
            for row in rows
        ]

    def list_diary_entries(self, *, kind: str = "day", limit: int = 60) -> list[dict]:
        with self.connect() as conn:
            rows = conn.execute(
                """
                SELECT *
                FROM diary_entries
                WHERE kind = ?
                ORDER BY period_key DESC
                LIMIT ?
                """,
                (kind, max(1, min(limit, 200))),
            ).fetchall()
        return [self._diary_row(row) for row in rows]

    def get_diary_entry(self, *, kind: str, period_key: str) -> dict | None:
        with self.connect() as conn:
            row = conn.execute(
                "SELECT * FROM diary_entries WHERE kind = ? AND period_key = ?",
                (kind, period_key),
            ).fetchone()
        return self._diary_row(row) if row is not None else None

    def upsert_diary_entry(
        self,
        *,
        kind: str,
        period_key: str,
        title: str = "",
        content: str = "",
        status: str,
        source: str = "",
        summary: dict | None = None,
        error: str = "",
        generated_at: float | None = None,
    ) -> dict:
        now = time.time()
        existing = self.get_diary_entry(kind=kind, period_key=period_key)
        entry_id = str((existing or {}).get("id") or f"diary_{uuid_like()}")
        created_at = float((existing or {}).get("createdAt") or now)
        with self.connect() as conn:
            conn.execute(
                """
                INSERT INTO diary_entries(
                    id, kind, period_key, title, content, status, source,
                    summary_json, error, created_at, updated_at, generated_at
                ) VALUES(?,?,?,?,?,?,?,?,?,?,?,?)
                ON CONFLICT(kind, period_key) DO UPDATE SET
                    title=excluded.title,
                    content=excluded.content,
                    status=excluded.status,
                    source=excluded.source,
                    summary_json=excluded.summary_json,
                    error=excluded.error,
                    updated_at=excluded.updated_at,
                    generated_at=excluded.generated_at
                """,
                (
                    entry_id,
                    kind,
                    period_key,
                    title,
                    content,
                    status,
                    source,
                    json.dumps(summary or {}, ensure_ascii=False),
                    error,
                    created_at,
                    now,
                    generated_at,
                ),
            )
        return self.get_diary_entry(kind=kind, period_key=period_key) or {}

    def _diary_row(self, row: sqlite3.Row) -> dict:
        return {
            "id": row["id"],
            "kind": row["kind"],
            "periodKey": row["period_key"],
            "title": row["title"],
            "content": row["content"],
            "status": row["status"],
            "source": row["source"],
            "summary": json.loads(row["summary_json"] or "{}"),
            "error": row["error"],
            "createdAt": row["created_at"],
            "updatedAt": row["updated_at"],
            "generatedAt": row["generated_at"],
        }

    def list_moments(self, *, limit: int = 50) -> list[dict]:
        with self.connect() as conn:
            rows = conn.execute(
                """
                SELECT *
                FROM moments
                ORDER BY created_at DESC, id DESC
                LIMIT ?
                """,
                (max(1, min(limit, 100)),),
            ).fetchall()
            moment_ids = [row["id"] for row in rows]
            likes: dict[str, list[str]] = {item: [] for item in moment_ids}
            comments: dict[str, list[dict]] = {item: [] for item in moment_ids}
            if moment_ids:
                placeholders = ",".join("?" for _ in moment_ids)
                for row in conn.execute(
                    f"SELECT moment_id, user_name FROM moment_likes WHERE moment_id IN ({placeholders}) ORDER BY created_at ASC",
                    moment_ids,
                ).fetchall():
                    likes[row["moment_id"]].append(row["user_name"])
                for row in conn.execute(
                    f"SELECT * FROM moment_comments WHERE moment_id IN ({placeholders}) ORDER BY created_at ASC, id ASC",
                    moment_ids,
                ).fetchall():
                    comments[row["moment_id"]].append(
                        {
                            "id": row["id"],
                            "momentId": row["moment_id"],
                            "author": row["author"],
                            "content": row["content"],
                            "parentId": row["parent_id"],
                            "createdAt": row["created_at"],
                        }
                    )
        return [
            {
                "id": row["id"],
                "author": row["author"],
                "content": row["content"],
                "imageUrl": row["image_url"],
                "imagePrompt": row["image_prompt"],
                "createdAt": row["created_at"],
                "metadata": json.loads(row["metadata_json"] or "{}"),
                "likes": likes.get(row["id"], []),
                "comments": comments.get(row["id"], []),
            }
            for row in rows
        ]

    def add_moment(
        self,
        *,
        moment_id: str,
        author: str,
        content: str,
        image_url: str = "",
        image_prompt: str = "",
        metadata: dict | None = None,
    ) -> dict:
        now = time.time()
        with self.connect() as conn:
            conn.execute(
                """
                INSERT INTO moments(id, author, content, image_url, image_prompt, created_at, metadata_json)
                VALUES(?,?,?,?,?,?,?)
                """,
                (
                    moment_id,
                    author,
                    content,
                    image_url,
                    image_prompt,
                    now,
                    json.dumps(metadata or {}, ensure_ascii=False),
                ),
            )
        return self.get_moment(moment_id) or {}

    def get_moment(self, moment_id: str) -> dict | None:
        return next((item for item in self.list_moments(limit=100) if item["id"] == moment_id), None)

    def set_moment_like(self, *, moment_id: str, user_name: str, liked: bool) -> dict | None:
        with self.connect() as conn:
            if liked:
                conn.execute(
                    """
                    INSERT OR IGNORE INTO moment_likes(moment_id, user_name, created_at)
                    VALUES(?,?,?)
                    """,
                    (moment_id, user_name, time.time()),
                )
            else:
                conn.execute(
                    "DELETE FROM moment_likes WHERE moment_id = ? AND user_name = ?",
                    (moment_id, user_name),
                )
        return self.get_moment(moment_id)

    def add_moment_comment(
        self,
        *,
        comment_id: str,
        moment_id: str,
        author: str,
        content: str,
        parent_id: str = "",
    ) -> dict | None:
        with self.connect() as conn:
            conn.execute(
                """
                INSERT INTO moment_comments(id, moment_id, author, content, parent_id, created_at)
                VALUES(?,?,?,?,?,?)
                """,
                (comment_id, moment_id, author, content, parent_id, time.time()),
            )
        return self.get_moment(moment_id)


def uuid_like() -> str:
    return f"{int(time.time() * 1000):x}"
