from __future__ import annotations

import asyncio
import base64
import json
import secrets
from dataclasses import dataclass
from typing import Any, Awaitable, Callable, Protocol

from .envelope import EnvelopeCodec, MessageKind
from .manifest import Capability, CapabilityRegistry, ResolvedCapability
from .uri import IfUri


class TransportError(RuntimeError):
    pass


@dataclass(slots=True)
class NatsMessage:
    subject: str
    sid: int
    reply: str
    data: bytes


class IfTransport(Protocol):
    name: str

    async def call(self, resolved: ResolvedCapability, envelope: Any, timeout: float = 2.0) -> Any:
        ...

    async def publish(self, resolved: ResolvedCapability, envelope: Any) -> dict[str, Any]:
        ...


Handler = Callable[[ResolvedCapability, Any], Any | Awaitable[Any]]


class InProcessTransport:
    name = "inproc"

    def __init__(self) -> None:
        self._handlers: dict[str, Handler] = {}
        self.published: list[bytes] = []

    def register(self, capability_id: str, handler: Handler) -> None:
        if capability_id in self._handlers:
            raise TransportError(f"handler already registered: {capability_id}")
        self._handlers[capability_id] = handler

    def has_handler(self, capability_id: str) -> bool:
        return capability_id in self._handlers

    async def call(self, resolved: ResolvedCapability, envelope: Any, timeout: float = 2.0) -> Any:
        handler = self._handlers.get(resolved.capability.id)
        if handler is None:
            raise TransportError(f"no inproc handler for {resolved.capability.id}")
        result = handler(resolved, envelope)
        if asyncio.iscoroutine(result):
            result = await asyncio.wait_for(result, timeout)
        return result

    async def publish(self, resolved: ResolvedCapability, envelope: Any) -> dict[str, Any]:
        self.published.append(EnvelopeCodec.serialize(envelope))
        handler = self._handlers.get(resolved.capability.id)
        if handler is not None:
            result = handler(resolved, envelope)
            if asyncio.iscoroutine(result):
                await result
        return {"transport": self.name, "stored": False, "delivered": handler is not None}


