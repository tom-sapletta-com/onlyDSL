from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from google.protobuf.message import Message

from .envelope import EnvelopeCodec, MessageKind
from .manifest import CapabilityRegistry, ResolvedCapability
from .transport import IfTransport, TransportError


class RuntimeErrorIfuri(RuntimeError):
    pass


@dataclass(slots=True)
class RouteDecision:
    uri: str
    capability_id: str
    runtime: str
    params: dict[str, str]
    transport_order: list[str]
    attempted: list[dict[str, str]]
    selected_transport: str = ""

    def to_dict(self) -> dict[str, Any]:
        return {
            "uri": self.uri,
            "capability_id": self.capability_id,
            "runtime": self.runtime,
            "params": dict(self.params),
            "transport_order": list(self.transport_order),
            "attempted": list(self.attempted),
            "selected_transport": self.selected_transport,
        }


class IfuriRuntime:
    """Deterministic URI resolver + transport dispatcher.

    Domain code sees only logical URI + protobuf payload. Host/port and transport
    selection are delegated to the manifest and transport adapters.
    """

    def __init__(self, registry: CapabilityRegistry, transports: dict[str, IfTransport]):
        self.registry = registry
        self.transports = dict(transports)

    def inspect_route(self, uri: str) -> dict[str, Any]:
        return self.registry.explain(uri)

    async def call(
        self,
        target_uri: str,
        payload: Message | None,
        *,
        source_uri: str = "ifuri://system/client/default/commands/call",
        correlation_id: str = "",
        timeout: float = 2.0,
        metadata: dict[str, str] | None = None,
    ) -> tuple[Any, RouteDecision]:
        resolved = self.registry.resolve(target_uri)
        capability = resolved.capability
        if capability.message_kind not in {"command", "query"}:
            raise RuntimeErrorIfuri(f"call() requires command/query capability, got {capability.message_kind}")
        kind = MessageKind.COMMAND if capability.message_kind == "command" else MessageKind.QUERY
        envelope = EnvelopeCodec.create(
            target_uri=target_uri,
            source_uri=source_uri,
            kind=kind,
            payload=payload,
            correlation_id=correlation_id,
            metadata=metadata,
        )
        self._validate_payload_contract(resolved, envelope)
        return await self.call_envelope(resolved, envelope, timeout=timeout)

    async def call_envelope(
        self, resolved: ResolvedCapability, envelope: Any, *, timeout: float = 2.0
    ) -> tuple[Any, RouteDecision]:
        order = list(resolved.capability.transport.ordered())
        decision = RouteDecision(
            uri=envelope.target_uri,
            capability_id=resolved.capability.id,
            runtime=resolved.capability.runtime,
            params=dict(resolved.params),
            transport_order=order,
            attempted=[],
        )
        errors: list[str] = []
        for name in order:
            transport = self.transports.get(name)
            if transport is None:
                msg = "transport not configured"
                decision.attempted.append({"transport": name, "result": "unavailable", "detail": msg})
                errors.append(f"{name}: {msg}")
                continue
            try:
                reply = await transport.call(resolved, envelope, timeout=timeout)
                decision.attempted.append({"transport": name, "result": "ok", "detail": ""})
                decision.selected_transport = name
                return reply, decision
            except TransportError as exc:
                decision.attempted.append({"transport": name, "result": "failed", "detail": str(exc)})
                errors.append(f"{name}: {exc}")
        raise RuntimeErrorIfuri(
            f"all transports failed for {resolved.capability.id}: " + "; ".join(errors)
        )

    async def emit(
        self,
        target_uri: str,
        payload: Message | None,
        *,
        source_uri: str = "ifuri://system/runtime/default/events/emitted",
        correlation_id: str = "",
        causation_id: str = "",
        aggregate_id: str = "",
        aggregate_version: int = 0,
        metadata: dict[str, str] | None = None,
    ) -> tuple[dict[str, Any], RouteDecision]:
        resolved = self.registry.resolve(target_uri)
        if resolved.capability.message_kind != "event":
            raise RuntimeErrorIfuri("emit() requires an event capability")
        envelope = EnvelopeCodec.create(
            target_uri=target_uri,
            source_uri=source_uri,
            kind=MessageKind.EVENT,
            payload=payload,
            correlation_id=correlation_id,
            causation_id=causation_id,
            aggregate_id=aggregate_id,
            aggregate_version=aggregate_version,
            metadata=metadata,
        )
        self._validate_payload_contract(resolved, envelope)
        order = list(resolved.capability.transport.ordered())
        decision = RouteDecision(
            uri=target_uri,
            capability_id=resolved.capability.id,
            runtime=resolved.capability.runtime,
            params=dict(resolved.params),
            transport_order=order,
            attempted=[],
        )
        errors: list[str] = []
        for name in order:
            transport = self.transports.get(name)
            if transport is None:
                decision.attempted.append({"transport": name, "result": "unavailable", "detail": "transport not configured"})
                errors.append(f"{name}: not configured")
                continue
            try:
                result = await transport.publish(resolved, envelope)
                decision.attempted.append({"transport": name, "result": "ok", "detail": ""})
                decision.selected_transport = name
                return result, decision
            except TransportError as exc:
                decision.attempted.append({"transport": name, "result": "failed", "detail": str(exc)})
                errors.append(f"{name}: {exc}")
        raise RuntimeErrorIfuri(f"all event transports failed: {'; '.join(errors)}")

    @staticmethod
    def _validate_payload_contract(resolved: ResolvedCapability, envelope: Any) -> None:
        expected = resolved.capability.input_type.strip()
        if not expected or expected.startswith("ifuri.dsl."):
            return
        actual = envelope.payload.type_url.rsplit("/", 1)[-1] if envelope.payload.type_url else ""
        if actual and actual != expected:
            raise RuntimeErrorIfuri(
                f"payload contract mismatch for {resolved.capability.id}: expected {expected}, got {actual}"
            )
