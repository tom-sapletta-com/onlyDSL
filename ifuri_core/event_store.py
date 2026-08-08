from __future__ import annotations

import sqlite3
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Iterable

from onlydsl_contracts.ifuri import IfUri
from onlydsl_core.envelope import EnvelopeCodec, MessageKind


class EventStoreError(RuntimeError):
    pass


class ConcurrencyError(EventStoreError):
    pass


@dataclass(slots=True)
class OutboxItem:
    id: int
    event_id: str
    subject: str
    envelope_bytes: bytes
    attempts: int


class SqliteEventStore:
    """Reference authoritative ES adapter for tests/local POC.

    PostgresEventStore implements the same semantics for Docker/production-like use.
    """

    def __init__(self, path: str | Path = ":memory:") -> None:
        self.path = str(path)
        self.conn = sqlite3.connect(self.path, isolation_level=None, check_same_thread=False)
        self.conn.row_factory = sqlite3.Row
        self._init_schema()

    def _init_schema(self) -> None:
        self.conn.executescript(
            """
            PRAGMA journal_mode=WAL;
            CREATE TABLE IF NOT EXISTS event_streams (
              stream_id TEXT PRIMARY KEY,
              version INTEGER NOT NULL
            );
            CREATE TABLE IF NOT EXISTS events (
              stream_id TEXT NOT NULL,
              version INTEGER NOT NULL,
              event_id TEXT NOT NULL UNIQUE,
              event_uri TEXT NOT NULL,
              envelope BLOB NOT NULL,
              created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
              PRIMARY KEY (stream_id, version)
            );
            CREATE TABLE IF NOT EXISTS outbox (
              id INTEGER PRIMARY KEY AUTOINCREMENT,
              event_id TEXT NOT NULL UNIQUE,
              subject TEXT NOT NULL,
              envelope BLOB NOT NULL,
              attempts INTEGER NOT NULL DEFAULT 0,
              published_at TEXT NULL,
              last_error TEXT NOT NULL DEFAULT ''
            );
            """
        )

    def current_version(self, stream_id: str) -> int:
        row = self.conn.execute(
            "SELECT version FROM event_streams WHERE stream_id = ?", (stream_id,)
        ).fetchone()
        return int(row["version"]) if row else 0

    def append(self, stream_id: str, expected_version: int, events: Iterable[Any]) -> list[Any]:
        items = list(events)
        if not items:
            return []
        cur = self.conn.cursor()
        cur.execute("BEGIN IMMEDIATE")
        try:
            cur.execute(
                "INSERT OR IGNORE INTO event_streams(stream_id, version) VALUES (?, 0)",
                (stream_id,),
            )
            row = cur.execute(
                "SELECT version FROM event_streams WHERE stream_id = ?", (stream_id,)
            ).fetchone()
            current = int(row[0])
            if current != int(expected_version):
                raise ConcurrencyError(
                    f"stream {stream_id!r} expected version {expected_version}, current {current}"
                )
            stored: list[Any] = []
            version = current
            for env in items:
                EnvelopeCodec.validate(env)
                if MessageKind(env.kind) != MessageKind.EVENT:
                    raise EventStoreError("event store accepts only EVENT envelopes")
                version += 1
                copy = type(env)()
                copy.CopyFrom(env)
                copy.aggregate_id = copy.aggregate_id or stream_id
                copy.aggregate_version = version
                encoded = EnvelopeCodec.serialize(copy)
                subject = IfUri.parse(copy.target_uri).to_subject()
                cur.execute(
                    "INSERT INTO events(stream_id, version, event_id, event_uri, envelope) VALUES (?,?,?,?,?)",
                    (stream_id, version, copy.id, copy.target_uri, encoded),
                )
                cur.execute(
                    "INSERT INTO outbox(event_id, subject, envelope) VALUES (?,?,?)",
                    (copy.id, subject, encoded),
                )
                stored.append(copy)
            cur.execute(
                "UPDATE event_streams SET version = ? WHERE stream_id = ?", (version, stream_id)
            )
            cur.execute("COMMIT")
            return stored
        except Exception:
            cur.execute("ROLLBACK")
            raise

    def load_stream(self, stream_id: str, after_version: int = 0) -> list[Any]:
        rows = self.conn.execute(
            "SELECT envelope FROM events WHERE stream_id = ? AND version > ? ORDER BY version",
            (stream_id, int(after_version)),
        ).fetchall()
        return [EnvelopeCodec.parse(bytes(row["envelope"])) for row in rows]

    def pending_outbox(self, limit: int = 100) -> list[OutboxItem]:
        rows = self.conn.execute(
            """
            SELECT id, event_id, subject, envelope, attempts
            FROM outbox
            WHERE published_at IS NULL
            ORDER BY id
            LIMIT ?
            """,
            (int(limit),),
        ).fetchall()
        return [
            OutboxItem(int(r["id"]), r["event_id"], r["subject"], bytes(r["envelope"]), int(r["attempts"]))
            for r in rows
        ]

    def mark_outbox_published(self, item_id: int) -> None:
        self.conn.execute(
            "UPDATE outbox SET published_at = CURRENT_TIMESTAMP, last_error = '' WHERE id = ?",
            (int(item_id),),
        )

    def mark_outbox_failed(self, item_id: int, error: str) -> None:
        self.conn.execute(
            "UPDATE outbox SET attempts = attempts + 1, last_error = ? WHERE id = ?",
            (str(error)[:1000], int(item_id)),
        )

    def outbox_stats(self) -> dict[str, int]:
        row = self.conn.execute(
            "SELECT COUNT(*) total, SUM(CASE WHEN published_at IS NULL THEN 1 ELSE 0 END) pending FROM outbox"
        ).fetchone()
        return {"total": int(row["total"] or 0), "pending": int(row["pending"] or 0)}

    def close(self) -> None:
        self.conn.close()
