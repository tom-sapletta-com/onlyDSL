"""Ports implemented by physical transport adapters outside onlydsl-core."""

from __future__ import annotations

from typing import Any, Protocol

from .capabilities import ResolvedCapability


class TransportError(RuntimeError):
    pass


class IfTransport(Protocol):
    name: str

    async def call(
        self, resolved: ResolvedCapability, envelope: Any, timeout: float = 2.0,
    ) -> Any:
        ...

    async def publish(
        self, resolved: ResolvedCapability, envelope: Any,
    ) -> dict[str, Any]:
        ...
