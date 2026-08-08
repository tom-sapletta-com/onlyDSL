from __future__ import annotations

from abc import ABC, abstractmethod
from typing import Any, Callable, Generic, TypeVar


class AggregateRoot(ABC):
    """Minimal event-sourced aggregate base; domain state changes only by events."""

    def __init__(self, aggregate_id: str):
        self.aggregate_id = aggregate_id
        self.version = 0
        self._uncommitted: list[Any] = []

    @abstractmethod
    def apply(self, event: Any) -> None:
        ...

    def load_from_history(self, events: list[Any]) -> None:
        for event in events:
            self.apply(event)
            self.version = int(event.aggregate_version)
        self._uncommitted.clear()

    def raise_event(self, event: Any) -> None:
        self.apply(event)
        self._uncommitted.append(event)

    def pull_uncommitted(self) -> list[Any]:
        out = list(self._uncommitted)
        self._uncommitted.clear()
        return out


A = TypeVar("A", bound=AggregateRoot)


class AggregateRepository(Generic[A]):
    def __init__(self, store: Any, factory: Callable[[str], A]):
        self.store = store
        self.factory = factory

    def load(self, aggregate_id: str) -> A:
        aggregate = self.factory(aggregate_id)
        aggregate.load_from_history(self.store.load_stream(aggregate_id))
        return aggregate

    def save(self, aggregate: A) -> list[Any]:
        pending = aggregate.pull_uncommitted()
        if not pending:
            return []
        expected = aggregate.version
        stored = self.store.append(aggregate.aggregate_id, expected, pending)
        aggregate.version = expected + len(stored)
        return stored
