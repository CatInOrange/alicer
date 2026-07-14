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