class NatsWireClient:
    """Small dependency-free NATS protocol client used by the POC.

    It intentionally implements only the protocol surface required here:
    CONNECT, PING/PONG, SUB/UNSUB, PUB and MSG.
    """

    def __init__(self, host: str = "127.0.0.1", port: int = 4222, name: str = "ifuri-poc") -> None:
        self.host = host
        self.port = int(port)
        self.name = name
        self.reader: asyncio.StreamReader | None = None
        self.writer: asyncio.StreamWriter | None = None
        self._reader_task: asyncio.Task[None] | None = None
        self._write_lock = asyncio.Lock()
        self._sid = 0
        self._subs: dict[int, asyncio.Queue[NatsMessage]] = {}
        self._closed = False
        self.server_info: dict[str, Any] = {}
        self.last_error: str = ""

    async def connect(self) -> "NatsWireClient":
        if self.writer is not None:
            return self
        self.reader, self.writer = await asyncio.open_connection(self.host, self.port)
        info_line = await asyncio.wait_for(self.reader.readline(), timeout=3)
        if not info_line.startswith(b"INFO "):
            raise TransportError(f"NATS expected INFO, got {info_line[:120]!r}")
        try:
            self.server_info = json.loads(info_line[5:].decode("utf-8"))
        except Exception as exc:
            raise TransportError("invalid NATS INFO payload") from exc
        payload = {
            "verbose": False,
            "pedantic": False,
            "tls_required": False,
            "name": self.name,
            "lang": "python-stdlib",
            "version": "0.3",
            "protocol": 1,
            "echo": True,
        }
        await self._write(b"CONNECT " + json.dumps(payload, separators=(",", ":")).encode() + b"\r\n")
        self._reader_task = asyncio.create_task(self._reader_loop(), name=f"nats-reader:{self.name}")
        await self.flush()
        return self

    async def _write(self, data: bytes) -> None:
        if self.writer is None:
            raise TransportError("NATS client is not connected")
        async with self._write_lock:
            self.writer.write(data)
            await self.writer.drain()

    async def flush(self, timeout: float = 2.0) -> None:
        inbox = f"_INBOX.FLUSH.{secrets.token_hex(8)}"
        # A request itself verifies both publish and receive paths and avoids a special PONG waiter.
        sid, q = await self.subscribe(inbox, max_msgs=1)
        await self.publish(inbox, b"ok")
        try:
            await asyncio.wait_for(q.get(), timeout)
        finally:
            await self.unsubscribe(sid)

    async def subscribe(
        self, subject: str, *, queue_group: str = "", max_msgs: int | None = None
    ) -> tuple[int, asyncio.Queue[NatsMessage]]:
        _validate_nats_subject(subject, allow_wildcards=True)
        self._sid += 1
        sid = self._sid
        q: asyncio.Queue[NatsMessage] = asyncio.Queue()
        self._subs[sid] = q
        if queue_group:
            command = f"SUB {subject} {queue_group} {sid}\r\n".encode()
        else:
            command = f"SUB {subject} {sid}\r\n".encode()
        await self._write(command)
        if max_msgs is not None:
            await self._write(f"UNSUB {sid} {int(max_msgs)}\r\n".encode())
        return sid, q

    async def unsubscribe(self, sid: int) -> None:
        if sid in self._subs:
            await self._write(f"UNSUB {sid}\r\n".encode())
            self._subs.pop(sid, None)

    async def publish(self, subject: str, data: bytes, reply: str = "") -> None:
        _validate_nats_subject(subject, allow_wildcards=False)
        if reply:
            _validate_nats_subject(reply, allow_wildcards=False)
            header = f"PUB {subject} {reply} {len(data)}\r\n".encode()
        else:
            header = f"PUB {subject} {len(data)}\r\n".encode()
        await self._write(header + data + b"\r\n")

    async def request(self, subject: str, data: bytes, timeout: float = 2.0) -> bytes:
        inbox = f"_INBOX.IFURI.{secrets.token_hex(12)}"
        sid, q = await self.subscribe(inbox, max_msgs=1)
        try:
            await self.publish(subject, data, reply=inbox)
            msg = await asyncio.wait_for(q.get(), timeout)
            return msg.data
        except asyncio.TimeoutError as exc:
            raise TransportError(f"NATS request timeout for {subject}") from exc
        finally:
            await self.unsubscribe(sid)

    async def close(self) -> None:
        self._closed = True
        if self._reader_task is not None:
            self._reader_task.cancel()
            try:
                await self._reader_task
            except BaseException:
                pass
            self._reader_task = None
        if self.writer is not None:
            self.writer.close()
            try:
                await self.writer.wait_closed()
            except Exception:
                pass
        self.writer = None
        self.reader = None
        self._subs.clear()

    async def _reader_loop(self) -> None:
        assert self.reader is not None
        try:
            while not self._closed:
                line = await self.reader.readline()
                if not line:
                    break
                line = line.rstrip(b"\r\n")
                if not line:
                    continue
                if line == b"PING":
                    await self._write(b"PONG\r\n")
                    continue
                if line in {b"PONG", b"+OK"} or line.startswith(b"INFO "):
                    continue
                if line.startswith(b"-ERR"):
                    self.last_error = line.decode("utf-8", errors="replace")
                    continue
                if line.startswith(b"MSG "):
                    parts = line.split()
                    if len(parts) == 4:
                        _, subject_b, sid_b, size_b = parts
                        reply_b = b""
                    elif len(parts) == 5:
                        _, subject_b, sid_b, reply_b, size_b = parts
                    else:
                        raise TransportError(f"unsupported NATS MSG header: {line!r}")
                    size = int(size_b)
                    data = await self.reader.readexactly(size)
                    crlf = await self.reader.readexactly(2)
                    if crlf != b"\r\n":
                        raise TransportError("invalid NATS payload terminator")
                    sid = int(sid_b)
                    q = self._subs.get(sid)
                    if q is not None:
                        await q.put(
                            NatsMessage(
                                subject_b.decode(),
                                sid,
                                reply_b.decode() if reply_b else "",
                                data,
                            )
                        )
                    continue
                if line.startswith(b"HMSG "):
                    raise TransportError("HMSG is not enabled in this minimal POC client")
                raise TransportError(f"unsupported NATS protocol line: {line!r}")
        except asyncio.CancelledError:
            raise
        except Exception as exc:
            self.last_error = f"{type(exc).__name__}: {exc}"
            for q in self._subs.values():
                # Do not fabricate a message; request() will timeout with a deterministic error.
                pass


