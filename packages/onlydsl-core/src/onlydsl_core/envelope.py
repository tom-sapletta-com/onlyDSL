"""Transport-neutral Protobuf envelope codec."""

from __future__ import annotations

import time
import uuid
from dataclasses import dataclass
from enum import IntEnum
from typing import Mapping

from google.protobuf.any_pb2 import Any as AnyMessage
from google.protobuf.message import Message
from google.protobuf.timestamp_pb2 import Timestamp

from . import envelope_pb2
from onlydsl_contracts.ifuri import IfUri


class EnvelopeError(ValueError):
    pass


class MessageKind(IntEnum):
    UNSPECIFIED = envelope_pb2.MESSAGE_KIND_UNSPECIFIED
    COMMAND = envelope_pb2.COMMAND
    QUERY = envelope_pb2.QUERY
    EVENT = envelope_pb2.EVENT
    REPLY = envelope_pb2.REPLY


@dataclass(frozen=True, slots=True)
class EnvelopeView:
    envelope_version: int
    id: str
    target_uri: str
    source_uri: str
    kind: MessageKind
    payload_type: str
    correlation_id: str
    causation_id: str
    aggregate_id: str
    aggregate_version: int
    metadata: dict[str, str]


class EnvelopeCodec:
    CURRENT_VERSION = 1

    @staticmethod
    def create(
        *,
        target_uri: str,
        source_uri: str,
        kind: MessageKind,
        payload: Message | None = None,
        message_id: str | None = None,
        correlation_id: str = "",
        causation_id: str = "",
        aggregate_id: str = "",
        aggregate_version: int = 0,
        metadata: Mapping[str, str] | None = None,
    ) -> envelope_pb2.Envelope:
        target = IfUri.parse(target_uri)
        source = IfUri.parse(source_uri)
        EnvelopeCodec._validate_kind_uri(kind, target)
        env = envelope_pb2.Envelope(
            envelope_version=EnvelopeCodec.CURRENT_VERSION,
            id=message_id or uuid.uuid4().hex,
            target_uri=str(target),
            source_uri=str(source),
            kind=int(kind),
            correlation_id=correlation_id,
            causation_id=causation_id,
            aggregate_id=aggregate_id,
            aggregate_version=max(0, int(aggregate_version)),
        )
        now = Timestamp()
        now.FromMilliseconds(int(time.time() * 1000))
        env.created_at.CopyFrom(now)
        if payload is not None:
            packed = AnyMessage()
            packed.Pack(payload)
            env.payload.CopyFrom(packed)
        if metadata:
            env.metadata.update({str(k): str(v) for k, v in metadata.items()})
        EnvelopeCodec.validate(env)
        return env

    @staticmethod
    def validate(env: envelope_pb2.Envelope) -> None:
        if env.envelope_version != EnvelopeCodec.CURRENT_VERSION:
            raise EnvelopeError(f"unsupported envelope_version: {env.envelope_version}")
        if not env.id:
            raise EnvelopeError("envelope id is required")
        target = IfUri.parse(env.target_uri)
        IfUri.parse(env.source_uri)
        try:
            kind = MessageKind(env.kind)
        except ValueError as exc:
            raise EnvelopeError(f"invalid message kind: {env.kind}") from exc
        if kind == MessageKind.UNSPECIFIED:
            raise EnvelopeError("message kind must be specified")
        EnvelopeCodec._validate_kind_uri(kind, target)
        if env.created_at.seconds == 0 and env.created_at.nanos == 0:
            raise EnvelopeError("created_at is required")

    @staticmethod
    def _validate_kind_uri(kind: MessageKind, uri: IfUri) -> None:
        expected = {
            MessageKind.COMMAND: "commands",
            MessageKind.QUERY: "queries",
            MessageKind.EVENT: "events",
        }.get(kind)
        if expected and uri.kind != expected:
            raise EnvelopeError(f"message kind {kind.name} requires URI kind '{expected}'")

    @staticmethod
    def serialize(env: envelope_pb2.Envelope) -> bytes:
        EnvelopeCodec.validate(env)
        return env.SerializeToString(deterministic=True)

    @staticmethod
    def parse(data: bytes) -> envelope_pb2.Envelope:
        env = envelope_pb2.Envelope()
        env.ParseFromString(data)
        EnvelopeCodec.validate(env)
        return env

    @staticmethod
    def unpack(env: envelope_pb2.Envelope, message: Message) -> Message:
        if not env.payload.Unpack(message):
            raise EnvelopeError(
                f"payload {env.payload.type_url!r} cannot be unpacked as "
                f"{message.DESCRIPTOR.full_name}"
            )
        return message

    @staticmethod
    def view(env: envelope_pb2.Envelope) -> EnvelopeView:
        EnvelopeCodec.validate(env)
        return EnvelopeView(
            env.envelope_version,
            env.id,
            env.target_uri,
            env.source_uri,
            MessageKind(env.kind),
            env.payload.type_url,
            env.correlation_id,
            env.causation_id,
            env.aggregate_id,
            env.aggregate_version,
            dict(env.metadata),
        )
