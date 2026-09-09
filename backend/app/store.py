"""SQLite persistence for jobs, their items, and settings.

A job is one submission (one or more URLs with shared options); an item is one URL within it.
All access happens on the event-loop thread, so a single connection suffices.
"""

from __future__ import annotations

import json
import sqlite3
import time
import uuid
from dataclasses import asdict, dataclass, field, fields
from pathlib import Path
from typing import Any

SCHEMA = """
CREATE TABLE IF NOT EXISTS jobs (
    id TEXT PRIMARY KEY,
    created_at REAL NOT NULL,
    kind TEXT NOT NULL,
    options TEXT NOT NULL,
    archived INTEGER NOT NULL DEFAULT 0
);
CREATE TABLE IF NOT EXISTS items (
    id TEXT PRIMARY KEY,
    job_id TEXT NOT NULL REFERENCES jobs(id) ON DELETE CASCADE,
    position INTEGER NOT NULL,
    url TEXT NOT NULL,
    status TEXT NOT NULL,
    title TEXT,
    uploader TEXT,
    duration REAL,
    thumbnail TEXT,
    stage TEXT,
    downloaded INTEGER,
    total INTEGER,
    speed REAL,
    eta INTEGER,
    file_path TEXT,
    error TEXT,
    created_at REAL NOT NULL,
    started_at REAL,
    finished_at REAL,
    collection TEXT,
    collection_index INTEGER
);
CREATE INDEX IF NOT EXISTS items_job ON items(job_id, position);
CREATE INDEX IF NOT EXISTS items_status ON items(status);
CREATE TABLE IF NOT EXISTS settings (
    key TEXT PRIMARY KEY,
    value TEXT NOT NULL
);
"""

QUEUED, RUNNING, DONE, ERROR, CANCELLED = "queued", "running", "done", "error", "cancelled"
ACTIVE = (QUEUED, RUNNING)
RETRYABLE = (ERROR, CANCELLED)


@dataclass
class Item:
    id: str
    job_id: str
    position: int
    url: str
    status: str
    title: str | None = None
    uploader: str | None = None
    duration: float | None = None
    thumbnail: str | None = None
    stage: str | None = None
    downloaded: int | None = None
    total: int | None = None
    speed: float | None = None
    eta: int | None = None
    file_path: str | None = None
    error: str | None = None
    created_at: float = 0.0
    started_at: float | None = None
    finished_at: float | None = None
    collection: str | None = None  # playlist/album this came from -> its own folder
    collection_index: int | None = None  # 1-based position in that collection -> "01 - " prefix


# Columns added after the first release; older databases get them on open.
_ADDED_COLUMNS = (
    ("items", "collection", "TEXT"),
    ("items", "collection_index", "INTEGER"),
    (
        "jobs",
        "archived",
        "INTEGER NOT NULL DEFAULT 0",
    ),  # hidden from the board, kept in the library
)


@dataclass
class Job:
    id: str
    created_at: float
    kind: str
    options: dict[str, Any]
    items: list[Item] = field(default_factory=list)
    archived: bool = False

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


ITEM_COLUMNS = tuple(f.name for f in fields(Item))


@dataclass(frozen=True)
class NewItem:
    url: str
    title: str | None = None
    thumbnail: str | None = None
    collection: str | None = None
    collection_index: int | None = None


def new_id() -> str:
    return uuid.uuid4().hex[:12]