class NatsJetStream:
    def __init__(self, client: NatsWireClient):
        self.client = client

    async def create_stream(
        self,
        name: str,
        subjects: list[str],
        *,
        storage: str = "memory",
        retention: str = "limits",
    ) -> dict[str, Any]:
        payload = {
            "name": name,
            "subjects": subjects,
            "storage": storage,
            "retention": retention,
            "discard": "old",
            "num_replicas": 1,
        }
        raw = await self.client.request(
            f"$JS.API.STREAM.CREATE.{name}", json.dumps(payload, separators=(",", ":")).encode(), 4.0
        )
        return _js_response(raw)

    async def stream_info(self, name: str) -> dict[str, Any]:
        raw = await self.client.request(f"$JS.API.STREAM.INFO.{name}", b"{}", 3.0)
        return _js_response(raw)

    async def publish(self, subject: str, data: bytes) -> dict[str, Any]:
        raw = await self.client.request(subject, data, 3.0)
        return _js_response(raw)

    async def get_message(self, stream: str, seq: int) -> dict[str, Any] | None:
        raw = await self.client.request(
            f"$JS.API.STREAM.MSG.GET.{stream}",
            json.dumps({"seq": int(seq)}, separators=(",", ":")).encode(),
            3.0,
        )
        body = json.loads(raw.decode("utf-8"))
        if "error" in body:
            if int(body["error"].get("code", 0)) == 404:
                return None
            raise TransportError(f"JetStream error: {body['error']}")
        msg = body.get("message") or {}
        encoded = msg.get("data", "")
        msg["data_bytes"] = base64.b64decode(encoded) if encoded else b""
        return msg

    async def replay(self, stream: str) -> list[dict[str, Any]]:
        info = await self.stream_info(stream)
        state = info.get("state", {})
        first_seq = int(state.get("first_seq", 0) or 0)
        last_seq = int(state.get("last_seq", 0) or 0)
        out: list[dict[str, Any]] = []
        for seq in range(first_seq, last_seq + 1):
            msg = await self.get_message(stream, seq)
            if msg is not None:
                out.append(msg)
        return out


