from __future__ import annotations

from typing import Any, Iterable

from .envelope import EnvelopeCodec, MessageKind
from .event_store import ConcurrencyError, EventStoreError, OutboxItem
from .uri import IfUri


SCHEMA_SQL = """
CREATE TABLE IF NOT EXISTS ifuri_event_streams (
  stream_id TEXT PRIMARY KEY,
  version BIGINT NOT NULL
);
CREATE TABLE IF NOT EXISTS ifuri_events (
  stream_id TEXT NOT NULL,
  version BIGINT NOT NULL,
  event_id TEXT NOT NULL UNIQUE,
  event_uri TEXT NOT NULL,
  envelope BYTEA NOT NULL,
  created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
  PRIMARY KEY (stream_id, version)
);
CREATE TABLE IF NOT EXISTS ifuri_outbox (
  id BIGSERIAL PRIMARY KEY,
  event_id TEXT NOT NULL UNIQUE,
  subject TEXT NOT NULL,
  envelope BYTEA NOT NULL,
  attempts INTEGER NOT NULL DEFAULT 0,
  published_at TIMESTAMPTZ NULL,
  last_error TEXT NOT NULL DEFAULT ''
);
CREATE INDEX IF NOT EXISTS ifuri_outbox_pending_idx
  ON ifuri_outbox(id) WHERE published_at IS NULL;
"""


class PostgresEventStore:
    """PostgreSQL authoritative event store + transactional outbox.

    `psycopg[binary]` is an optional runtime dependency installed in the Docker image.
    """

    def __init__(self, dsn: str) -> None:
        try:
            import psycopg
        except ImportError as exc:  # pragma: no cover - exercised by Docker integration
            raise RuntimeError("PostgresEventStore requires psycopg") from exc
        self.psycopg = psycopg
        self.conn = psycopg.connect(dsn, autocommit=True)
        with self.conn.transaction():
            with self.conn.cursor() as cur:
                for statement in SCHEMA_SQL.split(";"):
                    if statement.strip():
                        cur.execute(statement)

    def current_version(self, stream_id: str) -> int:
        with self.conn.cursor() as cur:
            cur.execute("SELECT version FROM ifuri_event_streams WHERE stream_id=%s", (stream_id,))
            row = cur.fetchone()
            return int(row[0]) if row else 0

    def append(self, stream_id: str, expected_version: int, events: Iterable[Any]) -> list[Any]:
        items = list(events)
        if not items:
            return []
        stored: list[Any] = []
        with self.conn.transaction():
            with self.conn.cursor() as cur:
                cur.execute(
                    "INSERT INTO ifuri_event_streams(stream_id, version) VALUES (%s,0) ON CONFLICT DO NOTHING",
                    (stream_id,),
                )
                cur.execute(
                    "SELECT version FROM ifuri_event_streams WHERE stream_id=%s FOR UPDATE", (stream_id,)
                )
                current = int(cur.fetchone()[0])
                if current != int(expected_version):
                    raise ConcurrencyError(
                        f"stream {stream_id!r} expected version {expected_version}, current {current}"
                    )
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
                        "INSERT INTO ifuri_events(stream_id,version,event_id,event_uri,envelope) VALUES (%s,%s,%s,%s,%s)",
                        (stream_id, version, copy.id, copy.target_uri, encoded),
                    )
                    cur.execute(
                        "INSERT INTO ifuri_outbox(event_id,subject,envelope) VALUES (%s,%s,%s)",
                        (copy.id, subject, encoded),
                    )
                    stored.append(copy)
                cur.execute(
                    "UPDATE ifuri_event_streams SET version=%s WHERE stream_id=%s", (version, stream_id)
                )
        return stored

    def load_stream(self, stream_id: str, after_version: int = 0) -> list[Any]:
        with self.conn.cursor() as cur:
            cur.execute(
                "SELECT envelope FROM ifuri_events WHERE stream_id=%s AND version>%s ORDER BY version",
                (stream_id, int(after_version)),
            )
            return [EnvelopeCodec.parse(bytes(row[0])) for row in cur.fetchall()]

    def pending_outbox(self, limit: int = 100) -> list[OutboxItem]:
        with self.conn.cursor() as cur:
            cur.execute(
                """
                SELECT id,event_id,subject,envelope,attempts
                FROM ifuri_outbox
                WHERE published_at IS NULL
                ORDER BY id
                LIMIT %s
                """,
                (int(limit),),
            )
            return [OutboxItem(int(r[0]), r[1], r[2], bytes(r[3]), int(r[4])) for r in cur.fetchall()]

    def mark_outbox_published(self, item_id: int) -> None:
        with self.conn.transaction():
            with self.conn.cursor() as cur:
                cur.execute(
                    "UPDATE ifuri_outbox SET published_at=now(), last_error='' WHERE id=%s", (int(item_id),)
                )

    def mark_outbox_failed(self, item_id: int, error: str) -> None:
        with self.conn.transaction():
            with self.conn.cursor() as cur:
                cur.execute(
                    "UPDATE ifuri_outbox SET attempts=attempts+1,last_error=%s WHERE id=%s",
                    (str(error)[:1000], int(item_id)),
                )

    def outbox_stats(self) -> dict[str, int]:
        with self.conn.cursor() as cur:
            cur.execute(
                "SELECT COUNT(*), COUNT(*) FILTER (WHERE published_at IS NULL) FROM ifuri_outbox"
            )
            row = cur.fetchone()
            return {"total": int(row[0]), "pending": int(row[1])}

    def close(self) -> None:
        self.conn.close()