class Store:
    def __init__(self, path: Path | str) -> None:
        self.conn = sqlite3.connect(str(path), check_same_thread=False)
        self.conn.row_factory = sqlite3.Row
        self.conn.execute("PRAGMA journal_mode=WAL")
        self.conn.execute("PRAGMA foreign_keys=ON")
        self.conn.executescript(SCHEMA)
        self._migrate()

    def _migrate(self) -> None:
        with self.conn:
            for table, column, declaration in _ADDED_COLUMNS:
                existing = {row["name"] for row in self.conn.execute(f"PRAGMA table_info({table})")}
                if column not in existing:
                    self.conn.execute(f"ALTER TABLE {table} ADD COLUMN {column} {declaration}")

    def close(self) -> None:
        self.conn.close()

    # --- jobs ---

    def create_job(
        self, kind: str, options: dict[str, Any], items: list[NewItem] | list[str]
    ) -> Job:
        new_items = [NewItem(x) if isinstance(x, str) else x for x in items]
        job_id, now = new_id(), time.time()
        with self.conn:
            self.conn.execute(
                "INSERT INTO jobs (id, created_at, kind, options) VALUES (?, ?, ?, ?)",
                (job_id, now, kind, json.dumps(options)),
            )
            self.conn.executemany(
                "INSERT INTO items (id, job_id, position, url, status, title, thumbnail,"
                " created_at, collection, collection_index)"
                " VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
                [
                    (
                        new_id(),
                        job_id,
                        i,
                        it.url,
                        QUEUED,
                        it.title,
                        it.thumbnail,
                        now,
                        it.collection,
                        it.collection_index,
                    )
                    for i, it in enumerate(new_items)
                ],
            )
        job = self.get_job(job_id)
        assert job is not None
        return job

    def get_job(self, job_id: str) -> Job | None:
        row = self.conn.execute("SELECT * FROM jobs WHERE id = ?", (job_id,)).fetchone()
        return self._job(row) if row else None

    def list_jobs(self, limit: int = 50, include_archived: bool = False) -> list[Job]:
        where = "" if include_archived else "WHERE archived = 0"
        rows = self.conn.execute(
            f"SELECT * FROM jobs {where} ORDER BY created_at DESC LIMIT ?", (limit,)
        ).fetchall()
        return [self._job(row) for row in rows]

    def delete_job(self, job_id: str) -> None:
        with self.conn:
            self.conn.execute("DELETE FROM jobs WHERE id = ?", (job_id,))

    def archive_job(self, job_id: str) -> None:
        """Take a job off the board; its finished items stay in the library."""
        with self.conn:
            self.conn.execute("UPDATE jobs SET archived = 1 WHERE id = ?", (job_id,))

    def archive_finished(self) -> int:
        """Archive every job that has nothing queued or running; returns how many."""
        with self.conn:
            cur = self.conn.execute(
                "UPDATE jobs SET archived = 1 WHERE archived = 0 AND NOT EXISTS ("
                " SELECT 1 FROM items WHERE items.job_id = jobs.id AND items.status IN (?, ?))",
                (QUEUED, RUNNING),
            )
        return cur.rowcount

    # --- library: every finished item, regardless of archiving ---

    @staticmethod
    def _library_filter(query: str | None, collection: str | None) -> tuple[str, list[Any]]:
        where = "WHERE items.status = ?"
        params: list[Any] = [DONE]
        if query:
            where += " AND (items.title LIKE ? OR items.url LIKE ? OR items.collection LIKE ?)"
            params += [f"%{query}%"] * 3
        if collection is not None:
            where += " AND items.collection = ?"
            params.append(collection)
        return where, params

    def library(
        self,
        query: str | None = None,
        limit: int = 100,
        offset: int = 0,
        collection: str | None = None,
    ) -> list[dict]:
        """Finished downloads, newest first - or in playlist order inside one collection."""
        where, params = self._library_filter(query, collection)
        order = (
            "items.collection_index IS NULL, items.collection_index, items.finished_at DESC"
            if collection is not None
            else "items.finished_at DESC, items.position"
        )
        rows = self.conn.execute(
            f"SELECT items.*, jobs.kind AS job_kind, jobs.options AS job_options FROM items"
            f" JOIN jobs ON jobs.id = items.job_id {where} ORDER BY {order} LIMIT ? OFFSET ?",
            (*params, limit, offset),
        ).fetchall()
        return [
            {
                **asdict(_item(row)),
                "kind": row["job_kind"],
                "options": json.loads(row["job_options"]),
            }
            for row in rows
        ]

    def library_count(self, query: str | None = None, collection: str | None = None) -> int:
        where, params = self._library_filter(query, collection)
        return self.conn.execute(
            f"SELECT COUNT(*) FROM items JOIN jobs ON jobs.id = items.job_id {where}", params
        ).fetchone()[0]

    def collections(self) -> list[str]:
        """Folder names finished downloads are grouped in: playlists, albums, user-made groups."""
        rows = self.conn.execute(
            "SELECT DISTINCT collection FROM items WHERE status = ? AND collection IS NOT NULL"
            " ORDER BY collection COLLATE NOCASE",
            (DONE,),
        ).fetchall()
        return [row[0] for row in rows]

    def delete_item(self, item_id: str) -> None:
        """Forget one download; a job left with no items goes too."""
        with self.conn:
            row = self.conn.execute("SELECT job_id FROM items WHERE id = ?", (item_id,)).fetchone()
            if not row:
                return
            self.conn.execute("DELETE FROM items WHERE id = ?", (item_id,))
            self.conn.execute(
                "DELETE FROM jobs WHERE id = ? AND NOT EXISTS"
                " (SELECT 1 FROM items WHERE job_id = ?)",
                (row["job_id"], row["job_id"]),
            )

    def _job(self, row: sqlite3.Row) -> Job:
        items = self.conn.execute(
            "SELECT * FROM items WHERE job_id = ? ORDER BY position", (row["id"],)
        ).fetchall()
        return Job(
            id=row["id"],
            created_at=row["created_at"],
            kind=row["kind"],
            options=json.loads(row["options"]),
            items=[_item(r) for r in items],
            archived=bool(row["archived"]),
        )

    # --- items ---

    def get_item(self, item_id: str) -> Item | None:
        row = self.conn.execute("SELECT * FROM items WHERE id = ?", (item_id,)).fetchone()
        return _item(row) if row else None

    def items_with_status(self, *statuses: str) -> list[Item]:
        marks = ",".join("?" * len(statuses))
        rows = self.conn.execute(
            f"SELECT * FROM items WHERE status IN ({marks}) ORDER BY created_at, position",
            statuses,
        ).fetchall()
        return [_item(r) for r in rows]

    def update_item(self, item_id: str, **values: Any) -> None:
        unknown = set(values) - set(ITEM_COLUMNS)
        if unknown:
            raise ValueError(f"unknown item columns: {sorted(unknown)}")
        assignments = ", ".join(f"{k} = ?" for k in values)
        with self.conn:
            self.conn.execute(
                f"UPDATE items SET {assignments} WHERE id = ?", (*values.values(), item_id)
            )

    def claim_next_queued(self) -> Item | None:
        """Atomically move the oldest queued item to running."""
        with self.conn:
            row = self.conn.execute(
                "SELECT id FROM items WHERE status = ? ORDER BY created_at, position LIMIT 1",
                (QUEUED,),
            ).fetchone()
            if not row:
                return None
            self.conn.execute(
                "UPDATE items SET status = ?, started_at = ?, stage = ? WHERE id = ?",
                (RUNNING, time.time(), "Starting", row["id"]),
            )
        return self.get_item(row["id"])

    def count_with_status(self, status: str) -> int:
        return self.conn.execute(
            "SELECT COUNT(*) FROM items WHERE status = ?", (status,)
        ).fetchone()[0]

    def recover_interrupted(self) -> int:
        """Items left 'running' by a previous process (crash, quit) go back to the queue."""
        with self.conn:
            cur = self.conn.execute(
                "UPDATE items SET status = ?, stage = NULL, downloaded = NULL, total = NULL,"
                " speed = NULL, eta = NULL, started_at = NULL WHERE status = ?",
                (QUEUED, RUNNING),
            )
        return cur.rowcount

    # --- settings ---

    def get_setting(self, key: str) -> str | None:
        row = self.conn.execute("SELECT value FROM settings WHERE key = ?", (key,)).fetchone()
        return row["value"] if row else None

    def set_setting(self, key: str, value: str) -> None:
        with self.conn:
            self.conn.execute(
                "INSERT INTO settings (key, value) VALUES (?, ?)"
                " ON CONFLICT(key) DO UPDATE SET value = excluded.value",
                (key, value),
            )


def _item(row: sqlite3.Row) -> Item:
    return Item(**{column: row[column] for column in ITEM_COLUMNS})