class NatsTransport:
    name = "nats"

    def __init__(self, client: NatsWireClient, *, event_stream: str = "IFURI_EVENTS") -> None:
        self.client = client
        self.js = NatsJetStream(client)
        self.event_stream = event_stream
        self._service_tasks: list[asyncio.Task[None]] = []
        self._service_sids: list[int] = []

    async def call(self, resolved: ResolvedCapability, envelope: Any, timeout: float = 2.0) -> Any:
        subject = resolved.uri.to_subject()
        raw = await self.client.request(subject, EnvelopeCodec.serialize(envelope), timeout)
        return EnvelopeCodec.parse(raw)

    async def publish(self, resolved: ResolvedCapability, envelope: Any) -> dict[str, Any]:
        subject = resolved.uri.to_subject()
        if resolved.capability.durable or resolved.uri.is_event:
            ack = await self.js.publish(subject, EnvelopeCodec.serialize(envelope))
            return {"transport": self.name, "stored": True, "ack": ack}
        await self.client.publish(subject, EnvelopeCodec.serialize(envelope))
        return {"transport": self.name, "stored": False}

    async def ensure_event_stream(self, subjects: list[str] | None = None) -> dict[str, Any]:
        subjects = subjects or ["ifuri.evt.>"]
        try:
            return await self.js.create_stream(self.event_stream, subjects)
        except TransportError as exc:
            # If stream already exists, return info. NATS API reports this as an error response.
            if "stream name already in use" not in str(exc).lower():
                raise
            return await self.js.stream_info(self.event_stream)

    async def serve_capability(
        self,
        capability: Capability,
        registry: CapabilityRegistry,
        handler: Handler,
        *,
        queue_group: str = "",
    ) -> None:
        subject = capability_pattern_to_subject(capability.uri_pattern)
        sid, q = await self.client.subscribe(subject, queue_group=queue_group)
        self._service_sids.append(sid)

        async def loop() -> None:
            while True:
                msg = await q.get()
                try:
                    env = EnvelopeCodec.parse(msg.data)
                    resolved = registry.resolve(env.target_uri)
                    if resolved.capability.id != capability.id:
                        raise TransportError(
                            f"subject route resolved to {resolved.capability.id}, expected {capability.id}"
                        )
                    result = handler(resolved, env)
                    if asyncio.iscoroutine(result):
                        result = await result
                    if msg.reply:
                        if result is None:
                            result = EnvelopeCodec.create(
                                target_uri=env.source_uri,
                                source_uri=env.target_uri,
                                kind=MessageKind.REPLY,
                                correlation_id=env.correlation_id or env.id,
                            )
                        await self.client.publish(msg.reply, EnvelopeCodec.serialize(result))
                except Exception as exc:
                    if msg.reply:
                        err = EnvelopeCodec.create(
                            target_uri="ifuri://system/error/default/events/reply_error",
                            source_uri="ifuri://system/nats/default/events/transport_error",
                            kind=MessageKind.REPLY,
                            correlation_id="",
                            metadata={"ok": "false", "error": f"{type(exc).__name__}:{exc}"[:512]},
                        )
                        await self.client.publish(msg.reply, EnvelopeCodec.serialize(err))

        self._service_tasks.append(asyncio.create_task(loop(), name=f"serve:{capability.id}"))

    async def stop_services(self) -> None:
        for task in self._service_tasks:
            task.cancel()
        for task in self._service_tasks:
            try:
                await task
            except BaseException:
                pass
        self._service_tasks.clear()
        for sid in self._service_sids:
            await self.client.unsubscribe(sid)
        self._service_sids.clear()


def capability_pattern_to_subject(pattern: str, prefix: str = "ifuri") -> str:
    from urllib.parse import urlsplit

    parsed = urlsplit(pattern)
    parts = [parsed.hostname or "", *[x for x in parsed.path.split("/") if x]]
    if len(parts) != 5:
        raise TransportError(f"invalid capability pattern: {pattern}")
    context, entity, identity, kind, operation = parts
    kind_prefix = {"commands": "cmd", "queries": "qry", "events": "evt", "artifacts": "art", "streams": "str"}[kind]

    def token(v: str) -> str:
        return "*" if v.startswith("{") and v.endswith("}") else v

    return ".".join([prefix, kind_prefix, token(context), token(entity), token(identity), token(operation)])


def _validate_nats_subject(subject: str, *, allow_wildcards: bool) -> None:
    if not subject or any(ch.isspace() for ch in subject):
        raise TransportError(f"invalid NATS subject: {subject!r}")
    if not allow_wildcards and ("*" in subject or ">" in subject):
        raise TransportError("wildcards are forbidden for publish subjects")


def _js_response(raw: bytes) -> dict[str, Any]:
    try:
        body = json.loads(raw.decode("utf-8"))
    except Exception as exc:
        raise TransportError(f"invalid JetStream response: {raw[:160]!r}") from exc
    if "error" in body:
        raise TransportError(f"JetStream error: {body['error']}")
    return body
