from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Protocol

from .event_store import OutboxItem
from .transport import NatsJetStream


class OutboxStore(Protocol):
    def pending_outbox(self, limit: int = 100) -> list[OutboxItem]: ...
    def mark_outbox_published(self, item_id: int) -> None: ...
    def mark_outbox_failed(self, item_id: int, error: str) -> None: ...


@dataclass(slots=True)
class PublishReport:
    published: int = 0
    failed: int = 0


class OutboxPublisher:
    def __init__(self, store: OutboxStore, jetstream: NatsJetStream):
        self.store = store
        self.jetstream = jetstream

    async def publish_once(self, limit: int = 100) -> PublishReport:
        report = PublishReport()
        for item in self.store.pending_outbox(limit):
            try:
                await self.jetstream.publish(item.subject, item.envelope_bytes)
                self.store.mark_outbox_published(item.id)
                report.published += 1
            except Exception as exc:
                self.store.mark_outbox_failed(item.id, f"{type(exc).__name__}: {exc}")
                report.failed += 1
        return report
