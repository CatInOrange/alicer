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

                CREATE TABLE IF NOT EXISTS scheduled_jobs (
                    job_key TEXT PRIMARY KEY,
                    ran_at REAL NOT NULL,
                    result_json TEXT NOT NULL DEFAULT '{}'
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
                    subject TEXT NOT NULL DEFAULT 'user',
                    content TEXT NOT NULL,
                    summary TEXT NOT NULL DEFAULT '',
                    tags_json TEXT NOT NULL DEFAULT '[]',
                    confidence REAL NOT NULL DEFAULT 0.7,
                    importance REAL NOT NULL DEFAULT 0.5,
                    status TEXT NOT NULL DEFAULT 'active',
                    enabled INTEGER NOT NULL DEFAULT 1,
                    pinned INTEGER NOT NULL DEFAULT 0,
                    sensitive INTEGER NOT NULL DEFAULT 0,
                    source_json TEXT NOT NULL DEFAULT '{}',
                    expires_at REAL,
                    last_used_at REAL,
                    created_at REAL NOT NULL,
                    updated_at REAL NOT NULL
                );
                CREATE TABLE IF NOT EXISTS memory_events (
                    id TEXT PRIMARY KEY,
                    memory_id TEXT NOT NULL,
                    action TEXT NOT NULL,
                    before_json TEXT NOT NULL DEFAULT '{}',
                    after_json TEXT NOT NULL DEFAULT '{}',
                    created_at REAL NOT NULL
                );
                CREATE INDEX IF NOT EXISTS idx_memory_events_memory
                ON memory_events(memory_id, created_at DESC);

                CREATE TABLE IF NOT EXISTS memory_queue (
                    message_id TEXT PRIMARY KEY,
                    role TEXT NOT NULL,
                    content TEXT NOT NULL,
                    trigger_type TEXT NOT NULL DEFAULT 'batch',
                    processed INTEGER NOT NULL DEFAULT 0,
                    created_at REAL NOT NULL,
                    processed_at REAL
                );
                CREATE INDEX IF NOT EXISTS idx_memory_queue_pending
                ON memory_queue(processed, created_at);

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

                CREATE TABLE IF NOT EXISTS rift_scenarios (
                    id TEXT PRIMARY KEY,
                    title TEXT NOT NULL,
                    genre TEXT NOT NULL,
                    surface_relation TEXT NOT NULL,
                    intensity TEXT NOT NULL,
                    user_role TEXT NOT NULL DEFAULT '',
                    ai_role TEXT NOT NULL DEFAULT '',
                    world_setting TEXT NOT NULL DEFAULT '',
                    core_conflict TEXT NOT NULL DEFAULT '',
                    status TEXT NOT NULL DEFAULT 'active',
                    turn_count INTEGER NOT NULL DEFAULT 0,
                    stats_json TEXT NOT NULL DEFAULT '{}',
                    summary TEXT NOT NULL DEFAULT '',
                    current_choices_json TEXT NOT NULL DEFAULT '[]',
                    hidden_json TEXT NOT NULL DEFAULT '{}',
                    ending_type TEXT NOT NULL DEFAULT '',
                    created_at REAL NOT NULL,
                    updated_at REAL NOT NULL
                );
                CREATE INDEX IF NOT EXISTS idx_rift_scenarios_updated
                ON rift_scenarios(updated_at DESC, id DESC);

                CREATE TABLE IF NOT EXISTS rift_events (
                    id TEXT PRIMARY KEY,
                    scenario_id TEXT NOT NULL,
                    turn_index INTEGER NOT NULL,
                    event_type TEXT NOT NULL,
                    choice_id TEXT NOT NULL DEFAULT '',
                    choice_text TEXT NOT NULL DEFAULT '',
                    scene_text TEXT NOT NULL DEFAULT '',
                    ai_dialogue TEXT NOT NULL DEFAULT '',
                    state_delta_json TEXT NOT NULL DEFAULT '{}',
                    created_at REAL NOT NULL,
                    FOREIGN KEY(scenario_id) REFERENCES rift_scenarios(id) ON DELETE CASCADE
                );
                CREATE INDEX IF NOT EXISTS idx_rift_events_scenario
                ON rift_events(scenario_id, turn_index, created_at, id);
                """
            )
            self._ensure_columns(
                conn,
                "memories",
                {
                    "subject": "TEXT NOT NULL DEFAULT 'user'",
                    "summary": "TEXT NOT NULL DEFAULT ''",
                    "confidence": "REAL NOT NULL DEFAULT 0.7",
                    "importance": "REAL NOT NULL DEFAULT 0.5",
                    "status": "TEXT NOT NULL DEFAULT 'active'",
                    "pinned": "INTEGER NOT NULL DEFAULT 0",
                    "sensitive": "INTEGER NOT NULL DEFAULT 0",
                    "source_json": "TEXT NOT NULL DEFAULT '{}'",
                    "expires_at": "REAL",
                    "last_used_at": "REAL",
                },
            )
            conn.execute(
                """
                CREATE INDEX IF NOT EXISTS idx_memories_status_kind
                ON memories(status, kind, enabled, importance DESC, updated_at DESC)
                """
            )

    def _ensure_columns(self, conn: sqlite3.Connection, table: str, columns: dict[str, str]) -> None:
        existing = {
            str(row["name"])
            for row in conn.execute(f"PRAGMA table_info({table})").fetchall()
        }
        for name, ddl in columns.items():
            if name not in existing:
                conn.execute(f"ALTER TABLE {table} ADD COLUMN {name} {ddl}")

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

    def get_scheduled_job(self, job_key: str) -> dict | None:
        with self.connect() as conn:
            row = conn.execute(
                "SELECT job_key, ran_at, result_json FROM scheduled_jobs WHERE job_key = ?",
                (job_key,),
            ).fetchone()
        if row is None:
            return None
        return {
            "jobKey": row["job_key"],
            "ranAt": row["ran_at"],
            "result": json.loads(row["result_json"] or "{}"),
        }

    def upsert_scheduled_job(self, *, job_key: str, result: dict) -> None:
        with self.connect() as conn:
            conn.execute(
                """
                INSERT OR REPLACE INTO scheduled_jobs(job_key, ran_at, result_json)
                VALUES(?, ?, ?)
                """,
                (job_key, time.time(), json.dumps(result, ensure_ascii=False)),
            )

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

    def list_memories(
        self,
        kind: str | None = None,
        limit: int = 30,
        *,
        status: str | None = "active",
        include_disabled: bool = False,
        query_text: str = "",
    ) -> list[dict]:
        query = "SELECT * FROM memories WHERE 1=1"
        params: list[object] = []
        if not include_disabled:
            query += " AND enabled = 1"
        if status and status != "all":
            query += " AND status = ?"
            params.append(status)
        if kind:
            query += " AND kind = ?"
            params.append(kind)
        if query_text.strip():
            query += " AND (content LIKE ? OR summary LIKE ? OR tags_json LIKE ?)"
            needle = f"%{query_text.strip()}%"
            params.extend([needle, needle, needle])
        query += " ORDER BY pinned DESC, importance DESC, updated_at DESC LIMIT ?"
        params.append(max(1, min(limit, 200)))
        with self.connect() as conn:
            rows = conn.execute(query, params).fetchall()
        return [self._memory_row(row) for row in rows]

    def get_memory(self, memory_id: str) -> dict | None:
        with self.connect() as conn:
            row = conn.execute("SELECT * FROM memories WHERE id = ?", (memory_id,)).fetchone()
        return self._memory_row(row) if row is not None else None

    def upsert_memory(
        self,
        *,
        memory_id: str,
        kind: str,
        content: str,
        subject: str = "user",
        summary: str = "",
        tags: list[str] | None = None,
        confidence: float = 0.7,
        importance: float = 0.5,
        status: str = "active",
        enabled: bool = True,
        pinned: bool = False,
        sensitive: bool = False,
        source: dict | None = None,
        expires_at: float | None = None,
    ) -> dict:
        now = time.time()
        existing = self.get_memory(memory_id)
        created_at = float((existing or {}).get("createdAt") or now)
        before = existing or {}
        with self.connect() as conn:
            conn.execute(
                """
                INSERT INTO memories(
                    id, kind, subject, content, summary, tags_json, confidence,
                    importance, status, enabled, pinned, sensitive, source_json,
                    expires_at, last_used_at, created_at, updated_at
                ) VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)
                ON CONFLICT(id) DO UPDATE SET
                    kind=excluded.kind,
                    subject=excluded.subject,
                    content=excluded.content,
                    summary=excluded.summary,
                    tags_json=excluded.tags_json,
                    confidence=excluded.confidence,
                    importance=excluded.importance,
                    status=excluded.status,
                    enabled=excluded.enabled,
                    pinned=excluded.pinned,
                    sensitive=excluded.sensitive,
                    source_json=excluded.source_json,
                    expires_at=excluded.expires_at,
                    updated_at=excluded.updated_at
                """,
                (
                    memory_id,
                    kind,
                    subject,
                    content,
                    summary,
                    json.dumps(tags or [], ensure_ascii=False),
                    max(0.0, min(1.0, float(confidence))),
                    max(0.0, min(1.0, float(importance))),
                    status,
                    1 if enabled else 0,
                    1 if pinned else 0,
                    1 if sensitive else 0,
                    json.dumps(source or {}, ensure_ascii=False),
                    expires_at,
                    (existing or {}).get("lastUsedAt"),
                    created_at,
                    now,
                ),
            )
        item = self.get_memory(memory_id) or {}
        self.add_memory_event(
            memory_id=memory_id,
            action="update" if existing else "create",
            before=before,
            after=item,
        )
        return item

    def update_memory(self, memory_id: str, updates: dict) -> dict | None:
        current = self.get_memory(memory_id)
        if current is None:
            return None
        next_item = {**current, **updates}
        return self.upsert_memory(
            memory_id=memory_id,
            kind=str(next_item.get("kind") or "fact"),
            subject=str(next_item.get("subject") or "user"),
            content=str(next_item.get("content") or ""),
            summary=str(next_item.get("summary") or ""),
            tags=[str(item) for item in (next_item.get("tags") or [])],
            confidence=float(next_item.get("confidence") or 0.7),
            importance=float(next_item.get("importance") or 0.5),
            status=str(next_item.get("status") or "active"),
            enabled=bool(next_item.get("enabled", True)),
            pinned=bool(next_item.get("pinned", False)),
            sensitive=bool(next_item.get("sensitive", False)),
            source=dict(next_item.get("source") or {}),
            expires_at=next_item.get("expiresAt"),
        )

    def add_memory_event(
        self,
        *,
        memory_id: str,
        action: str,
        before: dict | None = None,
        after: dict | None = None,
    ) -> None:
        with self.connect() as conn:
            conn.execute(
                """
                INSERT INTO memory_events(id, memory_id, action, before_json, after_json, created_at)
                VALUES(?,?,?,?,?,?)
                """,
                (
                    f"mev_{time.time_ns()}",
                    memory_id,
                    action,
                    json.dumps(before or {}, ensure_ascii=False),
                    json.dumps(after or {}, ensure_ascii=False),
                    time.time(),
                ),
            )

    def enqueue_memory_message(self, *, message_id: str, role: str, content: str, trigger_type: str) -> None:
        if not content.strip():
            return
        with self.connect() as conn:
            conn.execute(
                """
                INSERT OR IGNORE INTO memory_queue(message_id, role, content, trigger_type, processed, created_at)
                VALUES(?,?,?,?,0,?)
                """,
                (message_id, role, content, trigger_type, time.time()),
            )

    def list_pending_memory_queue(self, *, limit: int = 60) -> list[dict]:
        with self.connect() as conn:
            rows = conn.execute(
                """
                SELECT message_id, role, content, trigger_type, created_at
                FROM memory_queue
                WHERE processed = 0
                ORDER BY created_at ASC
                LIMIT ?
                """,
                (max(1, min(limit, 120)),),
            ).fetchall()
        return [
            {
                "messageId": row["message_id"],
                "role": row["role"],
                "content": row["content"],
                "triggerType": row["trigger_type"],
                "createdAt": row["created_at"],
            }
            for row in rows
        ]

    def count_pending_memory_queue(self) -> int:
        with self.connect() as conn:
            row = conn.execute("SELECT COUNT(*) AS count FROM memory_queue WHERE processed = 0").fetchone()
        return int(row["count"] if row else 0)

    def mark_memory_queue_processed(self, message_ids: list[str]) -> None:
        if not message_ids:
            return
        with self.connect() as conn:
            placeholders = ",".join("?" for _ in message_ids)
            conn.execute(
                f"UPDATE memory_queue SET processed = 1, processed_at = ? WHERE message_id IN ({placeholders})",
                [time.time(), *message_ids],
            )

    def mark_memories_used(self, memory_ids: list[str]) -> None:
        if not memory_ids:
            return
        with self.connect() as conn:
            placeholders = ",".join("?" for _ in memory_ids)
            conn.execute(
                f"UPDATE memories SET last_used_at = ? WHERE id IN ({placeholders})",
                [time.time(), *memory_ids],
            )

    def _memory_row(self, row: sqlite3.Row) -> dict:
        return {
            "id": row["id"],
            "kind": row["kind"],
            "subject": row["subject"],
            "content": row["content"],
            "summary": row["summary"],
            "tags": json.loads(row["tags_json"] or "[]"),
            "confidence": row["confidence"],
            "importance": row["importance"],
            "status": row["status"],
            "enabled": bool(row["enabled"]),
            "pinned": bool(row["pinned"]),
            "sensitive": bool(row["sensitive"]),
            "source": json.loads(row["source_json"] or "{}"),
            "expiresAt": row["expires_at"],
            "lastUsedAt": row["last_used_at"],
            "createdAt": row["created_at"],
            "updatedAt": row["updated_at"],
        }

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

    def list_rifts(self, *, limit: int = 50) -> list[dict]:
        with self.connect() as conn:
            rows = conn.execute(
                """
                SELECT *
                FROM rift_scenarios
                ORDER BY updated_at DESC, id DESC
                LIMIT ?
                """,
                (max(1, min(limit, 100)),),
            ).fetchall()
        return [self._rift_row(row) for row in rows]

    def get_rift(self, scenario_id: str) -> dict | None:
        with self.connect() as conn:
            row = conn.execute(
                "SELECT * FROM rift_scenarios WHERE id = ?",
                (scenario_id,),
            ).fetchone()
        return self._rift_row(row) if row is not None else None

    def add_rift(self, *, scenario_id: str, payload: dict) -> dict:
        now = time.time()
        with self.connect() as conn:
            conn.execute(
                """
                INSERT INTO rift_scenarios(
                    id, title, genre, surface_relation, intensity, user_role,
                    ai_role, world_setting, core_conflict, status, turn_count,
                    stats_json, summary, current_choices_json, hidden_json,
                    ending_type, created_at, updated_at
                ) VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)
                """,
                (
                    scenario_id,
                    payload.get("title") or "未命名裂隙",
                    payload.get("genre") or "",
                    payload.get("surfaceRelation") or "",
                    payload.get("intensity") or "",
                    payload.get("userRole") or "",
                    payload.get("aiRole") or "",
                    payload.get("worldSetting") or "",
                    payload.get("coreConflict") or "",
                    payload.get("status") or "active",
                    int(payload.get("turnCount") or 0),
                    json.dumps(payload.get("stats") or {}, ensure_ascii=False),
                    payload.get("summary") or "",
                    json.dumps(payload.get("currentChoices") or [], ensure_ascii=False),
                    json.dumps(payload.get("hidden") or {}, ensure_ascii=False),
                    payload.get("endingType") or "",
                    now,
                    now,
                ),
            )
        return self.get_rift(scenario_id) or {}

    def update_rift(self, scenario_id: str, updates: dict) -> dict | None:
        current = self.get_rift(scenario_id)
        if current is None:
            return None
        next_item = {**current, **updates}
        with self.connect() as conn:
            conn.execute(
                """
                UPDATE rift_scenarios
                SET title = ?, genre = ?, surface_relation = ?, intensity = ?,
                    user_role = ?, ai_role = ?, world_setting = ?,
                    core_conflict = ?, status = ?, turn_count = ?,
                    stats_json = ?, summary = ?, current_choices_json = ?,
                    ending_type = ?, updated_at = ?
                WHERE id = ?
                """,
                (
                    next_item.get("title") or "",
                    next_item.get("genre") or "",
                    next_item.get("surfaceRelation") or "",
                    next_item.get("intensity") or "",
                    next_item.get("userRole") or "",
                    next_item.get("aiRole") or "",
                    next_item.get("worldSetting") or "",
                    next_item.get("coreConflict") or "",
                    next_item.get("status") or "active",
                    int(next_item.get("turnCount") or 0),
                    json.dumps(next_item.get("stats") or {}, ensure_ascii=False),
                    next_item.get("summary") or "",
                    json.dumps(next_item.get("currentChoices") or [], ensure_ascii=False),
                    next_item.get("endingType") or "",
                    time.time(),
                    scenario_id,
                ),
            )
        return self.get_rift(scenario_id)

    def delete_rift(self, scenario_id: str) -> None:
        with self.connect() as conn:
            conn.execute("DELETE FROM rift_scenarios WHERE id = ?", (scenario_id,))

    def add_rift_event(
        self,
        *,
        event_id: str,
        scenario_id: str,
        turn_index: int,
        event_type: str,
        choice_id: str = "",
        choice_text: str = "",
        scene_text: str = "",
        ai_dialogue: str = "",
        state_delta: dict | None = None,
    ) -> dict:
        with self.connect() as conn:
            conn.execute(
                """
                INSERT INTO rift_events(
                    id, scenario_id, turn_index, event_type, choice_id,
                    choice_text, scene_text, ai_dialogue, state_delta_json,
                    created_at
                ) VALUES(?,?,?,?,?,?,?,?,?,?)
                """,
                (
                    event_id,
                    scenario_id,
                    turn_index,
                    event_type,
                    choice_id,
                    choice_text,
                    scene_text,
                    ai_dialogue,
                    json.dumps(state_delta or {}, ensure_ascii=False),
                    time.time(),
                ),
            )
        return self.get_rift_event(event_id) or {}

    def get_rift_event(self, event_id: str) -> dict | None:
        with self.connect() as conn:
            row = conn.execute("SELECT * FROM rift_events WHERE id = ?", (event_id,)).fetchone()
        return self._rift_event_row(row) if row is not None else None

    def list_rift_events(self, scenario_id: str, *, limit: int = 200) -> list[dict]:
        with self.connect() as conn:
            rows = conn.execute(
                """
                SELECT *
                FROM rift_events
                WHERE scenario_id = ?
                ORDER BY turn_index ASC, created_at ASC, id ASC
                LIMIT ?
                """,
                (scenario_id, max(1, min(limit, 300))),
            ).fetchall()
        return [self._rift_event_row(row) for row in rows]

    def _rift_row(self, row: sqlite3.Row) -> dict:
        return {
            "id": row["id"],
            "title": row["title"],
            "genre": row["genre"],
            "surfaceRelation": row["surface_relation"],
            "intensity": row["intensity"],
            "userRole": row["user_role"],
            "aiRole": row["ai_role"],
            "worldSetting": row["world_setting"],
            "coreConflict": row["core_conflict"],
            "status": row["status"],
            "turnCount": row["turn_count"],
            "stats": json.loads(row["stats_json"] or "{}"),
            "summary": row["summary"],
            "currentChoices": json.loads(row["current_choices_json"] or "[]"),
            "hidden": json.loads(row["hidden_json"] or "{}"),
            "endingType": row["ending_type"],
            "createdAt": row["created_at"],
            "updatedAt": row["updated_at"],
        }

    def _rift_event_row(self, row: sqlite3.Row) -> dict:
        return {
            "id": row["id"],
            "scenarioId": row["scenario_id"],
            "turnIndex": row["turn_index"],
            "eventType": row["event_type"],
            "choiceId": row["choice_id"],
            "choiceText": row["choice_text"],
            "sceneText": row["scene_text"],
            "aiDialogue": row["ai_dialogue"],
            "stateDelta": json.loads(row["state_delta_json"] or "{}"),
            "createdAt": row["created_at"],
        }


def uuid_like() -> str:
    return f"{int(time.time() * 1000):x}"
